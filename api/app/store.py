"""Persistence for conversations, behind an interface so tests can run without Postgres."""

from datetime import UTC, datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import SessionLocal, get_session
from app.models import Conversation, Message
from app.schemas.correction import StoredCorrections

LIST_LIMIT = 50


class Store(Protocol):
    async def create_conversation(self, scenario: str) -> Conversation: ...

    async def list_conversations(self) -> list[Conversation]:
        """Most recent first."""
        ...

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None: ...

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        """Oldest first."""
        ...

    async def add_message(self, conversation_id: UUID, role: str, content: str) -> Message: ...

    async def save_corrections(self, message_id: UUID, corrections: StoredCorrections) -> None:
        """Write a message's corrections. Safe to call from a background task: it must not share
        the request's database session."""
        ...

    async def end_conversation(self, conversation_id: UUID) -> Conversation | None:
        """Mark the conversation ended (idempotent: the first end time is kept)."""
        ...


class SqlStore:
    def __init__(
        self, session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session = session
        self._session_factory = session_factory

    async def create_conversation(self, scenario: str) -> Conversation:
        conversation = Conversation(scenario=scenario)
        self._session.add(conversation)
        await self._session.commit()
        await self._session.refresh(conversation)
        return conversation

    async def list_conversations(self) -> list[Conversation]:
        result = await self._session.scalars(
            select(Conversation).order_by(Conversation.created_at.desc()).limit(LIST_LIMIT)
        )
        return list(result)

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        # populate_existing: the long-lived WebSocket session must see `ended_at` set elsewhere.
        return await self._session.get(Conversation, conversation_id, populate_existing=True)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        result = await self._session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result)

    async def add_message(self, conversation_id: UUID, role: str, content: str) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def save_corrections(self, message_id: UUID, corrections: StoredCorrections) -> None:
        # Its own short-lived session: this runs concurrently with the reply, and an AsyncSession
        # must not be used by two tasks at once.
        async with self._session_factory() as session:
            message = await session.get(Message, message_id)
            if message is None:
                return
            message.corrections = corrections.model_dump(mode="json")
            await session.commit()

    async def end_conversation(self, conversation_id: UUID) -> Conversation | None:
        conversation = await self.get_conversation(conversation_id)
        if conversation is not None and conversation.ended_at is None:
            conversation.ended_at = datetime.now(UTC)
            await self._session.commit()
            await self._session.refresh(conversation)
        return conversation


async def get_store(session: Annotated[AsyncSession, Depends(get_session)]) -> Store:
    return SqlStore(session, SessionLocal)
