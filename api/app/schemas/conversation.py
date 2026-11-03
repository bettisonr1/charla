"""Request/response shapes for the conversation endpoints and the chat WebSocket."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_SCENARIO_LENGTH = 500
MAX_MESSAGE_LENGTH = 2000


class ConversationCreate(BaseModel):
    scenario: str = Field(min_length=1, max_length=MAX_SCENARIO_LENGTH)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ClientMessage(BaseModel):
    """A frame the browser sends over the chat WebSocket."""

    type: Literal["message"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
