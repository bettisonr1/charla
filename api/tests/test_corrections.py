from app.corrections import locate_corrections
from app.schemas.correction import Correction, CorrectionReport, ErrorCategory, LocatedCorrection
from evals.scoring import Expected, aggregate, score_case


def corr(original: str, corrected: str = "x", cat: str = "grammar") -> Correction:
    return Correction(
        original=original, corrected=corrected, category=ErrorCategory(cat), explanation="e"
    )


def located(start: int, end: int, corrected: str = "x", cat: str = "grammar") -> LocatedCorrection:
    return LocatedCorrection(
        original="o",
        corrected=corrected,
        category=ErrorCategory(cat),
        explanation="e",
        start=start,
        end=end,
    )


def test_locate_exact_and_case_insensitive() -> None:
    res = locate_corrections("Yo soy cansado", CorrectionReport(corrections=[corr("yo soy")]))
    assert (res.located[0].start, res.located[0].end) == (0, 6)
    assert res.located[0].original == "Yo soy"


def test_locate_drops_unfound_and_keeps_longer_overlap() -> None:
    report = CorrectionReport(corrections=[corr("soy"), corr("Yo soy cansado"), corr("invented")])
    res = locate_corrections("Yo soy cansado", report)
    assert [(c.start, c.end) for c in res.located] == [(0, 14)]
    assert res.dropped == 2


def test_locate_normalizes_nfc_and_repeated_uses_first() -> None:
    res = locate_corrections("café y café", CorrectionReport(corrections=[corr("café")]))
    assert (res.located[0].start, res.located[0].end) == (0, 4)


def test_score_clean_and_false_positive() -> None:
    clean = score_case("c", "Hola", [], [located(0, 4)], 0, 0.1)
    assert not clean.passed and clean.n_false_positive == 1


def test_score_match_fix_and_alt() -> None:
    exp = [Expected("soy cansado", "estoy cansado", "ser_estar", ["Estoy  cansada"])]
    msg = "Yo soy cansado"
    ok = score_case("c", msg, exp, [located(3, 14, "estoy cansada", "ser_estar")], 0, 0.1)
    assert ok.passed and ok.n_fix_correct == 1 and ok.n_category_correct == 1
    miss = score_case("c", msg, exp, [], 0, 0.1)
    assert not miss.passed and miss.n_matched == 0


def test_aggregate_metrics() -> None:
    exp = [Expected("soy", "estoy", "ser_estar")]
    a = score_case("a", "Yo soy", exp, [located(3, 6, "estoy", "ser_estar")], 0, 1.0)
    b = score_case("b", "Hola", [], [], 1, 3.0)
    m = aggregate([a, b])
    assert m["recall"] == 1.0 and m["clean_pass_rate"] == 1.0
    assert m["locate_drop_rate"] == 0.5 and m["fix_accuracy"] == 1.0
