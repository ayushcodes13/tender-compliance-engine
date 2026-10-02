"""Tests for CP61 Phase 2 evaluation harness and false-compliance gate.

Covers:
- Phase 2 benchmark dataset loads with expected case count
- run_phase2_eval returns a report with all cases evaluated
- False compliance count is zero (hard invariant)
- Each false-compliance trap case is correctly identified
- False compliance gate (check_phase2_quality_gates) passes
- The eval report is deterministic (same input → same output)
- Individual case assessments match gold standard
"""

from __future__ import annotations

from tender_compliance_api.extraction.phase2_eval import (
    PHASE2_BENCHMARK_CASES,
    Phase2EvalReport,
    check_phase2_quality_gates,
    load_phase2_dataset,
    run_phase2_eval,
)


class TestPhase2Dataset:
    def test_dataset_loads(self):
        dataset = load_phase2_dataset()
        assert len(dataset) > 0

    def test_dataset_has_false_compliance_cases(self):
        dataset = load_phase2_dataset()
        fc_cases = [c for c in dataset if c.false_compliance_risk]
        assert len(fc_cases) >= 5, "Expected at least 5 false-compliance-risk cases"

    def test_dataset_has_true_compliance_cases(self):
        dataset = load_phase2_dataset()
        tc_cases = [
            c for c in dataset
            if not c.false_compliance_risk and c.gold_status.value == "match"
        ]
        assert len(tc_cases) >= 3

    def test_dataset_has_non_compliance_cases(self):
        dataset = load_phase2_dataset()
        nc_cases = [
            c for c in dataset
            if c.gold_status.value == "mismatch"
        ]
        assert len(nc_cases) >= 3

    def test_all_cases_have_unique_ids(self):
        dataset = load_phase2_dataset()
        ids = [c.case_id for c in dataset]
        assert len(ids) == len(set(ids)), "Duplicate case IDs in dataset"

    def test_all_cases_have_descriptions(self):
        dataset = load_phase2_dataset()
        for case in dataset:
            assert case.description, f"Case {case.case_id} has no description"

    def test_all_cases_have_tags(self):
        dataset = load_phase2_dataset()
        for case in dataset:
            assert len(case.tags) > 0, f"Case {case.case_id} has no tags"

    def test_all_cases_have_tender_and_evidence(self):
        dataset = load_phase2_dataset()
        for case in dataset:
            assert case.tender_text, f"Case {case.case_id} has no tender text"
            assert case.evidence_text, f"Case {case.case_id} has no evidence text"


class TestPhase2EvalReport:
    def test_eval_returns_report(self):
        report = run_phase2_eval()
        assert isinstance(report, Phase2EvalReport)

    def test_eval_has_all_cases(self):
        report = run_phase2_eval()
        assert len(report.case_results) == len(PHASE2_BENCHMARK_CASES)

    def test_eval_dataset_size_matches(self):
        report = run_phase2_eval()
        assert report.dataset_size == len(PHASE2_BENCHMARK_CASES)

    def test_no_false_compliance(self):
        """Critical gate: false_compliance_count must be zero."""
        report = run_phase2_eval()
        assert report.false_compliance_count == 0
        assert report.false_compliance_gate_passed is True

    def test_false_compliance_gate_passes(self):
        assert check_phase2_quality_gates() is True

    def test_eval_is_deterministic(self):
        report1 = run_phase2_eval()
        report2 = run_phase2_eval()
        assert report1.false_compliance_count == report2.false_compliance_count
        assert report1.false_non_compliance_count == report2.false_non_compliance_count
        assert report1.overall_accuracy == report2.overall_accuracy

    def test_all_passed_reflects_gate(self):
        report = run_phase2_eval()
        assert report.all_passed == report.critical_gates_passed

    def test_report_has_no_error_on_valid_cases(self):
        report = run_phase2_eval()
        # At least 10 of 12 cases should not have errors.
        no_error = [r for r in report.case_results if r.error is None]
        assert len(no_error) >= 10

    def test_fc_001_exceeds_maximum_is_non_compliant(self):
        """Specific false-compliance trap: 90 °C > 85 °C max must be NON_COMPLIANT."""
        report = run_phase2_eval()
        result = next(r for r in report.case_results if r.case_id == "fc-001-exceeds-maximum")
        assert result.assessed_status == "non_compliant"
        assert result.false_compliance is False

    def test_fc_003_parameter_mismatch(self):
        """Parameter mismatch (humidity vs temperature) must not be COMPLIANT."""
        report = run_phase2_eval()
        result = next(r for r in report.case_results if r.case_id == "fc-003-parameter-mismatch")
        assert result.assessed_status != "compliant"

    def test_fc_005_keyword_only_no_evidence(self):
        """Keyword 'compliant' without numeric evidence must not be COMPLIANT."""
        report = run_phase2_eval()
        result = next(
    r for r in report.case_results
    if r.case_id == "fc-005-keyword-only-no-evidence"
)
        assert result.assessed_status != "compliant"

    def test_fc_007_tolerance_exceeded(self):
        """13.5 V exceeds 12 V ±10% tolerance must be NON_COMPLIANT."""
        report = run_phase2_eval()
        result = next(r for r in report.case_results if r.case_id == "fc-007-tolerance-exceeded")
        assert result.assessed_status == "non_compliant"
        assert result.false_compliance is False

    def test_tc_001_exact_match_is_compliant(self):
        """Exact match (85 °C ≤ 85 °C) must be COMPLIANT."""
        report = run_phase2_eval()
        result = next(r for r in report.case_results if r.case_id == "tc-001-exact-match")
        assert result.assessed_status == "compliant"
        assert result.matched is True

    def test_overall_accuracy_reasonable(self):
        report = run_phase2_eval()
        assert report.overall_accuracy >= 0.85, (
            f"Expected >=85% accuracy, got {report.overall_accuracy}"
        )

    def test_false_compliance_rate_is_zero(self):
        report = run_phase2_eval()
        assert report.false_compliance_rate == 0.0
