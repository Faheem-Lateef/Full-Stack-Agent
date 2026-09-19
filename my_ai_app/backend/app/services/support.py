"""Workspace policy and support workflow. Repository owns all SQL."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.db.models.support import (
    Document,
    Draft,
    Invitation,
    Membership,
    SupportCase,
    SupportJob,
    Workspace,
)
from app.repositories.support import SupportRepository


class SupportService:
    def __init__(self, db):
        self.repo = SupportRepository(db)

    async def authorize(self, wid, user, *, manage=False, owner=False, lock=False):
        workspace = await self.repo.workspace(wid, lock=lock)
        member = await self.repo.membership(wid, user.id)
        if not member:
            raise NotFoundError("Workspace not found")
        if owner and member.role != "owner":
            raise AuthorizationError("Workspace owner required")
        if manage and member.role not in {"owner", "admin"}:
            raise AuthorizationError("Workspace administrator required")
        return workspace, member

    async def create_workspace(self, user, data):
        if len(await self.repo.workspaces(user.id)) >= 10:
            raise RateLimitError("Workspace limit reached")
        workspace = await self.repo.add(Workspace(**data.model_dump()))
        await self.repo.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
        await self.repo.audit(workspace.id, user.id, "workspace.created", workspace.id)
        return workspace

    async def invite(self, wid, user, data):
        await self.authorize(wid, user, manage=True, lock=True)
        token = secrets.token_urlsafe(32)
        invite = await self.repo.add(
            Invitation(
                workspace_id=wid,
                email=str(data.email).lower(),
                role=data.role,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=3),
            )
        )
        await self.repo.audit(wid, user.id, "invitation.created", invite.id)
        return {"id": invite.id, "token": token, "expires_at": invite.expires_at}

    async def accept(self, user, token):
        invitation = await self.repo.invitation(hashlib.sha256(token.encode()).hexdigest())
        if not invitation or invitation.consumed or invitation.expires_at <= datetime.now(UTC):
            raise ValidationError("Invitation is invalid or expired")
        if user.email.lower() != invitation.email:
            raise AuthorizationError("Sign in using the invited email address")
        await self.repo.workspace(invitation.workspace_id, lock=True)
        if not await self.repo.membership(invitation.workspace_id, user.id):
            await self.repo.add(
                Membership(
                    workspace_id=invitation.workspace_id, user_id=user.id, role=invitation.role
                )
            )
        invitation.consumed = True
        await self.repo.audit(
            invitation.workspace_id, user.id, "invitation.accepted", invitation.id
        )
        return {"workspace_id": invitation.workspace_id}

    async def change_member(self, wid, user, uid, role=None):
        _, actor = await self.authorize(wid, user, manage=True, lock=True)
        target = await self.repo.membership(wid, uid)
        if not target:
            raise NotFoundError("Member not found")
        if (target.role == "owner" or role == "owner") and actor.role != "owner":
            raise AuthorizationError("Only an owner can change ownership")
        members = await self.repo.members(wid)
        if (
            target.role == "owner"
            and role != "owner"
            and sum(m["role"] == "owner" for m in members) <= 1
        ):
            raise ValidationError("The workspace must retain an owner")
        if role:
            target.role = role
        else:
            await self.repo.remove_member(wid, uid)
        await self.repo.audit(wid, user.id, "member.changed", uid)

    async def upload(self, wid, user, filename, data, replaces=None):
        await self.authorize(wid, user, manage=True, lock=True)
        filename = PurePath(filename.replace("\\", "/")).name[:200]
        ext = PurePath(filename).suffix.lower()
        if ext not in {".txt", ".md", ".pdf"} or not data or len(data) > 10 * 1024 * 1024:
            raise ValidationError("Upload a nonempty TXT, Markdown or text PDF, at most 10 MB")
        if ext == ".pdf" and not data.startswith(b"%PDF-"):
            raise ValidationError("File is not a PDF")
        if ext != ".pdf":
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValidationError("Text documents must use UTF-8") from exc
            if b"\x00" in data:
                raise ValidationError("Binary content is not accepted")
        usage = await self.repo.usage(wid)
        if usage["documents"] >= 100 or usage["storage_bytes"] + len(data) > 50 * 1024 * 1024:
            raise RateLimitError("Pilot knowledge allowance reached (100 documents / 50 MB)")
        if replaces:
            previous = await self.repo.scoped(Document, wid, replaces)
            if previous.state != "ready":
                raise ValidationError("Only a ready document can be replaced")
        doc = await self.repo.add(
            Document(
                workspace_id=wid,
                title=filename,
                filename=filename,
                checksum=hashlib.sha256(data).hexdigest(),
                original=data,
                size=len(data),
                replaces_id=replaces,
            )
        )
        await self.repo.add(
            SupportJob(
                workspace_id=wid,
                actor_id=user.id,
                kind="ingest",
                target_id=doc.id,
                request_key=str(uuid4()),
            )
        )
        await self.repo.audit(wid, user.id, "document.uploaded", doc.id)
        return doc

    async def delete_document(self, wid, user, did, archive=False):
        await self.authorize(wid, user, manage=True, lock=True)
        doc = await self.repo.scoped(Document, wid, did, lock=True)
        doc.state = "archived" if archive else "deleted"
        if not archive:
            doc.original = None
            doc.size = 0
            await self.repo.purge_chunks(wid, did)
            await self.repo.purge_citations(wid, did)
        await self.repo.audit(wid, user.id, "document." + doc.state, did)

    async def retry_document(self, wid, user, did):
        await self.authorize(wid, user, manage=True, lock=True)
        doc = await self.repo.scoped(Document, wid, did, lock=True)
        if doc.state != "failed":
            raise ValidationError("Only failed processing can be retried")
        doc.state, doc.error = "queued", None
        return await self.repo.add(
            SupportJob(
                workspace_id=wid,
                actor_id=user.id,
                kind="ingest",
                target_id=did,
                request_key=str(uuid4()),
            )
        )

    async def create_case(self, wid, user, question):
        await self.authorize(wid, user)
        return await self.repo.add(
            SupportCase(workspace_id=wid, created_by=user.id, question=question)
        )

    async def generate(self, wid, user, cid, key):
        workspace, _ = await self.authorize(wid, user, lock=True)
        await self.repo.scoped(SupportCase, wid, cid)
        existing = await self.repo.existing_job(wid, str(key))
        if existing:
            if existing.kind != "generate" or existing.target_id != cid:
                raise AlreadyExistsError("Request key already used for another operation")
            return existing
        key_value = (
            settings.OPENAI_API_KEY
            if settings.LLM_PROVIDER == "openai"
            else settings.ORCAROUTER_API_KEY
        )
        if not key_value.strip():
            raise ValidationError(
                "The operator must configure the selected LLM provider key before drafting"
            )
        usage = await self.repo.usage(wid)
        if (
            usage["generations_this_month"] >= workspace.generation_limit
            or usage["active_jobs"] >= 5
        ):
            raise RateLimitError("Workspace generation or concurrency allowance reached")
        job = await self.repo.add(
            SupportJob(
                workspace_id=wid,
                actor_id=user.id,
                kind="generate",
                target_id=cid,
                request_key=str(key),
            )
        )
        await self.repo.audit(wid, user.id, "generation.requested", job.id)
        return job

    async def edit_draft(self, wid, user, did, data):
        await self.authorize(wid, user)
        draft = await self.repo.scoped(Draft, wid, did, lock=True)
        if draft.version != data.version:
            raise AlreadyExistsError("Draft changed. Reload the latest revision before saving.")
        if len(draft.history) >= 100:
            raise ValidationError("Revision limit reached; create a new draft")
        draft.history = [
            *draft.history,
            {"version": draft.version, "reply": draft.reply, "actor_id": str(user.id)},
        ]
        draft.reply, draft.version, draft.approved_by = data.reply, draft.version + 1, None
        await self.repo.audit(wid, user.id, "draft.edited", did)
        return draft

    async def approve(self, wid, user, did, version, copied=False):
        await self.authorize(wid, user, lock=True)
        draft = await self.repo.scoped(Draft, wid, did, lock=True)
        if draft.version != version:
            raise AlreadyExistsError("Draft changed; review the latest revision")
        if copied and not draft.approved_by:
            raise ValidationError("Review and approve the draft first")
        for citation in draft.citations:
            doc = await self.repo.scoped(Document, wid, UUID(citation["document_id"]))
            if doc.state != "ready":
                raise ValidationError("A source is no longer current; regenerate and review")
        if not copied:
            draft.approved_by = user.id
        await self.repo.audit(wid, user.id, "draft.copied" if copied else "draft.approved", did)
        return draft
