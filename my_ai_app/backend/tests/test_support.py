"""Support policy tests. PostgreSQL integration is explicit and rolls back all writes."""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_ai.models.test import TestModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.agents import support as support_agent
from app.agents.support import validate_answer
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.db.models.support import Document, Draft, Invitation, SupportJob
from app.db.models.user import User
from app.db.session import get_db_session
from app.main import app
from app.schemas.support import DraftInput, InviteInput, SupportAnswer, WorkspaceInput
from app.services.knowledge import cosine, extract, rank_chunks, split_pages
from app.services.support import SupportService
from app.worker import support as worker


def test_chunks_preserve_page_and_overlap():
    parts = split_pages(["refund " * 800, "Shipping takes three days"])
    assert [c["page"] for c in parts] == [1, 1, 2]
    assert len(parts[0]["text"].split()) == 480
    assert parts[2]["ordinal"] == 2


def test_empty_documents_fail():
    with pytest.raises(ValidationError, match="No readable text"):
        split_pages(["  "])


def test_retrieval_and_no_match():
    chunk = SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        page=2,
        text="Refund requests must arrive within fourteen days",
        embedding=None,
    )
    assert rank_chunks([(chunk, "Policy")], "refund")[0]["page"] == 2
    assert rank_chunks([(chunk, "Policy")], "unicorn") == []
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1], [1, 2]) == 0


def test_citations_cannot_be_invented():
    with pytest.raises(ValidationError, match="invalid source"):
        validate_answer(
            SupportAnswer(outcome="answerable", reply="A reply", citation_ids=[uuid4()]), []
        )
    with pytest.raises(ValidationError, match="must cite"):
        validate_answer(SupportAnswer(outcome="answerable", reply="A reply"), [])
    assert (
        validate_answer(
            SupportAnswer(outcome="insufficient_evidence", reply="Please clarify"), []
        ).outcome
        == "insufficient_evidence"
    )


@pytest.mark.anyio
async def test_native_text_parser():
    result = await extract("policy.txt", b"Refunds are reviewed within fourteen days.")
    assert result[0]["page"] == 1
    assert "fourteen" in result[0]["text"]
    with pytest.raises(ValidationError):
        await extract("bad.pdf", b"%PDF- broken")


@pytest.fixture
async def support_db():
    if os.getenv("RUN_SUPPORT_DB_TESTS") != "1":
        pytest.skip("Set RUN_SUPPORT_DB_TESTS=1 for rollback-only local PostgreSQL checks")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def setup_support(support_db):
    svc = SupportService(support_db)
    owner = await svc.repo.add(
        User(email=f"support-test-{uuid4()}@example.com", full_name="Support Test")
    )
    outsider = await svc.repo.add(
        User(email=f"support-test-{uuid4()}@example.com", role="admin", is_app_admin=True)
    )
    workspace = await svc.create_workspace(owner, WorkspaceInput(name="Isolation test"))
    return svc, owner, outsider, workspace


@pytest.mark.anyio
async def test_global_admin_has_no_workspace_access(setup_support):
    svc, _, outsider, w = setup_support
    with pytest.raises(NotFoundError):
        await svc.authorize(w.id, outsider)
    assert await svc.repo.workspaces(outsider.id) == []


@pytest.mark.anyio
async def test_invitations_are_email_bound_and_single_use(setup_support):
    svc, owner, outsider, w = setup_support
    invitation = await svc.invite(w.id, owner, InviteInput(email=outsider.email))
    with pytest.raises(AuthorizationError):
        await svc.accept(owner, invitation["token"])
    result = await svc.accept(outsider, invitation["token"])
    assert result["workspace_id"] == w.id
    with pytest.raises(ValidationError):
        await svc.accept(outsider, invitation["token"])
    with pytest.raises(AuthorizationError):
        await svc.upload(w.id, outsider, "test.txt", b"Text")
    with pytest.raises(ValidationError, match="retain an owner"):
        await svc.change_member(w.id, owner, owner.id, "agent")


@pytest.mark.anyio
async def test_expired_invitation(setup_support):
    svc, owner, outsider, w = setup_support
    invitation = await svc.invite(w.id, owner, InviteInput(email=outsider.email))
    row = await svc.repo.scoped(Invitation, w.id, invitation["id"])
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        await svc.accept(outsider, invitation["token"])


@pytest.mark.anyio
async def test_upload_limits_and_scoped_sources(setup_support):
    svc, owner, outsider, w = setup_support
    with pytest.raises(ValidationError):
        await svc.upload(w.id, owner, "bad.exe", b"data")
    with pytest.raises(ValidationError):
        await svc.upload(w.id, owner, "bad.txt", b"\x00data")
    doc = await svc.upload(w.id, owner, "policy.txt", b"Refunds take fourteen days")
    assert doc.original and doc.state == "queued"
    assert (await svc.repo.usage(w.id))["documents"] == 1
    other = await svc.create_workspace(outsider, WorkspaceInput(name="Other"))
    with pytest.raises(NotFoundError):
        await svc.repo.scoped(Document, other.id, doc.id)
    assert await svc.repo.chunks(other.id) == []


@pytest.mark.anyio
async def test_draft_conflict_approval_and_deleted_source(setup_support):
    svc, owner, _, w = setup_support
    doc = await svc.upload(w.id, owner, "policy.txt", b"Policy text")
    doc.state = "ready"
    case = await svc.create_case(w.id, owner, "What is the policy?")
    draft = await svc.repo.add(
        Draft(
            workspace_id=w.id,
            case_id=case.id,
            reply="Original",
            outcome="answerable",
            citations=[{"id": str(uuid4()), "document_id": str(doc.id)}],
        )
    )
    await svc.approve(w.id, owner, draft.id, 1)
    await svc.edit_draft(w.id, owner, draft.id, DraftInput(version=1, reply="Edited"))
    assert draft.approved_by is None and draft.version == 2
    with pytest.raises(AlreadyExistsError):
        await svc.edit_draft(w.id, owner, draft.id, DraftInput(version=1, reply="Stale"))
    assert draft.reply == "Edited"
    await svc.delete_document(w.id, owner, doc.id)
    assert doc.original is None
    assert draft.citations[0]["unavailable"]
    with pytest.raises(ValidationError):
        await svc.approve(w.id, owner, draft.id, 2)


@pytest.mark.anyio
async def test_duplicate_generation_and_missing_key(setup_support, monkeypatch):
    svc, owner, _, w = setup_support
    case = await svc.create_case(w.id, owner, "What is our refund policy?")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValidationError, match="configure"):
        await svc.generate(w.id, owner, case.id, uuid4())
    # Only queues requests; never calls this deliberately invalid test credential.
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "unit-test-not-a-real-key")
    key = uuid4()
    first = await svc.generate(w.id, owner, case.id, key)
    second = await svc.generate(w.id, owner, case.id, key)
    assert first.id == second.id
    assert (await svc.repo.usage(w.id))["generations_this_month"] == 1


@pytest.mark.anyio
async def test_routes_deny_cross_workspace_ids(setup_support, support_db, monkeypatch):
    svc, owner, outsider, w = setup_support
    document = await svc.upload(w.id, owner, "policy.txt", b"Private policy")
    monkeypatch.setattr(settings, "SUPPORT_ENABLED", True)

    async def database():
        yield support_db

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_current_user] = lambda: outsider
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ["knowledge", "members", "usage", "support/cases", "jobs"]:
                assert (await client.get(f"/api/v1/workspaces/{w.id}/{path}")).status_code == 404
            assert (
                await client.delete(f"/api/v1/workspaces/{w.id}/knowledge/{document.id}")
            ).status_code == 404
            app.dependency_overrides[get_current_user] = lambda: owner
            response = await client.get(f"/api/v1/workspaces/{w.id}/knowledge")
            assert response.status_code == 200
            assert "original" not in response.json()[0]
            case = await svc.create_case(w.id, owner, "What is the policy?")
            draft = await svc.repo.add(
                Draft(
                    workspace_id=w.id,
                    case_id=case.id,
                    reply="Review required",
                    outcome="insufficient_evidence",
                )
            )
            response = await client.patch(
                f"/api/v1/workspaces/{w.id}/support/drafts/{draft.id}",
                json={"reply": "Edited for review", "version": 1},
            )
            assert response.status_code == 200
            assert response.json()["version"] == 2
            assert response.json()["updated_at"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_worker_indexes_then_publishes_cited_draft(setup_support, support_db, monkeypatch):
    svc, owner, _, w = setup_support
    monkeypatch.setattr(settings, "SUPPORT_EMBEDDINGS_ENABLED", False)

    @asynccontextmanager
    async def context():
        yield support_db
        await support_db.flush()

    monkeypatch.setattr(worker, "get_worker_db_context", context)
    doc = await svc.upload(
        w.id, owner, "refund.txt", b"Refund requests are reviewed within fourteen days."
    )
    job = (await svc.repo.listing(SupportJob, w.id))[0]
    job.state = "processing"
    await worker.process_job(job)
    assert doc.state == "ready"
    chunks = await svc.repo.chunks(w.id)
    assert len(chunks) == 1
    case = await svc.create_case(w.id, owner, "How are refund requests reviewed?")
    generation = await svc.repo.add(
        SupportJob(
            workspace_id=w.id,
            actor_id=owner.id,
            kind="generate",
            target_id=case.id,
            request_key=str(uuid4()),
            state="processing",
        )
    )

    async def answer(question, sources, tone, escalation):
        assert sources[0]["document_id"] == str(doc.id)
        return SupportAnswer(
            outcome="answerable", reply="Within fourteen days.", citation_ids=[sources[0]["id"]]
        ), {"input_tokens": 20}

    monkeypatch.setattr(worker, "generate_answer", answer)
    await worker.process_job(generation)
    drafts = await svc.repo.case_drafts(w.id, case.id)
    assert len(drafts) == 1
    assert drafts[0].citations[0]["document_id"] == str(doc.id)
    assert generation.state == "completed"


@pytest.mark.anyio
async def test_worker_does_not_publish_cancelled_or_deleted_sources(
    setup_support, support_db, monkeypatch
):
    svc, owner, _, w = setup_support

    @asynccontextmanager
    async def context():
        yield support_db
        await support_db.flush()

    monkeypatch.setattr(worker, "get_worker_db_context", context)
    monkeypatch.setattr(settings, "SUPPORT_EMBEDDINGS_ENABLED", False)
    doc = await svc.upload(
        w.id, owner, "refund.txt", b"Refunds are considered within fourteen days."
    )
    job = (await svc.repo.listing(SupportJob, w.id))[0]
    job.state = "processing"
    await worker.process_job(job)
    case = await svc.create_case(w.id, owner, "What is the refund policy?")
    generation = await svc.repo.add(
        SupportJob(
            workspace_id=w.id,
            actor_id=owner.id,
            kind="generate",
            target_id=case.id,
            request_key=str(uuid4()),
            state="processing",
        )
    )

    async def deleted_during_generation(question, sources, tone, escalation):
        await svc.delete_document(w.id, owner, doc.id)
        return SupportAnswer(
            outcome="answerable", reply="Reply", citation_ids=[sources[0]["id"]]
        ), {}

    monkeypatch.setattr(worker, "generate_answer", deleted_during_generation)
    with pytest.raises(ValidationError, match="Knowledge changed"):
        await worker.process_job(generation)
    assert await svc.repo.case_drafts(w.id, case.id) == []


@pytest.mark.anyio
async def test_owner_transfer_and_member_removal_cancel_jobs(setup_support):
    svc, owner, outsider, w = setup_support
    invitation = await svc.invite(w.id, owner, InviteInput(email=outsider.email))
    await svc.accept(outsider, invitation["token"])
    await svc.change_member(w.id, owner, outsider.id, "owner")
    job = await svc.repo.add(
        SupportJob(
            workspace_id=w.id,
            actor_id=owner.id,
            kind="generate",
            target_id=uuid4(),
            request_key=str(uuid4()),
        )
    )
    await svc.change_member(w.id, outsider, owner.id)
    assert job.state == "cancelled"
    with pytest.raises(NotFoundError):
        await svc.authorize(w.id, owner)


@pytest.mark.anyio
async def test_structured_agent_runs_with_test_model(monkeypatch):
    cid = uuid4()
    model = TestModel(
        custom_output_args={
            "outcome": "answerable",
            "reply": "Fourteen days.",
            "citation_ids": [str(cid)],
        }
    )
    monkeypatch.setattr(support_agent, "_build_model", lambda name: model)
    answer, usage = await support_agent.generate_answer(
        "Refund timeframe?",
        [{"id": str(cid), "text": "Review takes fourteen days"}],
        "Concise",
        "Escalate",
    )
    assert answer.citation_ids == [cid]
    assert usage["prompt_version"] == "support-v1"


@pytest.mark.anyio
async def test_empty_knowledge_does_not_call_provider(monkeypatch):
    def forbidden(name):
        raise AssertionError("No provider call for empty evidence")

    monkeypatch.setattr(support_agent, "_build_model", forbidden)
    answer, usage = await support_agent.generate_answer("Unknown?", [], "Concise", "Escalate")
    assert answer.outcome == "insufficient_evidence"
    assert usage == {}


def test_offline_retrieval_report_does_not_claim_answer_quality():
    from app.evaluations.support import EvaluationCase, score

    did = uuid4()
    chunk = SimpleNamespace(
        id=uuid4(), document_id=did, page=1, text="Refunds take fourteen days", embedding=None
    )
    report = score(
        [(chunk, "Policy")],
        [
            EvaluationCase(question="Refund policy?", expected_document_ids=[did]),
            EvaluationCase(question="Unrelated shipping?", expected_document_ids=[did]),
        ],
    )
    assert report["hit_rate_at_5"] == 0.5
    assert report["live_provider_calls"] == 0
    assert report["answer_quality_assessed"] is False
