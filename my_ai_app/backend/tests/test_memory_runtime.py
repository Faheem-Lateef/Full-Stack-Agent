"""Regression coverage for memory outages, scope and streaming compatibility."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic_ai import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app.agents.memory import build_memory_capability
from app.core.config import settings
from app.db import memory_pool
from app.services.agent_session import AgentSession


@pytest.mark.anyio
async def test_failed_connection_cools_down_after_completion(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_pool, "_memory_pool", None)
    monkeypatch.setattr(memory_pool, "_memory_store", None)
    monkeypatch.setattr(memory_pool, "_last_attempt_at", None)
    monkeypatch.setattr(memory_pool, "_init_lock", asyncio.Lock())
    clock = [0.0]
    monkeypatch.setattr(memory_pool.time, "monotonic", lambda: clock[0])
    started, release = asyncio.Event(), asyncio.Event()

    async def failed_connect(*args, **kwargs):
        assert kwargs["timeout"] == 5
        assert kwargs["ssl"] == settings.POSTGRES_SSL_MODE
        started.set()
        await release.wait()
        clock[0] = 20.0
        raise OSError("database unavailable")

    connect = AsyncMock(side_effect=failed_connect)
    monkeypatch.setattr(memory_pool.asyncpg, "create_pool", connect)
    first = asyncio.create_task(memory_pool.get_memory_store())
    await started.wait()
    clock[0] = 15.0
    queued = [asyncio.create_task(memory_pool.get_memory_store()) for _ in range(4)]
    release.set()
    assert await asyncio.gather(first, *queued) == [None] * 5
    assert connect.await_count == 1
    assert memory_pool._last_attempt_at == 20.0
    clock[0] = 25.0
    assert await memory_pool.get_memory_store() is None
    assert connect.await_count == 1
    clock[0] = 31.0
    await memory_pool.get_memory_store()
    assert connect.await_count == 2


@pytest.mark.anyio
@pytest.mark.parametrize("user_id", [None, "", "../other", "not-a-user"])
async def test_userless_or_invalid_scope_never_opens_store(monkeypatch, user_id):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    with patch("app.agents.memory.get_memory_store", new_callable=AsyncMock) as store:
        assert await build_memory_capability(user_id) is None
        store.assert_not_awaited()


@pytest.mark.anyio
async def test_streamed_tool_result_uses_pydantic_ai_v2_part():
    websocket = MagicMock()
    user = MagicMock(id=uuid4())
    session = AgentSession(websocket, user)
    assert session.deps.user_id == str(user.id)

    async def events():
        yield FunctionToolCallEvent(
            part=ToolCallPart("read_memory", {"filename": "MEMORY.md"}, "call-1")
        )
        yield FunctionToolResultEvent(
            part=ToolReturnPart("read_memory", "Saved preference", "call-1")
        )

    collected = []
    with patch("app.services.agent_session.send_event", new_callable=AsyncMock) as send:
        await session._stream_tool_events(events(), collected)
    assert collected[0]["result"] == "Saved preference"
    assert send.await_args.args[1:] == (
        "tool_result",
        {"tool_call_id": "call-1", "content": "Saved preference"},
    )


def test_autogeneration_preserves_memory_tables():
    from app.db.migration_filters import MEMORY_TABLES, include_migration_object

    for name in MEMORY_TABLES:
        assert not include_migration_object(None, name, "table", True, None)
    assert include_migration_object(None, "users", "table", True, None)


@pytest.mark.anyio
async def test_agent_can_recall_scoped_memory_without_provider(monkeypatch):
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai_harness.memory import InMemoryStore

    from app.agents.assistant import AssistantAgent, Deps
    from app.agents.memory import memory_scope_prefix

    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    store = InMemoryStore()
    user_a, user_b = str(uuid4()), str(uuid4())
    await store.write(
        memory_scope_prefix(user_a) + "MEMORY.md", "Prefers concise answers", expected_version=None
    )
    await store.write(
        memory_scope_prefix(user_b) + "MEMORY.md", "Other user private note", expected_version=None
    )

    def model(messages, info):
        assert "Other user private note" not in str(messages)
        assert "read_memory" in {tool.name for tool in info.function_tools}
        results = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if results:
            return ModelResponse(parts=[TextPart(str(results[-1].content))])
        return ModelResponse(parts=[ToolCallPart("read_memory", {"file": "MEMORY.md"}, "recall-1")])

    with patch("app.agents.memory.get_memory_store", new_callable=AsyncMock, return_value=store):
        capability = await build_memory_capability(user_a)
    with patch("app.agents.assistant._build_model", return_value=FunctionModel(model)):
        assistant = AssistantAgent(memory_capability=capability, thinking_effort="")
        output, events, _ = await assistant.run("What do you remember?", deps=Deps(user_id=user_a))
    assert "Prefers concise answers" in output
    assert any(isinstance(event, ToolReturnPart) for event in events)
