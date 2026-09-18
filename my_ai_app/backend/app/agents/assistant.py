import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import (
    ReinjectSystemPrompt,
    Thinking,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.agents.prompts import DEFAULT_SYSTEM_PROMPT
from app.agents.tools.ask_user_tool import MAX_QUESTIONS, QuestionItem, format_answers
from app.agents.utils import get_current_datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_model(model_name: str) -> OpenAIResponsesModel:
    """OpenAI-only deployment."""
    return OpenAIResponsesModel(
        model_name or settings.AI_MODEL,
        provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
    )


AskUserCallback = Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


@dataclass
class Deps:
    """Dependencies passed to tools via RunContext."""

    user_id: str | None = None
    user_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    ask_user: AskUserCallback | None = None


class AssistantAgent:
    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        thinking_effort: str | None = None,
    ):
        self.model_name = model_name or settings.AI_MODEL
        # ``temperature`` stays ``None`` when caller didn't set it — don't fall
        # back to settings.AI_TEMPERATURE here. Reasoning/o-series models
        # (gpt-5.5, o1, …) reject the parameter entirely, so we only forward
        # it to the model when explicitly requested.
        self.temperature = temperature
        self.thinking_effort = (
            thinking_effort
            if thinking_effort is not None
            else (settings.AI_THINKING_EFFORT if settings.AI_THINKING_ENABLED else None)
        )
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._agent: Agent[Deps, str] | None = None

    def _create_agent(self) -> Agent[Deps, str]:
        model = _build_model(self.model_name)

        capabilities: list[Any] = [ReinjectSystemPrompt()]
        if self.thinking_effort:
            capabilities.append(Thinking(effort=self.thinking_effort))  # ty: ignore[invalid-argument-type]

        # The unified ``Thinking()`` capability enables reasoning, but for the
        # OpenAI Responses API it sets only the effort — not the *summary*
        # field that controls whether the model streams reasoning summaries
        # back to the client. Without ``openai_reasoning_summary`` set, the
        # model reasons internally and we never see ThinkingPart events.
        # ``openai_*``-prefixed fields on TypedDict settings are silently
        # ignored by other providers, so this is safe to apply unconditionally.
        model_settings: ModelSettings = ModelSettings()
        if self.temperature is not None:
            model_settings["temperature"] = self.temperature
        if self.thinking_effort:
            model_settings["openai_reasoning_summary"] = "auto"  # type: ignore[typeddict-unknown-key]  # ty: ignore[invalid-key]

        agent = Agent[Deps, str](
            model=model,
            model_settings=model_settings,
            system_prompt=self.system_prompt,
            capabilities=capabilities,
        )

        self._register_tools(agent)

        return agent

    def _register_tools(self, agent: Agent[Deps, str]) -> None:
        @agent.tool_plain
        def current_datetime() -> dict[str, str]:
            """Get the current date and time.

            Use this tool when you need to know the current date or time.
            """
            return get_current_datetime()

        @agent.tool
        async def ask_user(ctx: RunContext[Deps], questions: list[QuestionItem]) -> str:
            """Ask the user one or more questions and wait for their answers.

            Use this when a decision or missing detail would materially change what
            you do next and you can't reasonably assume it. You may pass several
            questions at once — the user answers them one after another and you get
            all the answers back together (good for an intake/setup flow). You can
            also call this again later to follow up on what they said. Prefer
            answering directly when the request is already clear.

            Args:
                questions: The questions to ask. Each has the question text, optional
                    suggested `options`, and `allow_custom` (whether a free-form
                    answer is allowed, default True).

            Returns:
                The user's answers as a Q/A transcript, with skipped questions marked.
            """
            if ctx.deps.ask_user is None:
                return (
                    "User interaction is unavailable here; proceed with a reasonable "
                    "assumption and state it briefly."
                )
            if not questions:
                return "No questions were provided."
            payload = [q.model_dump() for q in questions[:MAX_QUESTIONS]]
            answers = await ctx.deps.ask_user(payload)
            return format_answers(payload, answers)

    @staticmethod
    def _build_model_history(
        history: list[dict[str, str]] | None,
    ) -> list[ModelRequest | ModelResponse]:
        model_history: list[ModelRequest | ModelResponse] = []
        for msg in history or []:
            if msg["role"] == "user":
                model_history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
            elif msg["role"] == "assistant":
                model_history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
            elif msg["role"] == "system":
                model_history.append(ModelRequest(parts=[SystemPromptPart(content=msg["content"])]))
        return model_history

    @property
    def agent(self) -> Agent[Deps, str]:
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    async def run(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        deps: Deps | None = None,
    ) -> tuple[str, list[ToolCallPart | ToolReturnPart], Deps]:
        agent_deps = deps if deps is not None else Deps()

        logger.info("Running agent with user input: %s...", user_input[:100])
        result = await self.agent.run(
            user_input,
            deps=agent_deps,
            message_history=self._build_model_history(history),
        )

        tool_events: list[ToolCallPart | ToolReturnPart] = []
        for message in result.all_messages():
            if hasattr(message, "parts"):
                for part in message.parts:
                    if isinstance(part, (ToolCallPart, ToolReturnPart)):
                        tool_events.append(part)

        logger.info("Agent run complete. Output length: %s chars", len(result.output))

        return result.output, tool_events, agent_deps

    async def iter(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        deps: Deps | None = None,
    ) -> AsyncGenerator[Any, None]:
        agent_deps = deps if deps is not None else Deps()

        async with self.agent.iter(
            user_input,
            deps=agent_deps,
            message_history=self._build_model_history(history),
        ) as run:
            async for event in run:
                yield event


def get_agent(
    model_name: str | None = None,
    thinking_effort: str | None = None,
    temperature: float | None = None,
) -> AssistantAgent:
    return AssistantAgent(
        model_name=model_name,
        thinking_effort=thinking_effort,
        temperature=temperature,
    )


async def run_agent(
    user_input: str,
    history: list[dict[str, str]],
    deps: Deps | None = None,
) -> tuple[str, list[ToolCallPart | ToolReturnPart], Deps]:
    agent = get_agent()
    return await agent.run(user_input, history, deps)
