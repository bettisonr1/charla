# Phase 2 plan: corrections and end-of-conversation summary

Detail for the Phase 2 section of `roadmap.md`. Written against the Phase 1 code.

## Decisions

1. **Explanations are in Spanish**, simple, at the learner's level (as `Correction.explanation` already says).
2. **Accents and punctuation:** flag a missing accent only when it changes meaning (`esta`/`está`).
   Ignore missing `¿`/`¡` and other typing-on-a-phone slips. The prompt and the eval set encode this.
3. **After "End conversation" the chat is read-only.** No resuming; the summary is final.
4. **Corrections stay in `messages.corrections` (JSONB).** Revisit a `corrections` table in Phase 7
   if aggregation gets awkward.

## Gaps in Phase 1 this phase has to close

- **Shared DB session.** `SqlStore` wraps one `AsyncSession` for the whole WebSocket. The correction
  task runs concurrently with the reply, so it must open its own short-lived session, and only for its
  write, after the LLM call returns. `Store` needs a session factory (tests use a fake store).
- **Real ids for user messages.** The client uses `local-N` ids and never learns the saved UUID. Add a
  `user_message_saved` event.
- **`corrections` is not exposed.** `MessageOut` omits it. Add it so a reload shows past flags.
- **No eval harness exists** (Phase 1 promised one). Build the shared runner here.

## Data shapes

- **Model output:** `CorrectionReport` as-is (`original`, `corrected`, `category`, `explanation`,
  optional `natural_rewrite`). No offsets: models count characters badly.
- **Stored and served:** a located correction = the above plus `start`/`end`, computed by the server.
  A separate model, so the model-facing contract is untouched.
- `corrections` column: `NULL` = not checked or check failed; `{"corrections": []}` = checked, clean.

### Locating spans

- Normalize the message to NFC before saving and matching.
- Exact match of `original`, then case-insensitive fallback. No match: drop the correction and log it
  (this is also the guard against invented errors).
- Repeated fragment: first match. Overlapping spans: keep the longer.
- Offsets are code points; the client slices with `Array.from(content)`.
- Prompt rule: `original` is the shortest contiguous exact substring containing the error. For a
  missing word, quote the neighbouring words so there is something to underline.

## WebSocket protocol (additive)

    server -> client  {"type": "user_message_saved", "id": "<uuid>"}
                      {"type": "corrections", "message_id": "<uuid>", "corrections": [...located...]}

A failed correction call sends nothing and never produces an `error` event.

## Build order

1. **Eval and prompt.** `api/evals/corrections.jsonl` (known-error, clean and near-miss sentences,
   including the accent/punctuation rule) plus a runner reporting recall, false-positive rate on clean
   sentences, and p50/p95 latency per model. Tune the prompt, choose Haiku vs Sonnet from the numbers.
2. **Backend.** `LLM.correct()` with structured output; `correction_model` setting; locate-and-validate
   step; own-session persistence; new WS events; `MessageOut.corrections`. Mocked-SDK tests, including
   "correction failure leaves the chat working" and "socket closes mid-correction, result still saved".
3. **Web.** Handle the new events in `useChat`; render underlines in user bubbles; tap opens a bottom
   sheet (fix, category, explanation); one-handed on a phone.
4. **End conversation.** `ended_at` column + migration; `POST /conversations/{id}/end`; the server
   rejects further messages and the socket sends no agent opener once ended; summary endpoint; summary
   screen; read-only chat view.

## Summary (deterministic)

Built from stored corrections, no LLM: group by category, most frequent first, each with the learner's
own sentence and the corrected version. If corrections are still pending when the user ends the
conversation, wait briefly (a few seconds), then summarise what has landed.

## Done when

A deliberately wrong sentence is flagged within about 2 seconds, a correct one is not, and the summary
matches what was flagged.
