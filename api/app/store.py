"""Persistence for conversations, behind an interface so tests can run without Postgres."""

from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Conversation, Message

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


class SqlStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        return await self._session.get(Conversation, conversation_id)

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


async def get_store(session: Annotated[AsyncSession, Depends(get_session)]) -> Store:
    return SqlStore(session)
