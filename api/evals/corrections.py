"""Correction-quality eval. Calls the real model through the production path.

uv run python -m evals.corrections --model claude-haiku-5-5 --runs 3 --split dev
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.corrections import locate_corrections, normalize
from app.llm import AnthropicLLM
from app.prompts import CORRECTION_SYSTEM_PROMPT
from evals.scoring import (
    TARGETS,
    CaseResult,
    Expected,
    aggregate,
    case_pass_all_runs,
    combine_runs,
    meets_target,
    score_case,
)

HERE = Path(__file__).parent
CASES_PATH = HERE / "cases" / "corrections.jsonl"
RESULTS_DIR = HERE / "results"


def load_cases(path: Path, split: str) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return cases if split == "all" else [c for c in cases if c["split"] == split]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


async def run_once(
    llm: AnthropicLLM, model: str, cases: list[dict[str, Any]], report_lines: list[str]
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:  # sequential on purpose: parallel calls would skew latency
        message = normalize(case["message"])
        start = time.perf_counter()
        try:
            report = await llm.correct(message, case.get("context"), model=model)
        except Exception as exc:  # a failed call counts as a miss, not a crash
            report_lines.append(f"{case['id']}: ERROR {type(exc).__name__}: {exc}")
            report = None
        latency = time.perf_counter() - start
        located = locate_corrections(message, report) if report else None
        expected = [Expected(**e) for e in case["expected"]]
        result = score_case(
            case["id"],
            message,
            expected,
            located.located if located else [],
            located.dropped if located else 0,
            latency,
        )
        results.append(result)
        status = "ok  " if result.passed else "FAIL"
        report_lines.append(f"[{status}] {case['id']}: {message}")
        for c in located.located if located else []:
            report_lines.append(
                f"        [{c.start}:{c.end}] {c.original!r} -> {c.corrected!r} "
                f"({c.category.value}) {c.explanation}"
            )
        if located and located.dropped:
            report_lines.append(f"        dropped: {located.dropped}")
    return results


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def previous_result(model: str, split: str) -> dict[str, Any] | None:
    files = sorted(RESULTS_DIR.glob(f"*{split}*.json"))
    for f in reversed(files):
        data = json.loads(f.read_text())
        if data["model"] == model and data["split"] == split:
            return data  # type: ignore[no-any-return]
    return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--split", choices=["dev", "holdout", "all"], default="dev")
    ap.add_argument("--cases", type=Path, default=CASES_PATH)
    args = ap.parse_args()

    cases = load_cases(args.cases, args.split)
    llm = AnthropicLLM()
    report_lines: list[str] = []
    per_run: list[list[CaseResult]] = []
    for i in range(args.runs):
        report_lines.append(f"--- run {i + 1} ---")
        per_run.append(await run_once(llm, args.model, cases, report_lines))

    runs = [aggregate(r) for r in per_run]
    summary = combine_runs(runs)
    pass_all = case_pass_all_runs(per_run)

    now = datetime.now(UTC)
    record = {
        "date": now.isoformat(),
        "git_sha": _git_sha(),
        "prompt_hash": hashlib.sha256(CORRECTION_SYSTEM_PROMPT.encode()).hexdigest()[:12],
        "model": args.model,
        "split": args.split,
        "runs": runs,
        "summary": summary,
        "cases_passing_every_run": pass_all,
        "failures": sorted({r.case_id for run in per_run for r in run if not r.passed}),
    }
    prev = previous_result(args.model, args.split)

    print("\n".join(report_lines))
    print(f"\nmodel={args.model} split={args.split} cases={len(cases)} runs={args.runs}")
    print(f"{'metric':22}{'mean':>8}{'worst':>8}{'target':>8}  ok   delta")
    for metric, vals in summary.items():
        target = TARGETS[metric][0]
        ok = meets_target(metric, vals["worst"])
        delta = ""
        if prev and prev["summary"][metric]["mean"] is not None and vals["mean"] is not None:
            delta = f"{vals['mean'] - prev['summary'][metric]['mean']:+.3f}"
        mark = "-" if ok is None else ("yes" if ok else "NO")
        print(
            f"{metric:22}{_fmt(vals['mean']):>8}{_fmt(vals['worst']):>8}"
            f"{_fmt(target):>8}  {mark:4} {delta}"
        )
    print(f"cases passing every run: {pass_all:.1%}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{now:%Y%m%dT%H%M%S}-{args.split}-{args.model}.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
