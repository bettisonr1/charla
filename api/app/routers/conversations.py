"""Conversation endpoints: create/list/get over HTTP, and the chat itself over a WebSocket.

WebSocket protocol (JSON text frames):

  client -> server   {"type": "message", "content": "<the learner's text>"}
  server -> client   {"type": "user_message_saved", "id": "<message id>"}
                     {"type": "corrections", "message_id": "<id>", "corrections": [<located>]}
                     {"type": "token", "text": "<next chunk of the agent's reply>"}
                     {"type": "message_done", "id": "<message id>", "content": "<full reply>"}
                     {"type": "error", "detail": "<what went wrong>"}

On connect, the server replies first if the agent has not spoken yet (a new conversation) or if
the last stored message is the learner's and has no reply (an interrupted turn), unless the
conversation has ended. Corrections arrive whenever the separate correction call finishes, never
blocking the reply; a failed correction call sends nothing. After the conversation is ended, every
message gets an error event. Closing code 4404 means the conversation does not exist.
"""

import json
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app import pending
from app.corrections import check_message, normalize
from app.llm import LLM, LLMUnavailableError, get_llm
from app.models import Conversation
from app.prompts import build_system_prompt, to_api_messages
from app.schemas.conversation import (
    ClientMessage,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationSummary,
    MessageOut,
)
from app.schemas.correction import StoredCorrections
from app.store import Store, get_store
from app.summary import build_summary

log = structlog.get_logger()

router = APIRouter(prefix="/conversations", tags=["conversations"])

StoreDep = Annotated[Store, Depends(get_store)]
LLMDep = Annotated[LLM, Depends(get_llm)]

CLOSE_NOT_FOUND = 4404
# How long ending a conversation waits for corrections still in flight before summarising.
SUMMARY_WAIT_SECONDS = 5.0


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreate, store: StoreDep) -> Conversation:
    conversation = await store.create_conversation(body.scenario.strip())
    log.info(
        "conversation_created",
        conversation_id=str(conversation.id),
        scenario_length=len(conversation.scenario),
    )
    return conversation


@router.get("", response_model=list[ConversationOut])
async def list_conversations(store: StoreDep) -> list[Conversation]:
    return await store.list_conversations()


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: UUID, store: StoreDep) -> ConversationDetail:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await store.list_messages(conversation_id)
    return ConversationDetail(
        id=conversation.id,
        scenario=conversation.scenario,
        created_at=conversation.created_at,
        ended_at=conversation.ended_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.post("/{conversation_id}/end", response_model=ConversationOut)
async def end_conversation(conversation_id: UUID, store: StoreDep) -> Conversation:
    """End the conversation for good: the chat becomes read-only and the summary is final."""
    conversation = await store.end_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    log.info("conversation_ended", conversation_id=str(conversation_id))
    return conversation


@router.get("/{conversation_id}/summary", response_model=ConversationSummary)
async def get_summary(conversation_id: UUID, store: StoreDep) -> ConversationSummary:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.ended_at is None:
        raise HTTPException(status_code=409, detail="Conversation has not ended")
    # Corrections still in flight get a few seconds to land; then summarise what we have.
    await pending.wait_for_corrections(conversation_id, SUMMARY_WAIT_SECONDS)
    messages = await store.list_messages(conversation_id)
    return build_summary(conversation, messages)


async def _send(ws: WebSocket, event: dict[str, Any]) -> None:
    """Send an event, treating a send on a closed socket as a normal disconnect."""
    try:
        await ws.send_json(event)
    except RuntimeError as exc:
        raise WebSocketDisconnect() from exc


async def _reply(ws: WebSocket, store: Store, llm: LLM, conversation: Conversation) -> None:
    """Stream the agent's next reply to the client, then save it."""
    history = await store.list_messages(conversation.id)
    system = build_system_prompt(conversation.scenario)
    parts: list[str] = []
    try:
        async for chunk in llm.stream_reply(system, to_api_messages(history)):
            parts.append(chunk)
            await _send(ws, {"type": "token", "text": chunk})
    except WebSocketDisconnect:
        raise
    except LLMUnavailableError as exc:
        await _send(ws, {"type": "error", "detail": str(exc)})
        return
    except Exception:
        log.exception("reply_failed", conversation_id=str(conversation.id))
        await _send(ws, {"type": "error", "detail": "The agent couldn't reply. Try again."})
        return

    text = "".join(parts)
    if not text.strip():
        log.warning("reply_empty", conversation_id=str(conversation.id))
        await _send(ws, {"type": "error", "detail": "The agent sent an empty reply. Try again."})
        return

    # Another connection may have answered this turn while we were streaming (for example,
    # a page reload mid-reply). Keep the first reply and drop ours.
    if len(await store.list_messages(conversation.id)) != len(history):
        log.warning("reply_discarded_stale", conversation_id=str(conversation.id))
        return

    message = await store.add_message(conversation.id, "assistant", text)
    log.info("reply_sent", conversation_id=str(conversation.id), reply_length=len(text))
    await _send(ws, {"type": "message_done", "id": str(message.id), "content": text})


async def _correct(
    ws: WebSocket, store: Store, llm: LLM, message_id: UUID, content: str, context: str | None
) -> None:
    """Check one learner message in the background. Never raises and never sends `error`.

    It outlives a closed socket on purpose: the result is still saved, and shows on reload.
    """
    try:
        located = await check_message(llm, content, context)
        stored = StoredCorrections(corrections=located.corrections)
        await store.save_corrections(message_id, stored)
    except Exception:
        log.warning("correction_failed", message_id=str(message_id), exc_info=True)
        return
    log.info(
        "corrections_saved",
        message_id=str(message_id),
        count=len(located.corrections),
        dropped=located.dropped,
    )
    try:
        await _send(
            ws,
            {
                "type": "corrections",
                "message_id": str(message_id),
                "corrections": json.loads(stored.model_dump_json())["corrections"],
            },
        )
    except (WebSocketDisconnect, RuntimeError):
        pass  # The learner left; the saved result will show on reload.


@router.websocket("/{conversation_id}/ws")
async def chat(ws: WebSocket, conversation_id: UUID, store: StoreDep, llm: LLMDep) -> None:
    await ws.accept()
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        await ws.close(code=CLOSE_NOT_FOUND)
        return

    log.info("chat_connected", conversation_id=str(conversation_id))
    try:
        history = await store.list_messages(conversation_id)
        if conversation.ended_at is None and (not history or history[-1].role == "user"):
            await _reply(ws, store, llm, conversation)

        while True:
            raw = await ws.receive_text()
            try:
                incoming = ClientMessage.model_validate_json(raw)
            except ValidationError:
                await _send(ws, {"type": "error", "detail": "Message must be 1-2000 characters."})
                continue
            content = normalize(incoming.content.strip())
            if not content:
                await _send(ws, {"type": "error", "detail": "Message is empty."})
                continue
            # Re-read: the learner may have ended the conversation from another request.
            current = await store.get_conversation(conversation_id)
            if current is None or current.ended_at is not None:
                await _send(ws, {"type": "error", "detail": "This conversation has ended."})
                continue
            history = await store.list_messages(conversation_id)
            context = history[-1].content if history and history[-1].role == "assistant" else None
            saved = await store.add_message(conversation_id, "user", content)
            log.info(
                "user_message", conversation_id=str(conversation_id), content_length=len(content)
            )
            await _send(ws, {"type": "user_message_saved", "id": str(saved.id)})
            pending.spawn(conversation_id, _correct(ws, store, llm, saved.id, content, context))
            await _reply(ws, store, llm, conversation)
    except WebSocketDisconnect:
        log.info("chat_disconnected", conversation_id=str(conversation_id))
