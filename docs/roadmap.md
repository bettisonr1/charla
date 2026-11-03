# Charla roadmap

Each phase ends with something usable. Phases are ordered by dependency: later ones reuse
what earlier ones build. "Seamless" is not a phase; it is a bar every phase has to meet (see the end).

| # | Phase | You can... |
|---|-------|-----------|
| 1 | Typed conversation | chat in Spanish with an agent, streamed, saved |
| 2 | Corrections and end summary | see errors flagged inline as you type, get a mistake summary when you finish |
| 3 | Level adaptation | set your level and have the agent pitch to it |
| 4 | Text content and quizzing | upload text and be tested on it in conversation |
| 5 | Voice in and out | speak to the agent and hear it reply |
| 6 | Audio and video content | upload a recording or video and ask questions about it |
| 7 | Learner memory | have recurring mistakes shape future conversations |

Requests 2 and 4 from the original list (summarise mistakes, highlight errors in real time) share one
mechanism, so they are built together in phase 2.

## Phase 1: Typed conversation

**Goal:** a back-and-forth text chat in Spanish that persists.

- API: `conversations` and `messages` tables (+ first Alembic migration), `POST /conversations`,
  `POST /conversations/{id}/messages` returning a streamed reply (SSE), `GET /conversations/{id}`.
- Agent: system prompt for a Spanish conversation partner. Scenario is a free-text opener for now
  (e.g. "ordering at a restaurant"). Replies stay short and ask a follow-up question.
- Web: narrow-viewport-first chat screen, streaming render, conversation list.
- Tests: mocked Anthropic SDK; one eval-harness script that runs a canned conversation against the real model.

**Done when:** you can hold a 10-turn conversation, reload the page, and continue it.

## Phase 2: Corrections and end-of-conversation summary

**Goal:** catch real mistakes as they happen and summarise them at the end.

- On each user message, run a second, parallel call that returns a `CorrectionReport`
  (already defined in `api/app/schemas/correction.py`). The reply is never blocked on it.
- Persist each correction against the message: span, error type, fix, short explanation.
- Web: your message appears immediately, then underlines appear on the flagged spans when the report
  lands (typically a second or two later). Tap an underline for the fix and explanation.
- "End conversation" produces a summary: mistakes grouped by type, most frequent first, with your own
  sentences as examples and a corrected version of each.
- Quality bar (from `CLAUDE.md`): catch real errors, don't nitpick, don't invent errors. Build a small
  eval set of sentences with known errors and clean sentences, and run it before changing the prompt.
  A cheaper model such as Haiku may be enough for corrections; the eval decides.

**Done when:** a deliberately wrong sentence is flagged within about 2 seconds, a correct one is not,
and the summary matches what was flagged.

## Phase 3: Level adaptation

**Goal:** the agent talks at your level, not a fixed one.

- Learner settings: CEFR level (start at B1), dialect (still undecided, see open questions).
- Agent prompt targets one step above your level (B1+1). Corrections are also level-aware: don't flag
  C1 stylistic choices as errors at B1.
- Simple adaptation: after each conversation, nudge a per-skill estimate from the correction rate and
  the vocabulary you used, shown on the summary. Keep it transparent and overridable.

**Done when:** switching the level setting visibly changes vocabulary and sentence length of the replies.

## Phase 4: Text content and quizzing

**Goal:** upload text, then be tested on it in conversation.

- Upload: paste text or upload `.txt`/`.md`/PDF. Store the extracted text with the conversation.
- Agent mode "tutor quiz": reads the text, asks comprehension and vocabulary questions in Spanish, one
  at a time, follows up on wrong answers, and uses the Phase 2 correction pipeline on your answers.
- Includes the "explain it like a tutor" feature from the README: idioms and slang in the text
  explained in context.
- Long texts: chunk or summarise first; cache the document in the prompt.
- Ends with a summary: questions you got right and wrong, plus the usual mistake summary.

**Done when:** you can paste an article, get quizzed, and see the result.

## Phase 5: Voice in and out

**Goal:** speak to the agent and hear it answer, with latency that feels like talking.

- Anthropic has no speech models, so this needs third-party speech-to-text and text-to-speech.
  Pick vendors in a short spike (see open questions); keep them behind small interfaces in
  `api/app/voice/` so they can be swapped.
- Input: push-to-talk first (simplest, fewest false starts), then optional hands-free.
  Show the transcript as you speak; corrections run on the final transcript.
- Output: stream the reply text to TTS sentence by sentence so audio starts before the full reply exists.
- Note: spoken errors differ from typed ones (pronunciation is out of scope; grammar and word choice are in).
- Latency budget: under about 1.5 seconds from end of your speech to start of the reply audio.

**Done when:** you can run a full conversation without touching the keyboard.

## Phase 6: Audio and video content

**Goal:** upload a podcast, clip or video, then ask the agent about it.

- Pipeline: upload, extract audio (ffmpeg), transcribe with timestamps (reuses the Phase 5
  speech-to-text), then treat the transcript as Phase 4 text content.
- Timestamps let the agent say "around 2:10" and let the UI jump to that point.
- Video: audio track only to start. Visual understanding is a separate, later decision.
- Storage: local disk in dev; object storage later. Set a size and length limit up front.
- Run transcription as a background job with progress, not inside the request.

**Done when:** you can upload a 5-minute Spanish clip and be quizzed on it.

## Phase 7: Learner memory

**Goal:** recurring mistakes carry across conversations. This is the project's main differentiator,
and Phase 2 already stores the data it needs.

- Aggregate corrections across conversations into an error profile (type, frequency, recency, status).
- Feed the top few into the agent's context so it steers conversations towards them and checks
  whether they recur, without announcing it.
- Profile screen: what you keep getting wrong, what you've stopped getting wrong.
- Feeds the Phase 3 level estimate.

**Done when:** a mistake you made last week gets deliberately exercised in this week's conversation.

## Seamless: the bar for every phase

- Stream everything. Never show a blank wait; messages appear instantly and annotations arrive after.
- Correction and reply calls run in parallel; a failed correction call never breaks the chat.
- Retry and resume: a dropped connection or reload continues the conversation.
- Mobile first: usable one-handed on a phone.
- Keep a per-phase latency target and measure it in the eval harness, not by feel.

## Open questions

1. **Dialect:** Spain, Mexico, Argentina, neutral? Affects prompts, vocabulary and TTS voices (needed by Phase 3).
2. **Voice vendors:** needed before Phase 5. Compare on Spanish quality, streaming support and price.
3. **Auth:** none for now (single user). Revisit before anything is deployed publicly.
4. **File storage and limits** for Phases 4 and 6.
5. **Scenarios:** free-text prompts only, or a curated list (restaurant, doctor, job interview)?
