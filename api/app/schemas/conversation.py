"""Request/response shapes for the conversation endpoints and the chat WebSocket."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.correction import ErrorCategory, LocatedCorrection

MAX_SCENARIO_LENGTH = 500
MAX_MESSAGE_LENGTH = 2000


class ConversationCreate(BaseModel):
    scenario: str = Field(min_length=1, max_length=MAX_SCENARIO_LENGTH)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    # None: not checked, or the check failed. []: checked and clean.
    corrections: list[LocatedCorrection] | None = None
    created_at: datetime

    @field_validator("corrections", mode="before")
    @classmethod
    def _unwrap_stored(cls, value: Any) -> Any:
        # The column holds {"corrections": [...]}; the API serves the bare list.
        if isinstance(value, dict):
            return value.get("corrections", [])
        return value


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario: str
    created_at: datetime
    ended_at: datetime | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ClientMessage(BaseModel):
    """A frame the browser sends over the chat WebSocket."""

    type: Literal["message"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class SummaryExample(BaseModel):
    sentence: str  # the learner's whole message
    original: str  # the flagged fragment
    corrected: str  # the fragment, fixed
    corrected_sentence: str  # the whole message with the fix applied
    explanation: str


class SummaryGroup(BaseModel):
    category: ErrorCategory
    count: int
    examples: list[SummaryExample]


class ConversationSummary(BaseModel):
    conversation_id: UUID
    ended_at: datetime | None
    messages_sent: int
    total_corrections: int
    groups: list[SummaryGroup]
