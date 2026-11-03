"""The model call, behind a small interface so tests (and, later, other backends) can swap it."""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from app.config import settings

log = structlog.get_logger()

MAX_TOKENS = 600


class LLMUnavailableError(Exception):
    """The model can't be called (for example, no API key is configured)."""


class LLM(Protocol):
    def stream_reply(self, system: str, messages: list[MessageParam]) -> AsyncIterator[str]:
        """Yield the agent's reply as it is generated."""
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


@lru_cache
def get_llm() -> LLM:
    return AnthropicLLM()
