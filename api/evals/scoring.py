"""Pure scoring for the correction eval. No model calls here, so it is unit-tested in CI."""

import unicodedata
from dataclasses import dataclass, field

from app.corrections import normalize
from app.schemas.correction import LocatedCorrection


@dataclass(frozen=True)
class Expected:
    original: str
    corrected: str
    category: str
    alt_corrected: tuple[str, ...] = ()


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    expected: tuple[Expected, ...]
    context: str | None = None
    tags: tuple[str, ...] = ()
    split: str = "dev"


def parse_case(raw: dict[str, object]) -> Case:
    expected = tuple(
        Expected(
            original=str(e["original"]),
            corrected=str(e["corrected"]),
            category=str(e["category"]),
            alt_corrected=tuple(e.get("alt_corrected", ())),  # type: ignore[attr-defined]
        )
        for e in raw.get("expected", [])  # type: ignore[attr-defined]
    )
    return Case(
        id=str(raw["id"]),
        message=str(raw["message"]),
        expected=expected,
        context=str(raw["context"]) if raw.get("context") else None,
        tags=tuple(raw.get("tags", ())),  # type: ignore[arg-type]
        split=str(raw.get("split", "dev")),
    )


def fold(text: str) -> str:
    """NFC, case-folded, whitespace-collapsed, trailing punctuation ignored."""
    collapsed = " ".join(unicodedata.normalize("NFC", text).casefold().split())
    return collapsed.strip(" .,;:!?¡¿")


def expected_span(case: Case, expected: Expected) -> tuple[int, int] | None:
    message = normalize(case.message)
    original = normalize(expected.original)
    index = message.find(original)
    if index < 0:
        index = (
            message.lower().find(original.lower()) if len(message.lower()) == len(message) else -1
        )
    return None if index < 0 else (index, index + len(original))


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


@dataclass
class CaseResult:
    case_id: str
    clean: bool  # the case expects no corrections
    n_expected: int
    n_predicted: int  # located predictions
    n_dropped: int  # predictions the server could not place
    matched: int = 0
    false_positives: int = 0
    fix_correct: int = 0
    category_correct: int = 0
    latency_s: float = 0.0
    passed: bool = False
    explanations: list[str] = field(default_factory=list)


def score_case(
    case: Case, predicted: list[LocatedCorrection], dropped: int, latency_s: float
) -> CaseResult:
    spans = [expected_span(case, e) for e in case.expected]
    result = CaseResult(
        case_id=case.id,
        clean=not case.expected,
        n_expected=len(case.expected),
        n_predicted=len(predicted),
        n_dropped=dropped,
        latency_s=latency_s,
        explanations=[f"{p.original} -> {p.corrected}: {p.explanation}" for p in predicted],
    )
    used: set[int] = set()
    for p in predicted:
        span = (p.start, p.end)
        hit = next(
            (
                i
                for i, s in enumerate(spans)
                if s is not None and i not in used and _overlaps(span, s)
            ),
            None,
        )
        if hit is None:
            result.false_positives += 1
            continue
        used.add(hit)
        result.matched += 1
        exp = case.expected[hit]
        if fold(p.corrected) in {fold(exp.corrected), *(fold(a) for a in exp.alt_corrected)}:
            result.fix_correct += 1
        if p.category.value == exp.category:
            result.category_correct += 1
    result.passed = result.false_positives == 0 and result.matched == result.n_expected
    return result


@dataclass
class Metrics:
    clean_pass_rate: float
    false_positive_rate: float  # false positives per message
    recall: float
    fix_accuracy: float
    category_accuracy: float
    locate_drop_rate: float  # dropped / (located + dropped)
    latency_p50: float
    latency_p95: float


def _ratio(num: float, den: float) -> float:
    return num / den if den else 1.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest-rank.
    rank = max(1, round(q * len(ordered) + 0.4999999))
    return ordered[min(rank, len(ordered)) - 1]


def aggregate(results: list[CaseResult]) -> Metrics:
    clean = [r for r in results if r.clean]
    matched = sum(r.matched for r in results)
    predictions = sum(r.n_predicted + r.n_dropped for r in results)
    latencies = [r.latency_s for r in results]
    return Metrics(
        clean_pass_rate=_ratio(sum(r.n_predicted == 0 for r in clean), len(clean)),
        false_positive_rate=_ratio(sum(r.false_positives for r in results), len(results))
        if results
        else 0.0,
        recall=_ratio(matched, sum(r.n_expected for r in results)),
        fix_accuracy=_ratio(sum(r.fix_correct for r in results), matched),
        category_accuracy=_ratio(sum(r.category_correct for r in results), matched),
        locate_drop_rate=sum(r.n_dropped for r in results) / predictions if predictions else 0.0,
        latency_p50=percentile(latencies, 0.5),
        latency_p95=percentile(latencies, 0.95),
    )


# (metric, direction, target): "min" means value must be >= target, "max" means <=.
TARGETS: dict[str, tuple[str, float]] = {
    "clean_pass_rate": ("min", 0.95),
    "false_positive_rate": ("max", 0.05),
    "recall": ("min", 0.85),
    "fix_accuracy": ("min", 0.90),
    "locate_drop_rate": ("max", 0.05),
    "latency_p95": ("max", 2.0),
}


def meets_target(name: str, value: float) -> bool | None:
    """None when the metric has no target (it is report-only)."""
    if name not in TARGETS:
        return None
    direction, target = TARGETS[name]
    return value >= target if direction == "min" else value <= target


def merge_runs(runs: list[Metrics]) -> dict[str, dict[str, float]]:
    """Mean and worst value across runs, per metric."""
    out: dict[str, dict[str, float]] = {}
    for name in Metrics.__dataclass_fields__:
        values = [getattr(r, name) for r in runs]
        higher_is_better = TARGETS.get(name, ("min", 0))[0] == "min"
        out[name] = {
            "mean": sum(values) / len(values),
            "worst": min(values) if higher_is_better else max(values),
        }
    return out


def case_passes_every_run(per_run: list[list[CaseResult]]) -> dict[str, bool]:
    """A case passes only if it passes on every run."""
    verdicts: dict[str, bool] = {}
    for run in per_run:
        for r in run:
            verdicts[r.case_id] = verdicts.get(r.case_id, True) and r.passed
    return verdicts
