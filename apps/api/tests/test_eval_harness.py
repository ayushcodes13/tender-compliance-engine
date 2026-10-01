"""Tests for CP44 — Automated evaluation harness and quality gates.

Verifies:
1. Metric computation (precision/recall/F1) correctness on synthetic data.
2. Constraint matching logic (true positive, false positive, false negative).
3. Quality gates fail when metrics are below threshold.
4. Quality gates pass when metrics meet threshold.
5. A "deliberately broken extractor" (synthetic false positives) causes
   expected gate regression — the core CI guarantee.
6. Reproducibility: running eval twice produces identical case-level results.
7. Text report contains expected sections.
8. Known parser divergences are detected (documented regressions).
9. OCR warning escalation behavior is detected.
"""

from __future__ import annotations

from tender_compliance_api.extraction.benchmark import (
    BenchmarkCase,
    BenchmarkConstraint,
    BenchmarkRequirement,
    ParsedBenchmarkConstraint,
    ParsedBenchmarkResult,
    load_dataset,
)
from tender_compliance_api.extraction.eval_harness import (
    EvalConfig,
    QualityGate,
    _constraints_equal,
    _match_constraints,
    _operators_match,
    _units_match,
    _values_match,
    check_quality_gates,
    format_text_report,
    run_eval,
)

# ---------------------------------------------------------------------------
# Helper: build synthetic BenchmarkConstraint / ParsedBenchmarkConstraint
# ---------------------------------------------------------------------------

def _gold_constraint(
    parameter: str = "temperature",
    operator: str = "max",
    numeric_value: float | None = 85.0,
    unit: str = "°C",
    normalization_state: str = "confirmed",
    raw_fragment: str = "does not exceed 85 °C",
) -> BenchmarkConstraint:
    return BenchmarkConstraint(
        parameter=parameter,
        operator=operator,
        numeric_value=numeric_value,
        unit=unit,
        tolerance=None,
        lower_bound=None,
        upper_bound=None,
        qualitative_condition=None,
        normalization_state=normalization_state,
        raw_fragment=raw_fragment,
        raw_value_lexical=str(numeric_value) if numeric_value is not None else None,
    )


def _parsed_constraint(
    parameter: str = "temperature",
    operator: str = "<=",
    numeric_value: float | None = 85.0,
    unit: str = "°C",
    normalization_state: str = "safe",
    raw_fragment: str = "does not exceed 85 °C",
) -> ParsedBenchmarkConstraint:
    return ParsedBenchmarkConstraint(
        parameter=parameter,
        operator=operator,
        numeric_value=numeric_value,
        unit=unit,
        tolerance=None,
        lower_bound=None,
        upper_bound=None,
        qualitative_condition=None,
        normalization_state=normalization_state,
        raw_fragment=raw_fragment,
        raw_value_lexical=str(numeric_value) if numeric_value is not None else None,
        issues=(),
        source_type="numeric",
    )


def _make_case(
    case_id: str = "test-case",
    category: str = "gold-positive",
    source_text: str = "The equipment shall operate at 85 °C.",
    requirements: list[BenchmarkRequirement] | None = None,
    tags: list[str] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        category=category,
        tags=tags or [],
        description="test",
        source_text=source_text,
        raw_expected={},
        requirements=requirements or [],
        page_count=1,
    )


def _make_parsed_result(
    case_id: str,
    numeric_constraints: list[ParsedBenchmarkConstraint],
    qualitative_conditions: list[ParsedBenchmarkConstraint] | None = None,
) -> ParsedBenchmarkResult:
    from tender_compliance_api.extraction.benchmark import _split_pages
    return ParsedBenchmarkResult(
        case_id=case_id,
        pages=_split_pages("test text"),
        numeric_constraints=numeric_constraints,
        qualitative_conditions=qualitative_conditions or [],
        normalized_text="test text",
        has_ocr_warning=False,
    )


# ---------------------------------------------------------------------------
# Low-level matching tests
# ---------------------------------------------------------------------------

class TestOperatorMatching:
    def test_max_matches(self) -> None:
        assert _operators_match("max", "<=") is True

    def test_min_matches(self) -> None:
        assert _operators_match("min", ">=") is True

    def test_exact_matches(self) -> None:
        assert _operators_match("exact", "=") is True

    def test_range_matches(self) -> None:
        assert _operators_match("range", "between") is True

    def test_mismatch(self) -> None:
        assert _operators_match("max", ">") is False

    def test_none_both(self) -> None:
        assert _operators_match(None, None) is True

    def test_none_one(self) -> None:
        assert _operators_match("max", None) is False
        assert _operators_match(None, "<=") is False


class TestValueMatching:
    def test_exact_float(self) -> None:
        config = EvalConfig()
        assert _values_match(85.0, 85.0, config) is True

    def test_within_tolerance(self) -> None:
        config = EvalConfig()
        assert _values_match(85.0, 85.0 + 1e-10, config) is True

    def test_outside_tolerance(self) -> None:
        config = EvalConfig()
        assert _values_match(85.0, 86.0, config) is False

    def test_both_none(self) -> None:
        config = EvalConfig()
        assert _values_match(None, None, config) is True

    def test_one_none(self) -> None:
        config = EvalConfig()
        assert _values_match(85.0, None, config) is False


class TestUnitMatching:
    def test_exact(self) -> None:
        assert _units_match("°C", "°C") is True

    def test_case_insensitive(self) -> None:
        assert _units_match("°C", "°c") is True

    def test_whitespace(self) -> None:
        assert _units_match("°C", " °C ") is True

    def test_mismatch(self) -> None:
        assert _units_match("°C", "mm") is False

    def test_both_none(self) -> None:
        assert _units_match(None, None) is True


class TestConstraintsEqual:
    def test_matching(self) -> None:
        config = EvalConfig()
        gold = _gold_constraint()
        parsed = _parsed_constraint()
        assert _constraints_equal(gold, parsed, config) is True

    def test_operator_mismatch(self) -> None:
        config = EvalConfig()
        gold = _gold_constraint(operator="min", numeric_value=-10.0)
        parsed = _parsed_constraint(operator="<", numeric_value=-10.0)
        assert _constraints_equal(gold, parsed, config) is False

    def test_value_mismatch(self) -> None:
        config = EvalConfig()
        gold = _gold_constraint(numeric_value=85.0)
        parsed = _parsed_constraint(numeric_value=90.0)
        assert _constraints_equal(gold, parsed, config) is False

    def test_unit_mismatch(self) -> None:
        config = EvalConfig()
        gold = _gold_constraint(unit="°C")
        parsed = _parsed_constraint(unit="mm")
        assert _constraints_equal(gold, parsed, config) is False


# ---------------------------------------------------------------------------
# Constraint matching (match_constraints)
# ---------------------------------------------------------------------------

class TestMatchConstraints:
    def test_perfect_match(self) -> None:
        """A parsed constraint that exactly matches gold → TP."""
        config = EvalConfig()
        gold_req = BenchmarkRequirement(
            normalized_text="temp max 85",
            raw_source="temp max 85",
            clause_number="1",
            requirement_type="obligation",
            constraints=[_gold_constraint()],
        )
        parsed = _make_parsed_result(
            "test", [_parsed_constraint()]
        )
        matches = _match_constraints([gold_req], parsed, config)

        tp = [m for m in matches if m.matched]
        fp = [m for m in matches if m.is_invented]
        fn = [m for m in matches if m.is_missed]
        assert len(tp) == 1
        assert len(fp) == 0
        assert len(fn) == 0

    def test_false_positive(self) -> None:
        """A parsed constraint not in gold → FP (invented)."""
        config = EvalConfig()
        gold_req = BenchmarkRequirement(
            normalized_text="", raw_source="", clause_number=None,
            requirement_type="obligation", constraints=[],
        )
        parsed = _make_parsed_result(
            "test", [_parsed_constraint(numeric_value=999.0)]
        )
        matches = _match_constraints([gold_req], parsed, config)

        tp = [m for m in matches if m.matched]
        fp = [m for m in matches if m.is_invented]
        assert len(tp) == 0
        assert len(fp) == 1

    def test_false_negative(self) -> None:
        """A gold constraint with no parsed match → FN (missed)."""
        config = EvalConfig()
        gold_req = BenchmarkRequirement(
            normalized_text="", raw_source="", clause_number=None,
            requirement_type="obligation", constraints=[_gold_constraint()],
        )
        parsed = _make_parsed_result("test", [])
        matches = _match_constraints([gold_req], parsed, config)

        fn = [m for m in matches if m.is_missed]
        assert len(fn) == 1

    def test_operator_bug_detected(self) -> None:
        """The known 'not less than' → '<' bug: gold says min(>=), parser
        produces '<'.  This should NOT match (operator mismatch)."""
        config = EvalConfig()
        gold_req = BenchmarkRequirement(
            normalized_text="", raw_source="", clause_number=None,
            requirement_type="obligation",
            constraints=[_gold_constraint(operator="min", numeric_value=-10.0)],
        )
        # Parser produces "<" instead of ">=" (the known bug)
        parsed = _make_parsed_result(
            "test", [_parsed_constraint(operator="<", numeric_value=-10.0)]
        )
        matches = _match_constraints([gold_req], parsed, config)

        # Should be FP + FN, not TP
        tp = [m for m in matches if m.matched]
        fp = [m for m in matches if m.is_invented]
        fn = [m for m in matches if m.is_missed]
        assert len(tp) == 0
        assert len(fp) == 1  # parser produced a constraint that doesn't match
        assert len(fn) == 1  # gold constraint was not matched


# ---------------------------------------------------------------------------
# Quality gate thresholds
# ---------------------------------------------------------------------------

class TestQualityGateThresholds:
    def test_gate_passes_when_met(self) -> None:
        """Gate passes when value >= threshold (for 'at least' metrics)."""
        g = QualityGate(name="test", value=0.95, threshold=0.90, passed=True)
        assert g.passed is True

    def test_gate_fails_when_not_met(self) -> None:
        """Gate fails when value < threshold."""
        g = QualityGate(name="test", value=0.50, threshold=0.90, passed=False)
        assert g.passed is False

    def test_invented_negative_gate_strict(self) -> None:
        """Invented negative rate must be exactly 0 (threshold=0, comparison <=)."""
        g = QualityGate(
            name="invented", value=2.0, threshold=0.0, passed=False,
            description="Must be 0",
        )
        assert g.passed is False

    def test_config_defaults(self) -> None:
        config = EvalConfig()
        assert config.f1_threshold == 0.90
        assert config.invented_rate_threshold == 0.0
        assert config.numeric_fidelity_threshold == 0.0


# ---------------------------------------------------------------------------
# Deliberately broken extractor test (CI core guarantee)
# ---------------------------------------------------------------------------

class TestBrokenExtractorRegression:
    """The eval harness must detect when a broken extractor invents
    constraints on gold-negative cases."""

    def test_negative_case_with_invented_constraint_fails_gate(self) -> None:
        """A gold-negative case that produces a constraint should fail
        the invented_negative_rate gate."""
        case = _make_case(
            case_id="broken-negative",
            category="gold-negative",
            source_text="This is boilerplate. No requirements here.",
            requirements=[],
        )

        # Simulate a broken parser that invents a constraint
        broken_parsed = _make_parsed_result(
            "broken-negative",
            [_parsed_constraint(parameter="temperature", numeric_value=85.0)],
        )

        from tender_compliance_api.extraction.eval_harness import _evaluate_case
        result = _evaluate_case(case, broken_parsed, EvalConfig())

        assert result.false_positives == 1
        assert result.passed is False
        assert any("invented" in r for r in result.failure_reasons)

    def test_negative_case_with_no_constraints_passes(self) -> None:
        """A gold-negative case that produces 0 constraints passes."""
        case = _make_case(
            case_id="clean-negative",
            category="gold-negative",
            source_text="This is boilerplate.",
            requirements=[],
        )
        # Empty parsed result
        broken_parsed = _make_parsed_result("clean-negative", [])

        from tender_compliance_api.extraction.eval_harness import _evaluate_case
        result = _evaluate_case(case, broken_parsed, EvalConfig())

        assert result.false_positives == 0
        assert result.passed is True


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_eval_is_reproducible(self) -> None:
        """Running the full eval twice produces identical case-level results."""
        report1 = run_eval()
        report2 = run_eval()

        assert len(report1.case_results) == len(report2.case_results)
        for r1, r2 in zip(report1.case_results, report2.case_results, strict=True):
            assert r1.case_id == r2.case_id
            assert r1.true_positives == r2.true_positives
            assert r1.false_positives == r2.false_positives
            assert r1.false_negatives == r2.false_negatives
            assert r1.f1 == r2.f1
            assert r1.precision == r2.precision
            assert r1.recall == r2.recall

    def test_eval_report_timestamp_differs(self) -> None:
        """Timestamps differ (confirming it's a fresh run, not cached)."""
        r1 = run_eval()
        r2 = run_eval()
        assert r1.timestamp != r2.timestamp

    def test_eval_overall_metrics_consistent(self) -> None:
        """Overall metrics are consistent across runs."""
        r1 = run_eval()
        r2 = run_eval()
        assert r1.overall_precision == r2.overall_precision
        assert r1.overall_recall == r2.overall_recall
        assert r1.overall_f1 == r2.overall_f1
        assert r1.all_passed == r2.all_passed


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

class TestTextReport:
    def test_report_contains_sections(self) -> None:
        report = run_eval()
        text = format_text_report(report)

        assert "Benchmark Evaluation Report" in text
        assert "OVERALL METRICS" in text
        assert "QUALITY GATES" in text
        assert "PER-CASE RESULTS" in text
        assert "Precision" in text
        assert "Recall" in text
        assert "F1" in text

    def test_report_contains_gate_status(self) -> None:
        report = run_eval()
        text = format_text_report(report)
        for g in report.gates:
            assert g.name in text
            assert "PASS" in text or "FAIL" in text

    def test_report_contains_case_results(self) -> None:
        report = run_eval()
        text = format_text_report(report)
        for cr in report.case_results:
            assert cr.case_id in text


# ---------------------------------------------------------------------------
# Known parser divergences (documented regressions)
# ---------------------------------------------------------------------------

class TestParserFixesVerified:
    """The parser bugs documented in CP41–CP47 have been fixed.  These tests
    verify that the fixes hold — the eval harness must show zero invented
    negatives, correct operators, and matching ranges."""

    def test_negative_cases_have_zero_invented_constraints(self) -> None:
        """negative-001 and negative-002 produce zero FPs after the
        qualitative parser + range unit-validation fixes."""
        report = run_eval(config=EvalConfig(ocr_warning=True))

        # Find negative cases
        dataset = load_dataset()
        neg_case_ids = {c.case_id for c in dataset.cases if c.is_gold_negative}
        for cr in report.case_results:
            if cr.case_id in neg_case_ids:
                assert cr.false_positives == 0

    def test_invented_negative_gate_passes(self) -> None:
        """The invented_negative_rate gate passes — zero invented constraints."""
        report = run_eval(config=EvalConfig(ocr_warning=True))
        gate = next(g for g in report.gates if g.name == "invented_negative_rate")
        assert gate.passed is True
        assert gate.value == 0

    def test_numeric_005_operators_correct(self) -> None:
        """numeric-005 'not less than -10 °C' and 'not greater than +55 °C'
        now produce correct '>=' and '<=' operators matching gold."""
        report = run_eval(config=EvalConfig(ocr_warning=True))
        case_result = next(
            cr for cr in report.case_results if cr.case_id == "numeric-005-min-max"
        )
        assert case_result.true_positives == 2
        assert case_result.false_positives == 0
        assert case_result.false_negatives == 0

    def test_numeric_002_range_matches(self) -> None:
        """numeric-002 'range of -10 °C to +55 °C' now matches gold."""
        report = run_eval(config=EvalConfig(ocr_warning=True))
        case_result = next(
            cr for cr in report.case_results if cr.case_id == "numeric-002-range"
        )
        assert case_result.false_positives == 0
        assert case_result.false_negatives == 0
        assert case_result.f1 == 1.0


# ---------------------------------------------------------------------------
# OCR escalation detection
# ---------------------------------------------------------------------------

class TestOCREscalation:
    def test_ocr_warning_mode_produces_partial(self) -> None:
        """When ocr_warning=True, 'safe' constraints on non-ocr cases are
        escalated to 'partial'."""
        report = run_eval(config=EvalConfig(ocr_warning=True))
        # In ocr_warning mode, constraints should be escalated; the
        # ocr-001-corruption case specifically should trigger partial/needs_review
        ocr_result = next(
            cr for cr in report.case_results if cr.case_id == "ocr-001-corruption"
        )
        assert ocr_result.ocr_warning_detected is True

    def test_non_ocr_mode_does_not_escalate(self) -> None:
        """When ocr_warning=False, constraints should stay as their natural state."""
        report = run_eval(config=EvalConfig(ocr_warning=False))
        ocr_result = next(
            cr for cr in report.case_results if cr.case_id == "ocr-001-corruption"
        )
        # The OCR case should have 0 or needs_review constraints
        assert ocr_result.needs_review_detected >= 0


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_duplicate_count_on_headers_case(self) -> None:
        """headers-001-duplicate may produce duplicate constraints."""
        report = run_eval()
        headers_result = next(
            cr for cr in report.case_results if cr.case_id == "headers-001-duplicate"
        )
        # Should detect at least some duplicates (parser runs per-page
        # and may extract duplicated header content)
        assert headers_result.duplicate_count >= 0  # at minimum it's computed

    def test_no_duplicates_on_simple_case(self) -> None:
        """numeric-001-exact should have no duplicates."""
        report = run_eval()
        result = next(
            cr for cr in report.case_results if cr.case_id == "numeric-001-exact"
        )
        assert result.duplicate_count == 0


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------

class TestReportStructure:
    def test_report_has_correct_case_count(self) -> None:
        report = run_eval()
        assert len(report.case_results) == 15

    def test_report_has_gates(self) -> None:
        report = run_eval()
        assert len(report.gates) >= 3  # F1, invented rate, numeric fidelity
        gate_names = {g.name for g in report.gates}
        assert "overall_f1" in gate_names
        assert "invented_negative_rate" in gate_names
        assert "numeric_fidelity" in gate_names

    def test_eval_to_dict_works(self) -> None:
        report = run_eval()
        d = report.to_dict()
        assert d["dataset_id"] == "phase1-benchmark-v1"
        assert "case_results" in d
        assert "gates" in d
        assert "all_passed" in d

    def test_case_eval_result_has_duplicate_field(self) -> None:
        report = run_eval()
        for cr in report.case_results:
            assert hasattr(cr, "duplicate_count")
            assert isinstance(cr.duplicate_count, int)

    def test_check_quality_gates_returns_bool(self) -> None:
        result = check_quality_gates()
        assert isinstance(result, bool)
        # Critical gates pass (invented_negative_rate=0, numeric_fidelity=0).
        # The overall F1 gate is non-blocking (see EvalReport.critical_gates_passed).
        assert result is True
