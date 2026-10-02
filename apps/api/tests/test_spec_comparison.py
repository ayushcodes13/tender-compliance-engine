"""Tests for the deterministic spec comparison engine (CP53)."""

from __future__ import annotations

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.constraint_parser import (
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.spec_comparison import (
    ComparisonVerdict,
    compare_spec,
    compare_specs,
)
from tender_compliance_api.extraction.vendor_spec import (
    ParsedVendorSpec,
    parse_vendor_specs,
)


def _tc(text: str) -> ParsedConstraint:
    """Parse a single constraint from text."""
    constraints = parse_constraint(text)
    assert constraints, f"Failed to parse constraint from: {text!r}"
    return constraints[0]


def _vs(text: str) -> ParsedVendorSpec:
    """Parse a single vendor spec from text."""
    specs = parse_vendor_specs(text)
    assert specs, f"Failed to parse vendor spec from: {text!r}"
    return specs[0]


class TestUnitNormalization:
    """Unit conversion and dimensional compatibility."""

    def test_same_unit_exact_match(self) -> None:
        tc = _tc("= 50 V")
        vs = _vs("Supply voltage: 50 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH
        assert result.vendor_value == 50
        assert result.tender_unit == "V"
        assert result.vendor_unit == "V"

    def test_cross_unit_conversion_match(self) -> None:
        """1000 mV vs 1 V — must convert and match."""
        tc = _tc("= 1 V")
        vs = _vs("Supply voltage: 1000 mV")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH
        assert result.conversion is not None
        assert "mV" in result.conversion
        assert "V" in result.conversion

    def test_cross_unit_conversion_mismatch(self) -> None:
        """1000 mV vs 2 V — converts to 1 V, mismatches 2 V."""
        tc = _tc("= 2 V")
        vs = _vs("Supply voltage: 1000 mV")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_unit_dimension_mismatch(self) -> None:
        """5 V vs 5 mm — same number, different dimension."""
        tc = _tc("= 5 V")
        vs = _vs("Length: 5 mm")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE
        assert result.comparison_rule == "parameter_mismatch"

    def test_voltage_vs_current_dimension_mismatch(self) -> None:
        """5 V vs 5 A — same number, different dimension."""
        tc = _tc("= 5 V")
        vs = _vs("Current: 5 A")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE
        assert "parameter" in result.comparison_rule or "unit" in result.comparison_rule


class TestParameterMismatch:
    """Parameter/concept must match before comparison."""

    def test_accuracy_vs_resolution_incomparable(self) -> None:
        """Accuracy 0.5 % vs Resolution 0.5 % — same number/unit, different parameter."""
        tc = _tc("accuracy ≥ 0.5 %")
        vs = _vs("Resolution: 0.5 %")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE
        assert "parameter" in result.comparison_rule

    def test_same_parameter_different_unit_ok(self) -> None:
        """Both voltage, different units — should convert not mismatch on parameter."""
        tc = _tc("= 12 V")
        vs = _vs("Supply voltage: 12000 mV")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH
        assert result.conversion is not None


class TestComparisonOperators:
    """Each operator type produces the correct verdict."""

    def test_equal_exact_match(self) -> None:
        tc = _tc("= 25 °C")
        vs = _vs("Temperature: 25 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_equal_exact_mismatch(self) -> None:
        tc = _tc("= 25 °C")
        vs = _vs("Temperature: 30 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_less_than_or_equal_match(self) -> None:
        tc = _tc("≤ 50 V")
        vs = _vs("Supply voltage: 45 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_less_than_or_equal_boundary_match(self) -> None:
        tc = _tc("≤ 50 V")
        vs = _vs("Supply voltage: 50 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_less_than_or_equal_mismatch(self) -> None:
        tc = _tc("≤ 50 V")
        vs = _vs("Supply voltage: 55 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_greater_than_or_equal_match(self) -> None:
        tc = _tc("≥ 99 %")
        vs = _vs("Accuracy: 99.5 %")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_greater_than_or_equal_mismatch(self) -> None:
        tc = _tc("≥ 99 %")
        vs = _vs("Accuracy: 95 %")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_less_than_match(self) -> None:
        tc = _tc("response time < 100 ms")
        vs = _vs("Response time: 50 ms")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_greater_than_mismatch(self) -> None:
        tc = _tc("response time > 100 ms")
        vs = _vs("Response time: 50 ms")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH


class TestRangeComparison:
    """Range (BETWEEN) comparison with containment logic."""

    def test_range_containment_match(self) -> None:
        tc = _tc("between -10 and 55 °C")
        vs = _vs("Operating temperature: 25 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH
        assert result.comparison_rule.startswith("range_containment")

    def test_range_containment_mismatch(self) -> None:
        tc = _tc("temperature range: 0 to 55 °C")
        vs = _vs("Operating temperature: -5 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_range_boundary_match(self) -> None:
        """Value at the exact boundary of a range should match."""
        tc = _tc("temperature range: 0 to 55 °C")
        vs = _vs("Operating temperature: 0 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_range_with_negative_lower_bound(self) -> None:
        """between -10 and 55 °C with vendor at -5 °C — should be within range."""
        tc = _tc("between -10 and 55 °C")
        vs = _vs("Operating temperature: -5 °C")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH


class TestToleranceComparison:
    """Tolerance-aware comparisons."""

    def test_within_tolerance_match(self) -> None:
        tc = _tc("= 5 V ± 0.5 V")
        vs = _vs("Supply voltage: 5.3 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_outside_tolerance_mismatch(self) -> None:
        tc = _tc("= 5 V ± 0.5 V")
        vs = _vs("Supply voltage: 6 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_exact_tolerance_boundary(self) -> None:
        """Value exactly at tolerance boundary should match (≤)."""
        tc = _tc("= 5 V ± 0.5 V")
        vs = _vs("Supply voltage: 5.5 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH


class TestQualitativeComparison:
    """Percentage/qualitative specs compared directly without unit conversion."""

    def test_percentage_match(self) -> None:
        tc = _tc("= 95 %")
        vs = _vs("Accuracy: 95 %")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_percentage_mismatch(self) -> None:
        tc = _tc("= 95 %")
        vs = _vs("Accuracy: 90 %")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH


class TestNoFabrication:
    """Comparison must never fabricate a result."""

    def test_uncertain_tender_state_incomparable(self) -> None:
        """Tender constraint with PARTIAL state (non-tolerance issue) → INCOMPARABLE."""
        tc = _tc("= 5 V")
        vs = _vs("Supply voltage: 5 V")
        # Force PARTIAL state with a non-tolerance issue
        tc_partial = ParsedConstraint(
            parameter=tc.parameter,
            operator=tc.operator,
            numeric_value=tc.numeric_value,
            lower_bound=tc.lower_bound,
            upper_bound=tc.upper_bound,
            unit=tc.unit,
            tolerance=tc.tolerance,
            raw_fragment=tc.raw_fragment,
            raw_value_lexical=tc.raw_value_lexical,
            normalization_state=ConstraintNormalizationState.PARTIAL,
            issues=("ambiguous_decimal_thousands_separator",),
        )
        result = compare_spec(tc_partial, vs)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE
        assert "uncertain" in result.comparison_rule

    def test_uncertain_vendor_state_incomparable(self) -> None:
        """Vendor spec with PARTIAL state (non-tolerance issue) → INCOMPARABLE."""
        tc = _tc("= 5 V")
        vs = _vs("Supply voltage: 5 V")
        vs_partial = ParsedVendorSpec(
            parameter=vs.parameter,
            entity=vs.entity,
            value=vs.value,
            lower_bound=vs.lower_bound,
            upper_bound=vs.upper_bound,
            unit=vs.unit,
            tolerance=vs.tolerance,
            qualitative_statement=vs.qualitative_statement,
            conditions=vs.conditions,
            source_text=vs.source_text,
            source_page_number=vs.source_page_number,
            char_start=vs.char_start,
            char_end=vs.char_end,
            ocr_confidence=vs.ocr_confidence,
            location_type=vs.location_type,
            extraction_method=vs.extraction_method,
            extraction_version=vs.extraction_version,
            normalization_state=ConstraintNormalizationState.PARTIAL,
            issues=("ocr_warning",),
        )
        result = compare_spec(tc, vs_partial)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE
        assert "uncertain" in result.comparison_rule

    def test_missing_vendor_value_incomparable(self) -> None:
        """Vendor spec with None value → INCOMPARABLE (not mismatch)."""
        tc = _tc("= 5 V")
        vs = _vs("Supply voltage: 5 V")
        vs_no_val = ParsedVendorSpec(
            parameter=vs.parameter,
            entity=vs.entity,
            value=None,  # No numeric value
            lower_bound=vs.lower_bound,
            upper_bound=vs.upper_bound,
            unit=vs.unit,
            tolerance=vs.tolerance,
            qualitative_statement=vs.qualitative_statement,
            conditions=vs.conditions,
            source_text=vs.source_text,
            source_page_number=vs.source_page_number,
            char_start=vs.char_start,
            char_end=vs.char_end,
            ocr_confidence=vs.ocr_confidence,
            location_type=vs.location_type,
            extraction_method=vs.extraction_method,
            extraction_version=vs.extraction_version,
            normalization_state=vs.normalization_state,
            issues=vs.issues,
        )
        result = compare_spec(tc, vs_no_val)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE

    def test_qualitative_vs_numeric_incomparable(self) -> None:
        """Percentage requirement vs a numeric voltage spec → INCOMPARABLE."""
        tc = _tc("= 95 %")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.INCOMPARABLE


class TestSourceLinkage:
    """Every result preserves source text."""

    def test_source_text_preserved(self) -> None:
        tc = _tc("= 5 V")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert result.tender_text == tc.raw_fragment
        assert result.vendor_text == vs.source_text

    def test_reasons_populated(self) -> None:
        tc = _tc("= 10 V")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert len(result.reasons) > 0
        assert all(isinstance(r, str) for r in result.reasons)


class TestDeterminism:
    """Same inputs always produce same outputs."""

    def test_same_input_same_output(self) -> None:
        tc = _tc("≤ 50 V")
        vs = _vs("Supply voltage: 45 V")
        r1 = compare_spec(tc, vs)
        r2 = compare_spec(tc, vs)
        assert r1.verdict == r2.verdict
        assert r1.comparison_rule == r2.comparison_rule
        assert r1.reasons == r2.reasons

    def test_compare_specs_alias(self) -> None:
        """compare_specs should produce same result as compare_spec."""
        tc = _tc("= 12 V")
        vs = _vs("Supply voltage: 12000 mV")
        r1 = compare_spec(tc, vs)
        r2 = compare_specs(tc, vs)
        assert r1.verdict == r2.verdict
        assert r1.comparison_rule == r2.comparison_rule


class TestWrongMetricSameNumber:
    """Adversarial: same number, different metric must not pass."""

    def test_same_number_wrong_dimension(self) -> None:
        """5 V vs 5 mm — must be INCOMPARABLE, not MATCH."""
        tc = _tc("= 5 V")
        vs = _vs("Length: 5 mm")
        result = compare_spec(tc, vs)
        assert result.verdict != ComparisonVerdict.MATCH
        assert result.verdict == ComparisonVerdict.INCOMPARABLE

    def test_same_number_wrong_parameter(self) -> None:
        """100 ms vs 100 Hz — same number, different parameter."""
        tc = _tc("= 100 ms")
        vs = _vs("Frequency: 100 Hz")
        result = compare_spec(tc, vs)
        assert result.verdict != ComparisonVerdict.MATCH
        assert result.verdict == ComparisonVerdict.INCOMPARABLE


class TestBoundaryEquality:
    """Boundary values are included in the compliant range (inclusive by default)."""

    def test_less_than_equal_at_boundary(self) -> None:
        tc = _tc("≤ 50 V")
        vs = _vs("Supply voltage: 50 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_greater_than_equal_at_boundary(self) -> None:
        tc = _tc("≥ 5 V")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MATCH

    def test_less_than_at_boundary_excluded(self) -> None:
        """Strict < — value at the boundary should NOT match."""
        tc = _tc("Supply voltage < 50 V")
        vs = _vs("Supply voltage: 50 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH

    def test_greater_than_at_boundary_excluded(self) -> None:
        """Strict > — value at the boundary should NOT match."""
        tc = _tc("Supply voltage > 5 V")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert result.verdict == ComparisonVerdict.MISMATCH


class TestConversionExplanation:
    """Every numeric outcome explains the conversion and comparison rule."""

    def test_match_explains_conversion(self) -> None:
        tc = _tc("= 1 V")
        vs = _vs("Supply voltage: 1000 mV")
        result = compare_spec(tc, vs)
        assert result.conversion is not None
        assert "mV" in result.conversion
        assert "V" in result.conversion

    def test_same_unit_no_conversion(self) -> None:
        tc = _tc("= 5 V")
        vs = _vs("Supply voltage: 5 V")
        result = compare_spec(tc, vs)
        assert result.conversion is None
        assert result.comparison_rule == "exact"

    def test_details_populated(self) -> None:
        tc = _tc("= 5 V ± 0.5 V")
        vs = _vs("Supply voltage: 4.8 V")
        result = compare_spec(tc, vs)
        assert result.details is not None
        assert "tolerance" in result.details
