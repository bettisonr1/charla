import asyncio
import unicodedata
from uuid import UUID

from fastapi.testclient import TestClient

from app.corrections import locate_corrections
from app.llm import parse_correction_report
from app.routers.conversations import _correct
from app.schemas.correction import Correction, CorrectionReport, ErrorCategory
from tests.conftest import FakeLLM, FakeStore


def _c(original: str, corrected: str = "x", category: ErrorCategory = ErrorCategory.GRAMMAR):
    return Correction(original=original, corrected=corrected, category=category, explanation="e")


def _locate(message: str, *originals: str):
    return locate_corrections(message, CorrectionReport(corrections=[_c(o) for o in originals]))


# --- locating -----------------------------------------------------------------------------


def test_exact_match_gives_code_point_offsets() -> None:
    result = _locate("Yo soy muy cansado.", "soy muy cansado")
    assert [(c.start, c.end) for c in result.corrections] == [(3, 18)]
    assert result.dropped == 0


def test_case_insensitive_fallback_keeps_the_learners_spelling() -> None:
    result = _locate("Yo Soy cansado", "soy cansado")
    assert result.corrections[0].original == "Soy cansado"


def test_unlocatable_correction_is_dropped() -> None:
    result = _locate("Hola, ¿qué tal?", "inventado")
    assert result.corrections == []
    assert result.dropped == 1


def test_repeated_fragment_uses_first_match() -> None:
    result = _locate("la problema, la problema", "la problema")
    assert result.corrections[0].start == 0


def test_overlap_keeps_the_longer_span() -> None:
    result = _locate("Yo soy muy cansado hoy", "soy", "soy muy cansado")
    assert [c.original for c in result.corrections] == ["soy muy cansado"]
    assert result.dropped == 1


def test_matching_is_nfc_normalised() -> None:
    message = unicodedata.normalize("NFD", "Está aquí")
    decomposed = unicodedata.normalize("NFD", "Está")
    result = _locate(message, decomposed)
    assert result.corrections[0].original == unicodedata.normalize("NFC", "Está")
    assert result.corrections[0].end == 4


def test_offsets_count_code_points_not_utf16_units() -> None:
    result = _locate("😀 la problema", "la problema")
    assert result.corrections[0].start == 2


def test_parse_tolerates_code_fences() -> None:
    text = '```json\n{"corrections": [], "natural_rewrite": null}\n```'
    assert parse_correction_report(text).corrections == []


# --- WebSocket ----------------------------------------------------------------------------


def _create(client: TestClient) -> str:
    return str(client.post("/conversations", json={"scenario": "Un restaurante"}).json()["id"])


def _until(ws, *types: str) -> dict:  # type: ignore[no-untyped-def]
    while True:
        event = ws.receive_json()
        if event["type"] in types:
            return event  # type: ignore[no-any-return]


def _opener(ws) -> None:  # type: ignore[no-untyped-def]
    _until(ws, "message_done")


def test_flagged_sentence_gets_saved_id_and_located_corrections(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    llm.report = CorrectionReport(corrections=[_c("soy muy cansado", "estoy muy cansado")])
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        ws.send_json({"type": "message", "content": "Yo soy muy cansado."})
        saved = _until(ws, "user_message_saved")
        found = _until(ws, "corrections")

    user = next(m for m in store.messages if m.role == "user")
    assert saved["id"] == str(user.id)
    assert found["message_id"] == str(user.id)
    assert (found["corrections"][0]["start"], found["corrections"][0]["end"]) == (3, 18)
    assert user.corrections is not None
    assert llm.correct_calls == [("Yo soy muy cansado.", "Hola, ¿qué tal?")]

    detail = client.get(f"/conversations/{cid}").json()
    by_role = {m["role"]: m for m in detail["messages"]}
    assert by_role["user"]["corrections"][0]["corrected"] == "estoy muy cansado"
    assert by_role["assistant"]["corrections"] is None


def test_clean_sentence_is_stored_as_checked_and_clean(
    client: TestClient, store: FakeStore
) -> None:
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        ws.send_json({"type": "message", "content": "Estoy muy bien."})
        found = _until(ws, "corrections")
    assert found["corrections"] == []
    user = next(m for m in store.messages if m.role == "user")
    assert user.corrections == {"corrections": []}


def test_correction_failure_leaves_the_chat_working(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    llm.correct_error = RuntimeError("boom")
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        llm.chunks = ["Claro."]
        ws.send_json({"type": "message", "content": "Hola"})
        events = []
        while True:
            event = ws.receive_json()
            events.append(event["type"])
            if event["type"] == "message_done":
                break
        # The socket still works for another turn.
        ws.send_json({"type": "message", "content": "Otra vez"})
        _until(ws, "message_done")

    assert "error" not in events and "corrections" not in events
    assert next(m for m in store.messages if m.role == "user").corrections is None


def test_corrections_do_not_block_the_reply(client: TestClient, llm: FakeLLM) -> None:
    llm.correct_gate = asyncio.Event()  # never opened until the end of the test
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        ws.send_json({"type": "message", "content": "Hola"})
        done = _until(ws, "message_done")  # arrives although corrections are still pending
    assert done["content"] == "Hola, ¿qué tal?"


class ClosedSocket:
    """A WebSocket whose client has gone away."""

    async def send_json(self, event: object) -> None:
        raise RuntimeError("Cannot call send once a close message has been sent.")


async def test_result_is_saved_when_the_socket_closes_mid_correction(
    store: FakeStore, llm: FakeLLM
) -> None:
    conversation = await store.create_conversation("Un restaurante")
    message = await store.add_message(conversation.id, "user", "Tengo la problema.")
    llm.report = CorrectionReport(corrections=[_c("la problema", "el problema")])

    await _correct(ClosedSocket(), store, llm, message.id, message.content, None)  # type: ignore[arg-type]

    assert message.corrections is not None
    assert message.corrections["corrections"][0]["corrected"] == "el problema"


# --- end conversation and summary ---------------------------------------------------------


def test_summary_requires_an_ended_conversation(client: TestClient) -> None:
    cid = _create(client)
    assert client.get(f"/conversations/{cid}/summary").status_code == 409


def test_end_unknown_conversation_is_404(client: TestClient) -> None:
    assert client.post("/conversations/" + str(UUID(int=1)) + "/end").status_code == 404


def test_ended_conversation_is_read_only(
    client: TestClient, store: FakeStore, llm: FakeLLM
) -> None:
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        first = client.post(f"/conversations/{cid}/end").json()["ended_at"]
        assert client.post(f"/conversations/{cid}/end").json()["ended_at"] == first  # idempotent
        ws.send_json({"type": "message", "content": "Hola"})
        assert _until(ws, "error")["detail"] == "This conversation has ended."
    assert len(store.messages) == 1  # nothing saved

    calls_before = len(llm.calls)
    with client.websocket_connect(f"/conversations/{cid}/ws"):
        pass
    assert len(llm.calls) == calls_before
    assert client.get(f"/conversations/{cid}").json()["ended_at"] == first


def test_ended_empty_conversation_gets_no_opener(client: TestClient, llm: FakeLLM) -> None:
    cid = _create(client)
    client.post(f"/conversations/{cid}/end")
    with client.websocket_connect(f"/conversations/{cid}/ws"):
        pass
    assert llm.calls == []


def test_summary_groups_by_category_most_frequent_first(client: TestClient, llm: FakeLLM) -> None:
    cid = _create(client)
    with client.websocket_connect(f"/conversations/{cid}/ws") as ws:
        _opener(ws)
        for text, report in [
            (
                "Yo soy cansado",
                [_c("soy cansado", "estoy cansado", ErrorCategory.SER_ESTAR)],
            ),
            (
                "Tengo la problema",
                [_c("la problema", "el problema", ErrorCategory.GENDER_AGREEMENT)],
            ),
            (
                "Ella es enojada",
                [_c("es enojada", "está enojada", ErrorCategory.SER_ESTAR)],
            ),
        ]:
            llm.report = CorrectionReport(corrections=report)
            ws.send_json({"type": "message", "content": text})
            _until(ws, "corrections")
            _until(ws, "message_done")

    client.post(f"/conversations/{cid}/end")
    summary = client.get(f"/conversations/{cid}/summary").json()
    assert summary["messages_sent"] == 3
    assert summary["total_corrections"] == 3
    assert [(g["category"], g["count"]) for g in summary["groups"]] == [
        ("ser_estar", 2),
        ("gender_agreement", 1),
    ]
    example = summary["groups"][0]["examples"][0]
    assert example["sentence"] == "Yo soy cansado"
    assert example["corrected_sentence"] == "Yo estoy cansado"
