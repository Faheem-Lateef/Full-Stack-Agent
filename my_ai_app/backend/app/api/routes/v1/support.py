"""Workspace-scoped support API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import inspect

from app.api.deps import CurrentUser, DBSession
from app.core.config import settings
from app.db.models.support import Chunk, Document, Draft, Invitation, SupportCase, SupportJob
from app.schemas.support import (
    AcceptInput,
    CaseInput,
    DeleteWorkspaceInput,
    DraftInput,
    FeedbackInput,
    GenerateInput,
    InviteInput,
    RoleInput,
    VersionInput,
    WorkspaceInput,
)
from app.services.knowledge import search
from app.services.support import SupportService


def enabled():
    if not settings.SUPPORT_ENABLED:
        raise HTTPException(404, "Support workspace is not enabled")


router = APIRouter(dependencies=[Depends(enabled)])


def service(db: DBSession):
    return SupportService(db)


Svc = Annotated[SupportService, Depends(service)]


def public(obj):
    return {
        attr.key: getattr(obj, attr.key)
        for attr in inspect(type(obj)).column_attrs
        if attr.key not in {"original", "token_hash", "embedding"}
    }


@router.get("")
async def workspaces(svc: Svc, user: CurrentUser):
    return await svc.repo.workspaces(user.id)


@router.post("", status_code=201)
async def create_workspace(data: WorkspaceInput, svc: Svc, user: CurrentUser):
    return public(await svc.create_workspace(user, data))


@router.post("/accept-invitation")
async def accept(data: AcceptInput, svc: Svc, user: CurrentUser):
    return await svc.accept(user, data.token)


@router.patch("/{wid}")
async def update_workspace(wid: UUID, data: WorkspaceInput, svc: Svc, user: CurrentUser):
    workspace, _ = await svc.authorize(wid, user, manage=True, lock=True)
    for key, value in data.model_dump().items():
        setattr(workspace, key, value)
    await svc.repo.audit(wid, user.id, "workspace.updated", wid)
    return public(workspace)


@router.delete("/{wid}")
async def delete_workspace(wid: UUID, data: DeleteWorkspaceInput, svc: Svc, user: CurrentUser):
    workspace, _ = await svc.authorize(wid, user, owner=True, lock=True)
    if workspace.name != data.name:
        raise HTTPException(422, "Type the exact workspace name to confirm deletion")
    await svc.repo.delete_workspace(wid)
    return {"deleted": True}


@router.get("/{wid}/members")
async def members(wid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    return await svc.repo.members(wid)


@router.patch("/{wid}/members/{uid}")
async def role(wid: UUID, uid: UUID, data: RoleInput, svc: Svc, user: CurrentUser):
    await svc.change_member(wid, user, uid, data.role)
    return {"updated": True}


@router.delete("/{wid}/members/{uid}")
async def remove(wid: UUID, uid: UUID, svc: Svc, user: CurrentUser):
    await svc.change_member(wid, user, uid)
    return {"removed": True}


@router.post("/{wid}/invitations", status_code=201)
async def invite(wid: UUID, data: InviteInput, svc: Svc, user: CurrentUser):
    return await svc.invite(wid, user, data)


@router.get("/{wid}/invitations")
async def invitations(wid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user, manage=True)
    return [public(i) for i in await svc.repo.listing(Invitation, wid)]


@router.delete("/{wid}/invitations/{iid}")
async def revoke_invite(wid: UUID, iid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user, manage=True)
    invitation = await svc.repo.scoped(Invitation, wid, iid, lock=True)
    invitation.consumed = True
    return {"revoked": True}


@router.get("/{wid}/knowledge")
async def documents(wid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    return [public(d) for d in await svc.repo.listing(Document, wid) if d.state != "deleted"]


@router.post("/{wid}/knowledge", status_code=202)
async def upload(
    wid: UUID,
    svc: Svc,
    user: CurrentUser,
    file: UploadFile = File(...),
    replaces: UUID | None = None,
):
    await svc.authorize(wid, user, manage=True)
    # Bound memory even if multipart metadata lies about size.
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Maximum document size is 10 MB")
    return public(await svc.upload(wid, user, file.filename or "document.txt", content, replaces))


@router.get("/{wid}/knowledge/search")
async def search_knowledge(
    wid: UUID, svc: Svc, user: CurrentUser, q: str = Query(min_length=2, max_length=2000)
):
    await svc.authorize(wid, user)
    return {
        "mode": "hybrid" if settings.SUPPORT_EMBEDDINGS_ENABLED else "keyword",
        "sources": await search(svc.repo, wid, q),
    }


@router.get("/{wid}/knowledge/chunks/{cid}")
async def source(wid: UUID, cid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    chunk = await svc.repo.scoped(Chunk, wid, cid)
    doc = await svc.repo.scoped(Document, wid, chunk.document_id)
    if doc.state != "ready":
        raise HTTPException(410, "Source is no longer current")
    return {**public(chunk), "title": doc.title}


@router.delete("/{wid}/knowledge/{did}")
async def delete_document(wid: UUID, did: UUID, svc: Svc, user: CurrentUser, archive: bool = False):
    await svc.delete_document(wid, user, did, archive)
    return {"deleted": not archive, "archived": archive}


@router.post("/{wid}/knowledge/{did}/retry", status_code=202)
async def retry(wid: UUID, did: UUID, svc: Svc, user: CurrentUser):
    return public(await svc.retry_document(wid, user, did))


@router.get("/{wid}/support/cases")
async def cases(wid: UUID, svc: Svc, user: CurrentUser, q: str = Query(default="", max_length=200)):
    await svc.authorize(wid, user)
    return [public(c) for c in await svc.repo.search_cases(wid, q)]


@router.post("/{wid}/support/cases", status_code=201)
async def create_case(wid: UUID, data: CaseInput, svc: Svc, user: CurrentUser):
    return public(await svc.create_case(wid, user, data.question))


@router.get("/{wid}/support/cases/{cid}")
async def case(wid: UUID, cid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    return {
        "case": public(await svc.repo.scoped(SupportCase, wid, cid)),
        "drafts": [public(d) for d in await svc.repo.case_drafts(wid, cid)],
    }


@router.post("/{wid}/support/cases/{cid}/generations", status_code=202)
async def generate(wid: UUID, cid: UUID, data: GenerateInput, svc: Svc, user: CurrentUser):
    return public(await svc.generate(wid, user, cid, data.request_key))


@router.get("/{wid}/jobs")
async def jobs(wid: UUID, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    return [public(j) for j in await svc.repo.listing(SupportJob, wid)]


@router.post("/{wid}/jobs/{jid}/cancel")
async def cancel(wid: UUID, jid: UUID, svc: Svc, user: CurrentUser):
    _, member = await svc.authorize(wid, user, lock=True)
    job = await svc.repo.scoped(SupportJob, wid, jid, lock=True)
    if member.role == "agent" and job.actor_id != user.id:
        raise HTTPException(403, "Cannot cancel another member's job")
    if job.state in {"queued", "processing"}:
        job.state = "cancelled"
        if job.kind == "ingest":
            doc = await svc.repo.scoped(Document, wid, job.target_id)
            if doc.state == "queued":
                doc.state, doc.error = "failed", "Processing cancelled"
    return public(job)


@router.patch("/{wid}/support/drafts/{did}")
async def save_draft(wid: UUID, did: UUID, data: DraftInput, svc: Svc, user: CurrentUser):
    return public(await svc.edit_draft(wid, user, did, data))


@router.post("/{wid}/support/drafts/{did}/approve")
async def approve(wid: UUID, did: UUID, data: VersionInput, svc: Svc, user: CurrentUser):
    return public(await svc.approve(wid, user, did, data.version))


@router.post("/{wid}/support/drafts/{did}/copied")
async def copied(wid: UUID, did: UUID, data: VersionInput, svc: Svc, user: CurrentUser):
    return public(await svc.approve(wid, user, did, data.version, copied=True))


@router.post("/{wid}/support/drafts/{did}/feedback")
async def feedback(wid: UUID, did: UUID, data: FeedbackInput, svc: Svc, user: CurrentUser):
    await svc.authorize(wid, user)
    draft = await svc.repo.scoped(Draft, wid, did, lock=True)
    draft.feedback = data.feedback
    return {"saved": True}


@router.get("/{wid}/usage")
async def usage(wid: UUID, svc: Svc, user: CurrentUser):
    workspace, _ = await svc.authorize(wid, user)
    data = await svc.repo.usage(wid)
    return {
        **data,
        "generation_limit": workspace.generation_limit,
        "search_mode": "hybrid" if settings.SUPPORT_EMBEDDINGS_ENABLED else "keyword",
        "provider_configured": bool(
            settings.OPENAI_API_KEY
            if settings.LLM_PROVIDER == "openai"
            else settings.ORCAROUTER_API_KEY
        ),
    }
