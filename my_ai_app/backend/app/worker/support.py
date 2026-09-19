"""Run with: python -m app.worker.support. No paid automatic job replay."""

import asyncio
import contextlib
import logging
import time
from uuid import UUID

from app.agents.support import generate_answer
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.support import Chunk, Document, Draft, SupportCase, SupportJob
from app.db.session import get_worker_db_context
from app.repositories.support import SupportRepository
from app.services.knowledge import embeddings, extract, search

logger = logging.getLogger(__name__)


async def process_job(job):
    wid, jid = job.workspace_id, job.id
    started = time.monotonic()
    async with get_worker_db_context() as db:
        repo = SupportRepository(db)
        member = await repo.membership(wid, job.actor_id)
        if not member or (job.kind == "ingest" and member.role == "agent"):
            raise ValidationError("Membership no longer permits this operation")
        if job.kind == "ingest":
            doc = await repo.scoped(Document, wid, job.target_id)
            original = await repo.original(wid, doc.id)
            if doc.state not in {"queued", "processing"} or original is None:
                raise ValidationError("Document is no longer available for processing")
            filename = doc.filename
        else:
            case = await repo.scoped(SupportCase, wid, job.target_id)
            workspace = await repo.workspace(wid)
            question, tone, escalation = case.question, workspace.tone, workspace.escalation
            sources = await search(repo, wid, question)
    usage = {}
    if job.kind == "ingest":
        chunks = await extract(filename, original)
        vectors = await embeddings([c["text"] for c in chunks])
    else:
        answer, usage = await generate_answer(question, sources, tone, escalation)
    # Recheck authorization and source state after external work, before publishing.
    async with get_worker_db_context() as db:
        repo = SupportRepository(db)
        await repo.workspace(wid, lock=True)
        current = await repo.scoped(SupportJob, wid, jid, lock=True)
        if current.state != "processing":
            return
        member = await repo.membership(wid, job.actor_id)
        if not member or (job.kind == "ingest" and member.role == "agent"):
            raise ValidationError("Membership changed during processing")
        if job.kind == "ingest":
            doc = await repo.scoped(Document, wid, job.target_id, lock=True)
            if doc.state not in {"queued", "processing"}:
                raise ValidationError("Document was archived or deleted")
            existing = await repo.chunks(wid)
            if len(existing) + len(chunks) > 5000:
                raise ValidationError("Workspace exceeds the 5,000-chunk pilot search limit")
            await repo.purge_chunks(wid, doc.id)
            for chunk, vector in zip(chunks, vectors, strict=True):
                await repo.add(
                    Chunk(workspace_id=wid, document_id=doc.id, embedding=vector, **chunk)
                )
            if doc.replaces_id:
                old = await repo.scoped(Document, wid, doc.replaces_id, lock=True)
                if old.state != "ready":
                    raise ValidationError("The previous document is no longer current")
                old.state = "archived"
            doc.state, doc.error = "ready", None
            doc.embedding_model = (
                settings.SUPPORT_EMBEDDING_MODEL if settings.SUPPORT_EMBEDDINGS_ENABLED else None
            )
        else:
            cited = []
            for source in sources:
                doc = await repo.scoped(Document, wid, UUID(source["document_id"]))
                if doc.state != "ready":
                    raise ValidationError(
                        "Knowledge changed during generation; retry with current sources"
                    )
                if UUID(source["id"]) in answer.citation_ids:
                    cited.append({k: v for k, v in source.items() if k != "text"})
            await repo.add(
                Draft(
                    workspace_id=wid,
                    case_id=job.target_id,
                    reply=answer.reply,
                    outcome=answer.outcome,
                    citations=cited,
                )
            )
        current.state, current.error = "completed", None
        current.usage = {**usage, "duration_ms": round((time.monotonic() - started) * 1000)}
        await repo.audit(wid, job.actor_id, job.kind + ".completed", job.target_id)


async def run_once():
    async with get_worker_db_context() as db:
        job = await SupportRepository(db).claim()
    if job is None:
        return False
    try:
        await asyncio.wait_for(run_cancellable_job(job), timeout=240)
    except Exception as exc:
        # Provider responses may contain sensitive text; never log their raw body.
        message = (
            exc.message
            if isinstance(exc, ValidationError)
            else "Processing failed. Check provider configuration and worker health, then retry."
        )
        async with get_worker_db_context() as db:
            repo = SupportRepository(db)
            current = await repo.scoped(SupportJob, job.workspace_id, job.id, lock=True)
            if current.state == "processing":
                current.state, current.error = "failed", message
                if current.kind == "ingest":
                    doc = await repo.scoped(Document, job.workspace_id, job.target_id)
                    if doc.state == "queued":
                        doc.state, doc.error = "failed", message
        logger.warning("Support job %s failed (%s)", job.id, type(exc).__name__)
    return True


async def run_cancellable_job(job):
    task = asyncio.create_task(process_job(job))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=2)
            if task.done():
                break
            async with get_worker_db_context() as db:
                try:
                    current = await SupportRepository(db).scoped(
                        SupportJob, job.workspace_id, job.id
                    )
                    if current.state in {"cancelled", "failed"}:
                        task.cancel()
                        break
                except NotFoundError:
                    task.cancel()
                    break
        if not task.cancelled():
            with contextlib.suppress(asyncio.CancelledError):
                await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if not settings.SUPPORT_ENABLED or not await run_once():
                await asyncio.sleep(2)
        except Exception as exc:
            logger.warning("Worker unavailable (%s)", type(exc).__name__)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
