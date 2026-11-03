from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from anthropic.types import MessageParam
from fastapi.testclient import TestClient

from app.llm import get_llm
from app.main import app
from app.models import Conversation, Message
from app.store import get_store


class FakeStore:
    """In-memory Store, so API tests don't need Postgres."""

    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: list[Message] = []

    async def create_conversation(self, scenario: str) -> Conversation:
        conversation = Conversation(id=uuid4(), scenario=scenario, created_at=datetime.now(UTC))
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


class FakeLLM:
    """Replies with canned chunks and records what it was asked."""

    def __init__(self) -> None:
        self.chunks: list[str] = ["Hola, ", "¿qué ", "tal?"]
        self.error: Exception | None = None
        self.calls: list[tuple[str, list[MessageParam]]] = []

    async def stream_reply(self, system: str, messages: list[MessageParam]) -> AsyncIterator[str]:
        self.calls.append((system, list(messages)))
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


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
