import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from anthropic.types import MessageParam
from fastapi.testclient import TestClient

from app.llm import get_llm
from app.main import app
from app.models import Conversation, Message
from app.schemas.correction import CorrectionReport, StoredCorrections
from app.store import get_store


class FakeStore:
    """In-memory Store, so API tests don't need Postgres."""

    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: list[Message] = []
        self.fail_saves = False

    async def create_conversation(self, scenario: str) -> Conversation:
        conversation = Conversation(
            id=uuid4(), scenario=scenario, created_at=datetime.now(UTC), ended_at=None
        )
        self.conversations[conversation.id] = conversation
        return conversation

    async def list_conversations(self) -> list[Conversation]:
        return sorted(self.conversations.values(), key=lambda c: c.created_at, reverse=True)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        return [m for m in self.messages if m.conversation_id == conversation_id]

    async def add_message(self, conversation_id: UUID, role: str, content: str) -> Message:
        message = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )
        self.messages.append(message)
        return message

    async def save_corrections(self, message_id: UUID, corrections: StoredCorrections) -> None:
        for m in self.messages:
            if m.id == message_id:
                m.corrections = corrections.model_dump(mode="json")

    async def end_conversation(self, conversation_id: UUID) -> Conversation | None:
        conversation = self.conversations.get(conversation_id)
        if conversation is not None and conversation.ended_at is None:
            conversation.ended_at = datetime.now(UTC)
        return conversation


class FakeLLM:
    """Replies with canned chunks and records what it was asked."""

    def __init__(self) -> None:
        self.chunks: list[str] = ["Hola, ", "¿qué ", "tal?"]
        self.error: Exception | None = None
        self.calls: list[tuple[str, list[MessageParam]]] = []
        self.report = CorrectionReport()
        self.correct_error: Exception | None = None
        self.correct_gate: asyncio.Event | None = None  # set to hold corrections back
        self.correct_calls: list[tuple[str, str | None]] = []

    async def stream_reply(self, system: str, messages: list[MessageParam]) -> AsyncIterator[str]:
        self.calls.append((system, list(messages)))
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk

    async def correct(self, message: str, context: str | None = None) -> CorrectionReport:
        self.correct_calls.append((message, context))
        if self.correct_gate is not None:
            await self.correct_gate.wait()
        if self.correct_error is not None:
            raise self.correct_error
        return self.report


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(store: FakeStore, llm: FakeLLM) -> Iterator[TestClient]:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: llm
    yield TestClient(app)
    app.dependency_overrides.clear()
