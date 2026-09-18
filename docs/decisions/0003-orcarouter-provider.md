# 0003: Optional OrcaRouter provider

- Status: accepted
- Source: https://github.com/vstorm-co/full-stack-ai-agent-template/pull/141
- Reviewed commit: `317922c`

## Decision

Adapt the provider integration to the existing AgentHarbor PydanticAI application. Configure one active provider per deployment using `LLM_PROVIDER=openai` or `LLM_PROVIDER=orcarouter`. Keep the current local OpenAI selection until gateway credentials are supplied. The project generator and other framework templates are outside this adaptation.

The model factory uses `OpenAIResponsesModel` for both providers. OrcaRouter requests go to `https://api.orcarouter.ai/v1` with `ORCAROUTER_API_KEY`; direct OpenAI uses its own endpoint and key. Model names never choose credentials or endpoints. Do not automatically fall back to another provider when a key is absent or a request fails.

Defaults and the existing model-selector endpoint follow the active provider. Explicit `AI_MODEL` and `AI_AVAILABLE_MODELS` configuration wins. Catalog entries are starter choices, not a guarantee of account access or feature support. The readiness probe checks key presence only, without paid requests. Existing memory capability construction and UUID isolation remain shared across providers.

## Operation

Set these values in `my_ai_app/backend/.env`, then restart the backend and refresh the browser:

```dotenv
LLM_PROVIDER=orcarouter
ORCAROUTER_API_KEY=your-key
AI_MODEL=anthropic/claude-sonnet-4.6
```

Update or remove any explicitly configured `AI_AVAILABLE_MODELS` when switching providers. It accepts a JSON array. For OrcaRouter, use gateway model IDs such as `openai/gpt-5.5`; this deployment does not use the PR's all-providers prefix dispatcher. To switch back, set `LLM_PROVIDER=openai`, choose a direct OpenAI model ID, and configure `OPENAI_API_KEY`.

Requests, including any memory included in a model prompt, pass through the selected provider. Server-side keys must never be exposed in frontend environment variables.

## Validation and limits

Regression tests exercise provider defaults, explicit overrides, endpoint/key isolation, missing credentials, readiness, Responses streaming, real memory-tool execution through a simulated HTTP gateway, and HTTP 401 propagation. These tests do not establish that a live OrcaRouter model supports every feature. No live gateway calls were made because no OrcaRouter key was supplied. Before enabling it for users, verify streaming and memory tools with the intended model and account.

No new packages, database migrations or frontend changes are required for this provider integration. The existing transport dependency is reused.
