"""Provider routing and Responses transport tests; no external requests."""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai_harness.memory import InMemoryStore

from app.agents.assistant import AssistantAgent, Deps, _build_model
from app.agents.memory import build_memory_capability, memory_scope_prefix
from app.core.config import Settings, settings


@pytest.fixture
def clean_config(monkeypatch):
    for key in ("AI_MODEL", "AI_AVAILABLE_MODELS", "LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


def test_orcarouter_defaults(clean_config):
    config = Settings(_env_file=None, LLM_PROVIDER="orcarouter")
    assert config.AI_MODEL == "anthropic/claude-sonnet-4.6"
    assert "openai/gpt-5.5" in config.AI_AVAILABLE_MODELS


def test_explicit_models_are_preserved(clean_config):
    config = Settings(
        _env_file=None,
        LLM_PROVIDER="orcarouter",
        AI_MODEL="vendor/custom",
        AI_AVAILABLE_MODELS=["vendor/other"],
    )
    assert config.AI_MODEL == "vendor/custom"
    assert config.AI_AVAILABLE_MODELS == ["vendor/custom", "vendor/other"]


def test_unknown_provider_rejected(clean_config):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, LLM_PROVIDER="unknown")


@pytest.mark.parametrize(
    "provider,key_field", [("openai", "OPENAI_API_KEY"), ("orcarouter", "ORCAROUTER_API_KEY")]
)
def test_missing_selected_key_does_not_fall_back(monkeypatch, provider, key_field):
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "other-key")
    monkeypatch.setattr(settings, "ORCAROUTER_API_KEY", "other-key")
    monkeypatch.setattr(settings, key_field, "")
    with pytest.raises(ValueError, match=key_field):
        _build_model("some-model")


@pytest.mark.parametrize(
    "provider,host", [("openai", "api.openai.com"), ("orcarouter", "api.orcarouter.ai")]
)
def test_factory_routes_credentials_by_server_configuration(monkeypatch, provider, host):
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(settings, "ORCAROUTER_API_KEY", "test-orcarouter")
    # A namespaced gateway model must not cause direct OpenAI credential use.
    model = _build_model("openai/gpt-5.5" if provider == "orcarouter" else "gpt-5.5")
    assert model.client.base_url.host == host
    assert model.client.api_key == f"test-{provider}"


@pytest.mark.anyio
@pytest.mark.parametrize("key,expected", [("", "unhealthy"), ("test-orca", "healthy")])
async def test_readiness_checks_gateway_key(client, monkeypatch, key, expected):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "orcarouter")
    monkeypatch.setattr(settings, "ORCAROUTER_API_KEY", key)
    response = await client.get("/api/v1/health/ready")
    assert response.json()["checks"]["llm"]["provider"] == "orcarouter"
    assert response.json()["checks"]["llm"]["status"] == expected
    assert "test-orca" not in response.text


def response_body(output):
    return {
        "id": "resp-test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "anthropic/claude-sonnet-4.6",
        "output": output,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def message(text):
    return {
        "id": "msg-test",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


@pytest.fixture
def gateway_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "orcarouter")
    monkeypatch.setattr(settings, "ORCAROUTER_API_KEY", "test-orca")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "must-not-be-sent")
    monkeypatch.setattr(settings, "AI_MODEL", "anthropic/claude-sonnet-4.6")


@pytest.mark.anyio
async def test_gateway_transport_executes_memory_tool(gateway_settings, monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    store = InMemoryStore()
    uid = str(uuid4())
    await store.write(
        memory_scope_prefix(uid) + "MEMORY.md", "Prefers concise answers", expected_version=None
    )
    calls = []

    def handler(request):
        assert str(request.url) == "https://api.orcarouter.ai/v1/responses"
        assert request.headers["authorization"] == "Bearer test-orca"
        payload = json.loads(request.content)
        assert payload["model"] == "anthropic/claude-sonnet-4.6"
        calls.append(payload)
        if len(calls) == 1:
            assert "read_memory" in {tool["name"] for tool in payload["tools"]}
            output = [
                {
                    "id": "fc-test",
                    "type": "function_call",
                    "call_id": "call-test",
                    "name": "read_memory",
                    "arguments": json.dumps({"file": "MEMORY.md"}),
                    "status": "completed",
                }
            ]
        else:
            assert "Prefers concise answers" in json.dumps(payload["input"])
            output = [message("You prefer concise answers.")]
        return httpx.Response(200, json=response_body(output))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch(
            "app.agents.memory.get_memory_store", new_callable=AsyncMock, return_value=store
        ):
            memory = await build_memory_capability(uid)
        with patch(
            "app.agents.assistant.OpenAIProvider",
            side_effect=lambda **kwargs: OpenAIProvider(**kwargs, http_client=client),
        ):
            assistant = AssistantAgent(memory_capability=memory, thinking_effort="")
            output, _, _ = await assistant.run("Recall my preferences", deps=Deps(user_id=uid))
    assert len(calls) == 2
    assert output == "You prefer concise answers."


@pytest.mark.anyio
async def test_gateway_streaming(gateway_settings):
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        body = response_body([message("Hello")])
        events = [
            {
                "type": "response.created",
                "response": {**body, "output": [], "status": "in_progress"},
            },
            {"type": "response.output_item.added", "output_index": 0, "item": message("")},
            {
                "type": "response.content_part.added",
                "output_index": 0,
                "content_index": 0,
                "item_id": "msg-test",
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "content_index": 0,
                "item_id": "msg-test",
                "delta": "Hello",
            },
            {"type": "response.completed", "response": body},
        ]
        data = "".join(
            f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': i})}\n\n"
            for i, event in enumerate(events)
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch(
            "app.agents.assistant.OpenAIProvider",
            side_effect=lambda **kwargs: OpenAIProvider(**kwargs, http_client=client),
        ):
            assistant = AssistantAgent(thinking_effort="")
            async with assistant.agent.run_stream("Hello", deps=Deps()) as result:
                chunks = [chunk async for chunk in result.stream_text(delta=True)]
    assert "".join(chunks) == "Hello"


@pytest.mark.anyio
async def test_gateway_auth_failure_is_not_hidden(gateway_settings):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401, json={"error": {"message": "Invalid key", "type": "authentication_error"}}
            )
        )
    ) as client:
        with patch(
            "app.agents.assistant.OpenAIProvider",
            side_effect=lambda **kwargs: OpenAIProvider(**kwargs, http_client=client),
        ), pytest.raises(ModelHTTPError) as exc:
            await AssistantAgent(thinking_effort="").run("Hello")
    assert exc.value.status_code == 401
