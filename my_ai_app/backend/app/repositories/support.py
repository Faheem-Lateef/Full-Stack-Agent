"""SQL access for workspace support, including durable job claims."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.support import (
    Chunk,
    Document,
    Draft,
    Invitation,
    Membership,
    SupportAudit,
    SupportCase,
    SupportJob,
    Workspace,
)
from app.db.models.user import User


class SupportRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, obj):
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def flush(self):
        await self.db.flush()

    async def delete_workspace(self, wid: UUID):
        await self.db.execute(delete(Workspace).where(Workspace.id == wid))

    async def workspace(self, wid: UUID, *, lock=False):
        stmt = select(Workspace).where(Workspace.id == wid)
        if lock:
            stmt = stmt.with_for_update()
        obj = await self.db.scalar(stmt)
        if obj is None:
            raise NotFoundError("Workspace not found")
        return obj

    async def membership(self, wid: UUID, uid: UUID):
        return await self.db.scalar(
            select(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.workspace_id == wid, Membership.user_id == uid, User.is_active.is_(True)
            )
        )

    async def search_cases(self, wid: UUID, query: str):
        stmt = select(SupportCase).where(SupportCase.workspace_id == wid)
        if query:
            stmt = stmt.where(SupportCase.question.icontains(query, autoescape=True))
        return list(
            (await self.db.scalars(stmt.order_by(SupportCase.created_at.desc()).limit(200))).all()
        )

    async def workspaces(self, uid: UUID):
        rows = (
            await self.db.execute(
                select(Workspace, Membership.role)
                .join(Membership)
                .where(Membership.user_id == uid)
                .order_by(Workspace.created_at)
            )
        ).all()
        return [
            {"id": w.id, "name": w.name, "tone": w.tone, "escalation": w.escalation, "role": role}
            for w, role in rows
        ]

    async def members(self, wid: UUID):
        rows = (
            await self.db.execute(
                select(Membership, User.email)
                .join(User, User.id == Membership.user_id)
                .where(Membership.workspace_id == wid)
            )
        ).all()
        return [{"user_id": m.user_id, "email": email, "role": m.role} for m, email in rows]

    async def remove_member(self, wid: UUID, uid: UUID):
        await self.db.execute(
            delete(Membership).where(Membership.workspace_id == wid, Membership.user_id == uid)
        )
        await self.db.execute(
            update(SupportJob)
            .where(
                SupportJob.workspace_id == wid,
                SupportJob.actor_id == uid,
                SupportJob.state.in_(["queued", "processing"]),
            )
            .values(state="cancelled")
        )

    async def invitation(self, digest: str):
        return await self.db.scalar(
            select(Invitation).where(Invitation.token_hash == digest).with_for_update()
        )

    async def scoped(self, model, wid: UUID, oid: UUID, *, lock=False):
        stmt = select(model).where(model.workspace_id == wid, model.id == oid)
        if lock:
            stmt = stmt.with_for_update()
        obj = await self.db.scalar(stmt)
        if obj is None:
            raise NotFoundError("Record not found")
        return obj

    async def listing(self, model, wid: UUID, **filters):
        stmt = select(model).where(model.workspace_id == wid)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        if hasattr(model, "created_at"):
            stmt = stmt.order_by(model.created_at.desc())
        return list((await self.db.scalars(stmt.limit(200))).all())

    async def usage(self, wid: UUID):
        month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        runs = await self.db.scalar(
            select(func.count())
            .select_from(SupportJob)
            .where(
                SupportJob.workspace_id == wid,
                SupportJob.kind == "generate",
                SupportJob.created_at >= month,
            )
        )
        size = await self.db.scalar(
            select(func.coalesce(func.sum(Document.size), 0)).where(
                Document.workspace_id == wid, Document.state != "deleted"
            )
        )
        count = await self.db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.workspace_id == wid, Document.state != "deleted")
        )
        active = await self.db.scalar(
            select(func.count())
            .select_from(SupportJob)
            .where(SupportJob.workspace_id == wid, SupportJob.state.in_(["queued", "processing"]))
        )
        return {
            "generations_this_month": runs,
            "storage_bytes": size,
            "documents": count,
            "active_jobs": active,
        }

    async def existing_job(self, wid: UUID, key: str):
        return await self.db.scalar(
            select(SupportJob).where(SupportJob.workspace_id == wid, SupportJob.request_key == key)
        )

    async def chunks(self, wid: UUID):
        return list(
            (
                await self.db.execute(
                    select(Chunk, Document.title)
                    .join(Document, Document.id == Chunk.document_id)
                    .where(
                        Chunk.workspace_id == wid,
                        Document.workspace_id == wid,
                        Document.state == "ready",
                    )
                    .limit(5001)
                )
            ).all()
        )

    async def purge_chunks(self, wid: UUID, did: UUID):
        await self.db.execute(
            delete(Chunk).where(Chunk.workspace_id == wid, Chunk.document_id == did)
        )

    async def original(self, wid: UUID, did: UUID):
        return await self.db.scalar(
            select(Document.original).where(Document.workspace_id == wid, Document.id == did)
        )

    async def purge_citations(self, wid: UUID, did: UUID):
        # No document text in history: citation records contain identifiers only.
        drafts = (await self.db.scalars(select(Draft).where(Draft.workspace_id == wid))).all()
        for draft in drafts:
            if any(c["document_id"] == str(did) for c in draft.citations):
                draft.citations = [
                    {**c, "unavailable": True} if c["document_id"] == str(did) else c
                    for c in draft.citations
                ]
                draft.approved_by = None

    async def audit(self, wid: UUID, uid: UUID, action: str, target: UUID | None = None):
        await self.add(
            SupportAudit(workspace_id=wid, actor_id=uid, action=action, target_id=target)
        )

    async def claim(self):
        # Serialize short claim transactions across worker processes.
        if not await self.db.scalar(select(func.pg_try_advisory_xact_lock(728194021))):
            return None
        # Paid generation is never automatically replayed after uncertain completion.
        stale = datetime.now(UTC) - timedelta(minutes=5)
        await self.db.execute(
            update(SupportJob)
            .where(SupportJob.state == "processing", SupportJob.started_at < stale)
            .values(state="failed", error="Worker interrupted. Review usage before retrying.")
        )
        await self.db.execute(
            update(Document)
            .where(
                Document.state == "queued",
                Document.id.in_(
                    select(SupportJob.target_id).where(
                        SupportJob.kind == "ingest", SupportJob.state == "failed"
                    )
                ),
            )
            .values(state="failed", error="Worker interrupted. Retry processing.")
        )
        active = await self.db.scalar(
            select(func.count()).select_from(SupportJob).where(SupportJob.state == "processing")
        )
        if active >= 4:
            return None
        job = await self.db.scalar(
            select(SupportJob)
            .where(SupportJob.state == "queued")
            .order_by(SupportJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job:
            job.state = "processing"
            job.started_at = datetime.now(UTC)
            await self.db.flush()
        return job

    async def case_drafts(self, wid: UUID, cid: UUID):
        await self.scoped(SupportCase, wid, cid)
        return await self.listing(Draft, wid, case_id=cid)
