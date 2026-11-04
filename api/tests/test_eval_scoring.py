"""Tests for the eval's pure parts. The model calls themselves are never run in the test suite."""

import json
from collections import Counter

from app.schemas.correction import ErrorCategory, LocatedCorrection
from evals.corrections import CASES, load_cases
from evals.scoring import (
    Case,
    Expected,
    aggregate,
    case_passes_every_run,
    expected_span,
    fold,
    meets_target,
    merge_runs,
    percentile,
    score_case,
)


def _pred(original: str, start: int, corrected: str, category: ErrorCategory) -> LocatedCorrection:
    return LocatedCorrection(
        original=original,
        corrected=corrected,
        category=category,
        explanation="e",
        start=start,
        end=start + len(original),
    )


CASE = Case(
    id="c",
    message="Yo soy muy cansado.",
    expected=(Expected("soy muy cansado", "estoy muy cansado", "ser_estar", ("estoy cansado",)),),
)
CLEAN = Case(id="clean", message="Estoy bien.", expected=())


def test_case_file_is_well_formed() -> None:
    cases = load_cases("all")
    assert len(cases) >= 60
    assert len({c.id for c in cases}) == len(cases)
    for case in cases:
        for exp in case.expected:
            assert expected_span(case, exp) is not None, f"{case.id}: original not in message"
            assert exp.category in {c.value for c in ErrorCategory}, case.id
    raw = [json.loads(line) for line in CASES.read_text().splitlines()]
    assert {r["split"] for r in raw} == {"dev", "holdout"}
    categories = Counter(e.category for c in cases for e in c.expected)
    assert all(categories[c.value] >= 3 for c in ErrorCategory), categories


def test_overlapping_prediction_with_right_fix_is_a_hit() -> None:
    p = _pred("soy", 3, "estoy", ErrorCategory.SER_ESTAR)  # narrower span still overlaps
    r = score_case(
        CASE, [_pred("soy muy cansado", 3, "Estoy muy cansado.", ErrorCategory.SER_ESTAR)], 0, 1.0
    )
    assert (r.matched, r.false_positives, r.fix_correct, r.category_correct) == (1, 0, 1, 1)
    assert r.passed
    assert score_case(CASE, [p], 0, 1.0).fix_correct == 0


def test_alt_fix_is_accepted_and_wrong_category_still_matches() -> None:
    p = _pred("soy muy cansado", 3, "estoy cansado", ErrorCategory.GRAMMAR)
    r = score_case(CASE, [p], 0, 1.0)
    assert (r.fix_correct, r.category_correct) == (1, 0)


def test_miss_and_false_positive() -> None:
    assert not score_case(CASE, [], 0, 1.0).passed
    r = score_case(CLEAN, [_pred("Estoy", 0, "Soy", ErrorCategory.SER_ESTAR)], 0, 1.0)
    assert (r.false_positives, r.passed) == (1, False)


def test_aggregate_metrics() -> None:
    results = [
        score_case(
            CASE,
            [_pred("soy muy cansado", 3, "estoy muy cansado", ErrorCategory.SER_ESTAR)],
            1,
            1.0,
        ),
        score_case(CLEAN, [_pred("Estoy", 0, "Soy", ErrorCategory.SER_ESTAR)], 0, 3.0),
        score_case(CLEAN, [], 0, 2.0),
    ]
    m = aggregate(results)
    assert m.recall == 1.0
    assert m.clean_pass_rate == 0.5
    assert abs(m.false_positive_rate - 1 / 3) < 1e-9
    assert abs(m.locate_drop_rate - 1 / 3) < 1e-9
    assert m.latency_p50 == 2.0 and m.latency_p95 == 3.0


def test_fold_ignores_case_whitespace_and_trailing_punctuation() -> None:
    assert fold("  Estoy  Cansado. ") == fold("estoy cansado")


def test_percentile_and_targets() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert meets_target("recall", 0.9) is True
    assert meets_target("false_positive_rate", 0.2) is False
    assert meets_target("category_accuracy", 0.1) is None


def test_runs_merge_to_mean_and_worst_and_cases_must_pass_every_run() -> None:
    good = aggregate([score_case(CLEAN, [], 0, 1.0)])
    bad = aggregate([score_case(CLEAN, [_pred("E", 0, "e", ErrorCategory.GRAMMAR)], 0, 1.0)])
    merged = merge_runs([good, bad])
    assert merged["clean_pass_rate"] == {"mean": 0.5, "worst": 0.0}
    runs = [
        [score_case(CLEAN, [], 0, 1.0)],
        [score_case(CLEAN, [_pred("E", 0, "e", ErrorCategory.GRAMMAR)], 0, 1.0)],
    ]
    assert case_passes_every_run(runs) == {"clean": False}
