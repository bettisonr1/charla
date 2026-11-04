"""The model call, behind a small interface so tests (and, later, other backends) can swap it."""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from app.config import settings
from app.prompts import CORRECTION_SYSTEM_PROMPT, build_correction_user_message
from app.schemas.correction import CorrectionReport

log = structlog.get_logger()

MAX_TOKENS = 600
CORRECTION_MAX_TOKENS = 1000
CORRECTION_TOOL = "report_corrections"


class LLMUnavailableError(Exception):
    """The model can't be called (for example, no API key is configured)."""


class LLM(Protocol):
    def stream_reply(self, system: str, messages: list[MessageParam]) -> AsyncIterator[str]:
        """Yield the agent's reply as it is generated."""
        ...

    async def correct(
        self, message: str, context: str | None = None, model: str | None = None
    ) -> CorrectionReport:
        """Review a learner message and return the errors found (possibly none)."""
        ...


class AnthropicLLM:
    def __init__(self) -> None:
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        if not settings.anthropic_api_key:
            raise LLMUnavailableError("ANTHROPIC_API_KEY is not set. Add it to api/.env.")
        if self._client is None:
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def stream_reply(self, system: str, messages: list[MessageParam]) -> AsyncIterator[str]:
        client = self._get_client()
        log.info("llm_call", model=settings.anthropic_model, turns=len(messages))
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def correct(
        self, message: str, context: str | None = None, model: str | None = None
    ) -> CorrectionReport:
        client = self._get_client()
        model = model or settings.anthropic_model
        log.info("llm_correct", model=model, message_length=len(message))
        response = await client.messages.create(
            model=model,
            max_tokens=CORRECTION_MAX_TOKENS,
            system=CORRECTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_correction_user_message(message, context)}],
            tools=[
                {
                    "name": CORRECTION_TOOL,
                    "description": "Report the errors found in the learner's message.",
                    "input_schema": CorrectionReport.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": CORRECTION_TOOL},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == CORRECTION_TOOL:
                return CorrectionReport.model_validate(block.input)
        raise ValueError("model returned no correction report")


@lru_cache
def get_llm() -> LLM:
    return AnthropicLLM()
