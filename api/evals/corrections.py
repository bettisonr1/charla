"""Correction-quality eval: runs the production correction path against labelled cases.

    uv run python -m evals.corrections --model claude-haiku-5-5 --runs 3 --split dev

Calls the real model (needs ANTHROPIC_API_KEY in api/.env), so it never runs in CI. See
docs/phase-2-evals.md for the process.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.corrections import check_message
from app.llm import AnthropicLLM
from app.prompts import CORRECTION_SYSTEM_PROMPT
from evals.scoring import (
    Case,
    CaseResult,
    aggregate,
    case_passes_every_run,
    meets_target,
    merge_runs,
    parse_case,
    score_case,
)

HERE = Path(__file__).parent
CASES = HERE / "cases" / "corrections.jsonl"
RESULTS = HERE / "results"


def load_cases(split: str) -> list[Case]:
    cases = [
        parse_case(json.loads(line)) for line in CASES.read_text().splitlines() if line.strip()
    ]
    return cases if split == "all" else [c for c in cases if c.split == split]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


async def run_once(llm: AnthropicLLM, cases: list[Case]) -> list[CaseResult]:
    results = []
    for case in cases:  # sequential, so rate limiting does not skew latency
        started = time.perf_counter()
        try:
            located = await check_message(llm, case.message, case.context)
        except Exception as exc:  # a failed call counts as a miss, not a crash
            print(f"  {case.id}: call failed ({type(exc).__name__})")
            results.append(score_case(case, [], 0, time.perf_counter() - started))
            continue
        results.append(
            score_case(case, located.corrections, located.dropped, time.perf_counter() - started)
        )
    return results


def _latest_previous(model: str) -> dict | None:  # type: ignore[type-arg]
    files = sorted(RESULTS.glob(f"*{model}*.json"))
    return json.loads(files[-1].read_text()) if files else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=settings.correction_model)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="dev")
    args = parser.parse_args()

    settings.correction_model = args.model
    cases = load_cases(args.split)
    llm = AnthropicLLM()

    async def go() -> list[list[CaseResult]]:
        runs = []
        for i in range(args.runs):
            print(f"run {i + 1}/{args.runs} ({len(cases)} cases, {args.model})")
            runs.append(await run_once(llm, cases))
        return runs

    per_run = asyncio.run(go())
    summary = merge_runs([aggregate(r) for r in per_run])
    verdicts = case_passes_every_run(per_run)
    previous = _latest_previous(args.model)

    print(f"\n{'metric':<22}{'mean':>9}{'worst':>9}{'target':>8}{'delta':>9}")
    for name, v in summary.items():
        ok = meets_target(name, v["worst"])
        mark = "" if ok is None else ("  ok" if ok else "  MISS")
        delta = ""
        if previous and name in previous["metrics"]:
            delta = f"{v['mean'] - previous['metrics'][name]['mean']:+.3f}"
        print(f"{name:<22}{v['mean']:>9.3f}{v['worst']:>9.3f}{'':>8}{delta:>9}{mark}")

    failing = sorted(c for c, ok in verdicts.items() if not ok)
    print(f"\ncases passing every run: {len(verdicts) - len(failing)}/{len(verdicts)}")
    if failing:
        print("failing:", ", ".join(failing))

    print("\nexplanations (last run, for skimming):")
    for r in per_run[-1]:
        for line in r.explanations:
            print(f"  [{r.case_id}] {line}")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"{stamp}-{args.model}-{args.split}.json"
    out.write_text(
        json.dumps(
            {
                "model": args.model,
                "split": args.split,
                "runs": args.runs,
                "date": stamp,
                "git_sha": _git_sha(),
                "prompt_hash": hashlib.sha256(CORRECTION_SYSTEM_PROMPT.encode()).hexdigest()[:12],
                "metrics": summary,
                "failing_cases": failing,
            },
            indent=2,
        )
    )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
