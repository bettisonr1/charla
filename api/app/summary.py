"""The end-of-conversation summary. Deterministic: built from stored corrections, no LLM."""

from collections import defaultdict
from collections.abc import Sequence

from app.models import Conversation, Message
from app.schemas.conversation import (
    ConversationSummary,
    SummaryExample,
    SummaryGroup,
)
from app.schemas.correction import ErrorCategory, StoredCorrections


def build_summary(conversation: Conversation, messages: Sequence[Message]) -> ConversationSummary:
    by_category: dict[ErrorCategory, list[SummaryExample]] = defaultdict(list)
    user_messages = [m for m in messages if m.role == "user"]
    for m in user_messages:
        if not m.corrections:
            continue
        for c in StoredCorrections.model_validate(m.corrections).corrections:
            by_category[c.category].append(
                SummaryExample(
                    sentence=m.content,
                    original=c.original,
                    corrected=c.corrected,
                    corrected_sentence=m.content[: c.start] + c.corrected + m.content[c.end :],
                    explanation=c.explanation,
                )
            )
    # Most frequent first; ties keep the order mistakes were made in (sorted() is stable).
    groups = [
        SummaryGroup(category=cat, count=len(examples), examples=examples)
        for cat, examples in sorted(by_category.items(), key=lambda kv: -len(kv[1]))
    ]
    return ConversationSummary(
        conversation_id=conversation.id,
        ended_at=conversation.ended_at,
        messages_sent=len(user_messages),
        total_corrections=sum(g.count for g in groups),
        groups=groups,
    )
