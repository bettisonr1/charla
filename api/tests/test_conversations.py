from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.llm import LLMUnavailableError
from app.prompts import START_CUE
from tests.conftest import FakeLLM, FakeStore


def _create(client: TestClient, scenario: str = "Ordering at a restaurant in Madrid") -> str:
    response = client.post("/conversations", json={"scenario": scenario})
    assert response.status_code == 201
    return str(response.json()["id"])


def _read_reply(ws) -> dict:  # type: ignore[no-untyped-def]
    """Collect token events up to the closing message_done or error event."""
    tokens: list[str] = []
    while True:
        event = ws.receive_json()
        if event["type"] == "token":
            tokens.append(event["text"])
        else:
            return {**event, "tokens": tokens}


def test_create_and_get_conversation(client: TestClient) -> None:
    conversation_id = _create(client)
    detail = client.get(f"/conversations/{conversation_id}").json()
    assert detail["scenario"] == "Ordering at a restaurant in Madrid"
    assert detail["messages"] == []


def test_create_rejects_empty_and_overlong_scenarios(client: TestClient) -> None:
    assert client.post("/conversations", json={"scenario": ""}).status_code == 422
    assert client.post("/conversations", json={"scenario": "x" * 501}).status_code == 422


def test_get_unknown_conversation_is_404(client: TestClient) -> None:
    assert client.get(f"/conversations/{uuid4()}").status_code == 404


def test_list_conversations_most_recent_first(client: TestClient) -> None:
    first = _create(client, "first")
    second = _create(client, "second")
    ids = [c["id"] for c in client.get("/conversations").json()]
    assert ids == [second, first]


def test_new_conversation_opens_with_an_agent_message(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    conversation_id = _create(client)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        done = _read_reply(ws)

    assert done["type"] == "message_done"
    assert done["tokens"] == ["Hola, ", "¿qué ", "tal?"]
    assert done["content"] == "Hola, ¿qué tal?"
    assert [(m.role, m.content) for m in store.messages] == [("assistant", "Hola, ¿qué tal?")]
    system, messages = llm.calls[0]
    assert "Ordering at a restaurant in Madrid" in system
    assert messages == [{"role": "user", "content": START_CUE}]


def test_user_message_is_saved_and_answered(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    conversation_id = _create(client)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        _read_reply(ws)  # opener
        llm.chunks = ["Muy bien."]
        ws.send_json({"type": "message", "content": "  Quiero una mesa  "})
        done = _read_reply(ws)

    assert done["content"] == "Muy bien."
    assert [(m.role, m.content) for m in store.messages] == [
        ("assistant", "Hola, ¿qué tal?"),
        ("user", "Quiero una mesa"),
        ("assistant", "Muy bien."),
    ]
    _, messages = llm.calls[1]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]


def test_reconnect_does_not_repeat_the_opener(client: TestClient, llm: FakeLLM) -> None:
    conversation_id = _create(client)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        _read_reply(ws)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws"):
        pass
    assert len(llm.calls) == 1


def test_reconnect_answers_an_unanswered_user_message(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    conversation_id = _create(client)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        _read_reply(ws)
    cid = next(iter(store.conversations))
    store.messages.append(
        type(store.messages[0])(
            id=uuid4(),
            conversation_id=cid,
            role="user",
            content="Hola",
            created_at=store.messages[0].created_at,
        )
    )
    llm.chunks = ["¡Claro!"]
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        done = _read_reply(ws)
    assert done["content"] == "¡Claro!"


def test_unknown_conversation_closes_with_4404(client: TestClient) -> None:
    with client.websocket_connect(f"/conversations/{uuid4()}/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4404


def test_invalid_frames_get_an_error_and_keep_the_socket_open(
    client: TestClient, llm: FakeLLM
) -> None:
    conversation_id = _create(client)
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        _read_reply(ws)
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "message", "content": "   "})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "message", "content": "x" * 2001})
        assert ws.receive_json()["type"] == "error"
        assert len(llm.calls) == 1


def test_model_failure_sends_error_and_saves_no_reply(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    conversation_id = _create(client)
    llm.error = RuntimeError("boom")
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "boom" not in event["detail"]
    assert store.messages == []


def test_missing_api_key_is_reported(client: TestClient, llm: FakeLLM) -> None:
    conversation_id = _create(client)
    llm.error = LLMUnavailableError("ANTHROPIC_API_KEY is not set. Add it to api/.env.")
    with client.websocket_connect(f"/conversations/{conversation_id}/ws") as ws:
        event = ws.receive_json()
    assert event == {
        "type": "error",
        "detail": "ANTHROPIC_API_KEY is not set. Add it to api/.env.",
    }
