"""Deterministic scoring for the correction eval. No model calls here."""

import unicodedata
from dataclasses import dataclass, field
from statistics import quantiles
from typing import Any

from app.schemas.correction import LocatedCorrection


def fold(text: str) -> str:
    """NFC, case-folded, whitespace-collapsed, for comparing fixes."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass
class Expected:
    original: str
    corrected: str
    category: str
    alt_corrected: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    clean: bool
    n_expected: int
    n_predicted: int  # located predictions
    n_dropped: int  # predictions the server could not place
    n_matched: int
    n_false_positive: int
    n_fix_correct: int
    n_category_correct: int
    latency: float

    @property
    def passed(self) -> bool:
        """Clean: no predictions. Otherwise: everything found, nothing spurious."""
        if self.clean:
            return self.n_predicted == 0
        return self.n_matched == self.n_expected and self.n_false_positive == 0


def find_expected_span(message: str, exp: Expected) -> tuple[int, int] | None:
    start = unicodedata.normalize("NFC", message).find(unicodedata.normalize("NFC", exp.original))
    if start < 0:
        return None
    return start, start + len(exp.original)


def score_case(
    case_id: str,
    message: str,
    expected: list[Expected],
    predicted: list[LocatedCorrection],
    dropped: int,
    latency: float,
) -> CaseResult:
    spans = [find_expected_span(message, e) for e in expected]
    used: set[int] = set()
    matched = fix_ok = cat_ok = fp = 0
    for p in predicted:
        hit = next(
            (
                i
                for i, s in enumerate(spans)
                if i not in used and s and p.start < s[1] and s[0] < p.end
            ),
            None,
        )
        if hit is None:
            fp += 1
            continue
        used.add(hit)
        matched += 1
        e = expected[hit]
        if fold(p.corrected) in {fold(e.corrected), *(fold(a) for a in e.alt_corrected)}:
            fix_ok += 1
        if p.category.value == e.category:
            cat_ok += 1
    return CaseResult(
        case_id=case_id,
        clean=not expected,
        n_expected=len(expected),
        n_predicted=len(predicted),
        n_dropped=dropped,
        n_matched=matched,
        n_false_positive=fp,
        n_fix_correct=fix_ok,
        n_category_correct=cat_ok,
        latency=latency,
    )


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[pct - 1]


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    """Metrics for one run. Ratios are None when their denominator is zero."""
    clean = [r for r in results if r.clean]
    raised = sum(r.n_predicted + r.n_dropped for r in results)
    expected = sum(r.n_expected for r in results)
    matched = sum(r.n_matched for r in results)
    lat = [r.latency for r in results]
    return {
        "cases": len(results),
        "clean_pass_rate": _ratio(sum(r.passed for r in clean), len(clean)),
        "false_positive_rate": _ratio(sum(r.n_false_positive for r in results), len(results)),
        "recall": _ratio(matched, expected),
        "fix_accuracy": _ratio(sum(r.n_fix_correct for r in results), matched),
        "category_accuracy": _ratio(sum(r.n_category_correct for r in results), matched),
        "locate_drop_rate": _ratio(sum(r.n_dropped for r in results), raised),
        "latency_p50": percentile(lat, 50),
        "latency_p95": percentile(lat, 95),
    }


# metric -> (target, higher_is_better); None target = report only
TARGETS: dict[str, tuple[float | None, bool]] = {
    "clean_pass_rate": (0.95, True),
    "false_positive_rate": (0.05, False),
    "recall": (0.85, True),
    "fix_accuracy": (0.90, True),
    "category_accuracy": (None, True),
    "locate_drop_rate": (0.05, False),
    "latency_p95": (2.0, False),
}


def meets_target(metric: str, value: float | None) -> bool | None:
    target, higher = TARGETS.get(metric, (None, True))
    if target is None or value is None:
        return None
    return value >= target if higher else value <= target


def combine_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """Per metric: mean and worst across runs (worst respects metric direction)."""
    out: dict[str, dict[str, float | None]] = {}
    for metric in TARGETS:
        vals = [r[metric] for r in runs if r.get(metric) is not None]
        if not vals:
            out[metric] = {"mean": None, "worst": None}
            continue
        higher = TARGETS[metric][1]
        out[metric] = {
            "mean": sum(vals) / len(vals),
            "worst": min(vals) if higher else max(vals),
        }
    return out


def case_pass_all_runs(per_run: list[list[CaseResult]]) -> float:
    """% of cases that pass on every run."""
    by_case: dict[str, list[bool]] = {}
    for run in per_run:
        for r in run:
            by_case.setdefault(r.case_id, []).append(r.passed)
    return sum(all(v) for v in by_case.values()) / len(by_case) if by_case else 0.0
