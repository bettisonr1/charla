# Phase 2 eval plan: correction quality

Companion to `phase-2-plan.md`. The quality bar from `CLAUDE.md` is: catch real errors, don't
nitpick, don't invent errors. This eval makes that measurable so prompt and model changes are decided
by numbers, not by feel. Real-model runs live here, never in the pytest suite.

## What it answers

1. Does the correction prompt catch real errors? (recall)
2. Does it stay quiet on correct Spanish? (false positives, the most important number)
3. When it flags something, is the fix right and the span usable?
4. Is it fast enough? (about 2 seconds from message to flags, model call is most of that)
5. Haiku or Sonnet?

## Layout

    api/evals/
      cases/corrections.jsonl     the labelled cases
      corrections.py              runner (CLI)
      scoring.py                  pure scoring functions
      results/                    one JSON per run (gitignored except a committed baseline)

Run: `uv run python -m evals.corrections --model <id> --runs 3 --split dev`

- The runner calls the **same** `LLM.correct()` and the same locate-and-validate step as production,
  so it measures the real path including dropped (unlocatable) corrections.
- `scoring.py` is deterministic and gets ordinary unit tests in `api/tests/`. Only the model calls
  are excluded from CI.

## Case format

One JSON object per line:

    {"id": "ser-estar-01",
     "context": "¿Cómo te sientes hoy?",          // the agent's previous turn, optional
     "message": "Yo soy muy cansado.",
     "expected": [{"original": "soy muy cansado", "corrected": "estoy muy cansado",
                   "alt_corrected": ["estoy muy cansada"], "category": "ser_estar"}],
     "tags": ["ser_estar"],
     "split": "dev"}

- A **clean** case has `"expected": []`.
- `original` is what we expect to be underlined; `alt_corrected` lists other acceptable fixes.
- `split` is `dev` or `holdout` (see Process).

## What the cases cover (target ~60 to start)

| Group | Count | Purpose |
|-------|-------|---------|
| Real errors, one per category | ≥3 each × 10 categories | recall per `ErrorCategory` |
| Multi-error messages | ~6 | all found, no span overlaps, no double-flagging |
| Clean, plain correct Spanish | ~10 | baseline false-positive rate |
| Clean, **near-miss** | ~12 | the nitpick traps (below) |
| Accent/punctuation rule | ~6 | missing `¿`/`¡` and meaning-neutral accents ignored; `esta`/`está` flagged |
| Context-dependent | ~4 | short answers ("Sí, mañana") that are correct only given `context` |
| Missing-word errors | ~4 | span must quote neighbouring words so it is underlinable |
| Awkward input | ~4 | English words mixed in, very short, repeated fragment, emoji |

Near-miss clean cases (must **not** be flagged):
- Regional variants that are fine in some dialect: `vosotros`, `vos`, `carro`/`coche`/`auto`. Dialect is
  still undecided (roadmap open question 1), so these stay clean until it is.
- Informal but correct: dropped subject pronouns, colloquialisms, `pues`, `o sea`.
- Unusual but valid word order; valid alternatives to what the model would "prefer".
- Style preferences a native might change but that are not errors (the `register` trap).

## Sourcing the cases

- **Seed from real mistakes.** The learner's own past messages and errors are the most valuable cases,
  because they reflect the mistakes that actually occur. Rob supplies and labels these.
- Fill category gaps with synthetic sentences.
- Every case needs a label a Spanish speaker would agree with. Disputed cases get dropped, not fudged.
- When a real conversation produces a bad flag or a miss, add it as a case (regression habit).

## Scoring

Match each predicted correction to an expected one when their **located spans overlap**. Then:

| Metric | Definition | Target |
|--------|-----------|--------|
| **Clean pass rate** | % of clean cases with zero predictions | ≥ 95% |
| **False-positive rate** | predictions overlapping no expected error, per message | ≤ 5% |
| **Recall** | expected errors matched ÷ expected errors | ≥ 85% |
| **Fix accuracy** | matched predictions whose `corrected` equals `corrected` or an `alt_corrected` (NFC, case/whitespace-folded) | ≥ 90% |
| **Category accuracy** | matched predictions with the expected category | report only (categories overlap, e.g. `grammar` vs `gender_agreement`) |
| **Locate drop rate** | predictions the server could not place in the message | ≤ 5% |
| **Latency** | model call wall-clock, p50 and p95 | p95 ≤ ~2 s |

Targets are starting guesses; adjust after the first baseline run, then hold them.

Not scored automatically: explanation quality (is it correct Spanish, at B1, helpful?). The runner
prints each case's explanations to a readable report, and Rob skims a sample on every prompt change.
Add an LLM judge only if skimming stops being enough.

## Handling noise

- Temperature 0, but outputs still vary. Default `--runs 3`; report mean and worst run per metric.
- A case "passes" for pass-rate purposes only if it passes on every run.
- Latency measured sequentially, not in parallel, so rate limiting does not skew it.

## Process

1. **Baseline first:** run the initial prompt on `dev`, commit the numbers.
2. **Before every prompt or model change:** run the eval; compare with the last run (the runner prints
   deltas, and records git sha, prompt hash, model and date in each result file).
3. **Tune on `dev` only.** Keep ~20% of cases as `holdout`, run once when choosing the final prompt
   and model, so we do not overfit to the cases we looked at.
4. **Model choice:** run Haiku and Sonnet on the same cases. Pick the cheaper model if it meets every
   target; otherwise the false-positive rate decides, since a wrongly flagged correct sentence damages
   trust more than a missed error.
5. Cost is negligible at this size (~60 cases × 3 runs × 2 models), so run freely.

## Later reuse

- The Phase 1 reply eval (canned conversation against the real model, time to first token) shares the
  runner scaffolding and result format, so it lives in the same `evals/` package.
- Phase 3 adds a level dimension to the cases (`"level": "B1"`): a C1 stylistic choice is clean at B1.
- Phase 5 adds a spoken-transcript group (no punctuation or capitalization, disfluencies).
- Phase 7 reads corrections in aggregate, so category accuracy starts to matter then; promote it to a
  target at that point.
