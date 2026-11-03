"""Conversation endpoints: create/list/get over HTTP, and the chat itself over a WebSocket.

WebSocket protocol (JSON text frames):

  client -> server   {"type": "message", "content": "<the learner's text>"}
  server -> client   {"type": "token", "text": "<next chunk of the agent's reply>"}
                     {"type": "message_done", "id": "<message id>", "content": "<full reply>"}
                     {"type": "error", "detail": "<what went wrong>"}

On connect, the server replies first if the agent has not spoken yet (a new conversation) or if
the last stored message is the learner's and has no reply (an interrupted turn). Closing code
4404 means the conversation does not exist.
"""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.llm import LLM, LLMUnavailableError, get_llm
from app.models import Conversation
from app.prompts import build_system_prompt, to_api_messages
from app.schemas.conversation import (
    ClientMessage,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.store import Store, get_store

log = structlog.get_logger()

router = APIRouter(prefix="/conversations", tags=["conversations"])

StoreDep = Annotated[Store, Depends(get_store)]
LLMDep = Annotated[LLM, Depends(get_llm)]

CLOSE_NOT_FOUND = 4404


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
        messages=[MessageOut.model_validate(m) for m in messages],
    )


async def _send(ws: WebSocket, event: dict[str, str]) -> None:
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
        if not history or history[-1].role == "user":
            await _reply(ws, store, llm, conversation)

        while True:
            raw = await ws.receive_text()
            try:
                incoming = ClientMessage.model_validate_json(raw)
            except ValidationError:
                await _send(ws, {"type": "error", "detail": "Message must be 1-2000 characters."})
                continue
            content = incoming.content.strip()
            if not content:
                await _send(ws, {"type": "error", "detail": "Message is empty."})
                continue
            await store.add_message(conversation_id, "user", content)
            log.info(
                "user_message", conversation_id=str(conversation_id), content_length=len(content)
            )
            await _reply(ws, store, llm, conversation)
    except WebSocketDisconnect:
        log.info("chat_disconnected", conversation_id=str(conversation_id))
