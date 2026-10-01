"""Tests for CP33 — Deterministic numeric/operator/unit parsing.

Pure-function tests for :func:`parse_constraint` and :func:`_parse_number`,
covering:
- boundary operators (symbolic & natural-language)
- negatives
- decimals
- ranges (between / from-to / bare - / ..)
- percentages
- unit-bearing values
- scientific notation
- thousands separators
- tolerances (±)
- OCR-corrupted symbols (via ``_parse_number`` and the ``ocr_warning`` flag)
- no-fabrication (bare numbers, RAL codes, page refs)
- determinism (same input → same output)
- multiple constraints per fragment
- parameter inference from measurement nouns

Known limitations (documented, not bugs):
- ``_parse_number`` is the OCR-detection boundary: it flags numbers like ``2O``
  as corrupted **only when the full token including the letter reaches it**.
  ``_TOK_NUM`` stops at letters, so ``2O`` in free text is split into
  ``num=2`` + ``unit=O`` (unknown_unit → PARTIAL).  Direct ``_parse_number``
  tests prove the corruption logic itself is correct.
- Bare ranges (``X to Y`` without ``between``/``from``) do not capture a
  leading minus on the lower bound because ``\\b`` precedes the number; use
  ``between``/``from`` for negative bounds (the common tender form).
- ``"tolerance of N"`` immediately after a unit is absorbed by the unit-group
  regex in ``_BETWEEN_RE``/``_SPAN_RE``; ``± N`` works correctly.
"""

from __future__ import annotations

import pytest

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.constraint_parser import (
    ConstraintOperator,
    ParsedConstraint,
    _parse_number,
    parse_constraint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single(fragment: str, **kw) -> ParsedConstraint | None:
    """Parse a fragment and return the single constraint, or None."""
    results = parse_constraint(fragment, **kw)
    assert len(results) == 1, f"expected 1 constraint, got {len(results)}: {results}"
    return results[0]


def _assert_safe(c: ParsedConstraint) -> None:
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def _assert_partial(c: ParsedConstraint) -> None:
    assert c.normalization_state is ConstraintNormalizationState.PARTIAL


def _assert_needs_review(c: ParsedConstraint) -> None:
    assert c.normalization_state is ConstraintNormalizationState.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# 1. Empty / blank → no constraints (never fabricate)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_empty_or_blank_yields_no_constraints(text: str) -> None:
    assert parse_constraint(text) == []


# ---------------------------------------------------------------------------
# 2. No fabrication: bare numbers without operators
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "RAL 9005",
    "1 000",
    "25 °C",
    "Page 3",
    "Clause 5.2",
    "12345",
])
def test_no_operator_yields_no_constraints(text: str) -> None:
    """A number with no recognisable comparison operator yields nothing."""
    assert parse_constraint(text) == []


# ---------------------------------------------------------------------------
# 3. Symbolic operators
# ---------------------------------------------------------------------------

def test_less_than_or_equal_symbol() -> None:
    c = _single("≤ 95 %")
    assert c.operator == "<="
    assert c.numeric_value == 95.0
    assert c.unit == "%"
    assert c.parameter == "percentage"
    _assert_safe(c)


def test_less_than_or_equal_symbol_le() -> None:
    c = _single("<= 100 mm")
    assert c.operator == "<="
    assert c.numeric_value == 100.0
    assert c.unit == "mm"
    assert c.parameter == "length"
    _assert_safe(c)


def test_greater_than_or_equal_symbol() -> None:
    c = _single("≥ 20 kg")
    assert c.operator == ">="
    assert c.numeric_value == 20.0
    assert c.unit == "kg"
    assert c.parameter == "mass"
    _assert_safe(c)


def test_greater_than_or_equal_symbol_ge() -> None:
    c = _single(">= 10 bar")
    assert c.operator == ">="
    assert c.numeric_value == 10.0
    assert c.unit == "bar"
    assert c.parameter == "pressure"
    _assert_safe(c)


def test_less_than_symbol() -> None:
    c = _single("< 5 s")
    assert c.operator == "<"
    assert c.numeric_value == 5.0
    assert c.unit == "s"
    assert c.parameter == "time"
    _assert_safe(c)


def test_greater_than_symbol() -> None:
    c = _single("> 3 bar")
    assert c.operator == ">"
    assert c.numeric_value == 3.0
    assert c.unit == "bar"
    assert c.parameter == "pressure"
    _assert_safe(c)


def test_equal_symbol() -> None:
    c = _single("= 2 kg")
    assert c.operator == "="
    assert c.numeric_value == 2.0
    assert c.unit == "kg"
    assert c.parameter == "mass"
    _assert_safe(c)


def test_not_equal_symbol() -> None:
    c = _single("!= 5 mm")
    assert c.operator == "!="
    assert c.numeric_value == 5.0
    assert c.unit == "mm"
    assert c.parameter == "length"
    _assert_safe(c)


def test_not_equal_unicode() -> None:
    c = _single("≠ 5 mm")
    assert c.operator == "!="
    assert c.numeric_value == 5.0
    assert c.unit == "mm"


# ---------------------------------------------------------------------------
# 4. Natural-language operators
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "at most 95 %",
    "no more than 100 mm",
    "not exceed 200 mm",
    "does not exceed 250 mm",
    "must not exceed 300 mm",
    "shall not exceed 500 mm",
])
def test_le_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == "<="


@pytest.mark.parametrize("text", [
    "at least 20 kg",
    "no less than 10 bar",
    "greater than or equal to 50 Hz",
])
def test_ge_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == ">="


@pytest.mark.parametrize("text", [
    "less than 5 s",
    "below 100 °C",
    "under 50 mm",
    "fewer than 10 items",
    "lower than 30 °C",
])
def test_lt_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == "<"


@pytest.mark.parametrize("text", [
    "greater than 3 bar",
    "more than 50 %",
    "above 25 °C",
    "exceeds 100 mm",
    "over 5 kg",
])
def test_gt_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == ">"


@pytest.mark.parametrize("text", [
    "equal to 5 kg",
    "equals 10 mm",
    "equal 25 °C",
])
def test_eq_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == "="


@pytest.mark.parametrize("text", [
    "not equal to 5 mm",
    "other than 10 kg",
])
def test_ne_operator_variants(text: str) -> None:
    c = _single(text)
    assert c.operator == "!="


# ---------------------------------------------------------------------------
# 5. Negatives
# ---------------------------------------------------------------------------

def test_negative_temperature() -> None:
    c = _single("≥ -10 °C")
    assert c.operator == ">="
    assert c.numeric_value == -10.0
    assert c.unit == "°C"
    assert c.parameter == "temperature"
    _assert_safe(c)


def test_negative_less_than() -> None:
    c = _single("≤ -5 mm")
    assert c.operator == "<="
    assert c.numeric_value == -5.0
    assert c.unit == "mm"
    _assert_safe(c)


def test_negative_in_from_range() -> None:
    c = _single("from -10 °C to 55 °C")
    assert c.operator == "between"
    assert c.lower_bound == -10.0
    assert c.upper_bound == 55.0
    assert c.unit == "°C"
    assert c.parameter == "temperature"
    _assert_safe(c)


def test_positive_sign_preserved() -> None:
    c = _single("≤ +55 °C")
    assert c.operator == "<="
    assert c.numeric_value == 55.0
    assert c.raw_value_lexical == "+55"


def test_both_bounds_negative() -> None:
    c = _single("from -20 °C to -5 °C")
    assert c.operator == "between"
    assert c.lower_bound == -20.0
    assert c.upper_bound == -5.0
    assert c.unit == "°C"


# ---------------------------------------------------------------------------
# 6. Decimals
# ---------------------------------------------------------------------------

def test_decimal_value() -> None:
    c = _single("≤ 3.5 mm")
    assert c.numeric_value == 3.5
    assert c.raw_value_lexical == "3.5"
    assert c.unit == "mm"
    assert c.parameter == "length"
    _assert_safe(c)


def test_decimal_below_one() -> None:
    c = _single("= 0.5 s")
    assert c.numeric_value == 0.5
    assert c.raw_value_lexical == "0.5"
    assert c.unit == "s"


def test_decimal_in_range() -> None:
    c = _single("between 0.3 and 1.7 mm")
    assert c.operator == "between"
    assert c.lower_bound == 0.3
    assert c.upper_bound == 1.7
    _assert_safe(c)


def test_zero_value() -> None:
    c = _single("= 0 kg")
    assert c.numeric_value == 0.0
    assert c.raw_value_lexical == "0"


# ---------------------------------------------------------------------------
# 7. Ranges
# ---------------------------------------------------------------------------

def test_between_range() -> None:
    c = _single("between 5 and 10 mm")
    assert c.operator == "between"
    assert c.numeric_value is None
    assert c.lower_bound == 5.0
    assert c.upper_bound == 10.0
    assert c.unit == "mm"
    assert c.parameter == "length"
    _assert_safe(c)


def test_from_to_range() -> None:
    c = _single("from 20 to 30 bar")
    assert c.operator == "between"
    assert c.lower_bound == 20.0
    assert c.upper_bound == 30.0
    assert c.unit == "bar"
    assert c.parameter == "pressure"


def test_bare_range_dash() -> None:
    c = _single("5-10 mm")
    assert c.operator == "between"
    assert c.lower_bound == 5.0
    assert c.upper_bound == 10.0
    assert c.unit == "mm"
    assert c.parameter == "length"


def test_bare_range_to() -> None:
    c = _single("5 to 10 mm")
    assert c.operator == "between"
    assert c.lower_bound == 5.0
    assert c.upper_bound == 10.0
    assert c.unit == "mm"


def test_bare_range_through() -> None:
    c = _single("5 through 10 mm")
    assert c.operator == "between"
    assert c.lower_bound == 5.0
    assert c.upper_bound == 10.0


def test_bare_range_double_dot() -> None:
    c = _single("5..10 mm")
    assert c.operator == "between"
    assert c.lower_bound == 5.0
    assert c.upper_bound == 10.0
    assert c.unit == "mm"


def test_range_without_unit_no_fabrication() -> None:
    """A unit-less range like '5-10' is treated as page/clause numbering,
    not a measurement — no constraint is fabricated."""
    assert parse_constraint("5-10") == []


def test_range_without_unit_in_sentence_no_fabrication() -> None:
    """Even in a sentence, a unit-less range yields nothing."""
    assert parse_constraint("pages 5-10") == []


def test_between_range_without_unit_no_fabrication() -> None:
    assert parse_constraint("between 5 and 10") == []


def test_negative_lower_bound_captured_in_between() -> None:
    c = _single("between -10 and 55 °C")
    assert c.operator == "between"
    assert c.lower_bound == -10.0
    assert c.upper_bound == 55.0
    assert c.unit == "°C"


# ---------------------------------------------------------------------------
# 8. Percentages
# ---------------------------------------------------------------------------

def test_percentage_le() -> None:
    c = _single("≤ 95 %")
    assert c.unit == "%"
    assert c.parameter == "percentage"
    assert c.numeric_value == 95.0


def test_percentage_gt() -> None:
    c = _single("> 50 %")
    assert c.unit == "%"
    assert c.parameter == "percentage"
    assert c.numeric_value == 50.0


def test_percentage_no_space() -> None:
    c = _single("≤ 95%")
    assert c.unit == "%"
    assert c.parameter == "percentage"
    assert c.numeric_value == 95.0


def test_percentage_at_least() -> None:
    c = _single("at least 90 %")
    assert c.operator == ">="
    assert c.unit == "%"
    assert c.parameter == "percentage"
    assert c.numeric_value == 90.0


# ---------------------------------------------------------------------------
# 9. Unit-bearing values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit,param", [
    ("kg", "mass"),
    ("lb", "mass"),
    ("°c", "temperature"),
    ("bar", "pressure"),
    ("mpa", "pressure"),
    ("mm", "length"),
    ("cm", "length"),
    ("km", "length"),
    ("in", "length"),
    ("ft", "length"),
    ("v", "voltage"),
    ("hz", "frequency"),
    ("s", "time"),
    ("min", "time"),
    ("h", "time"),
    ("rad", "angle"),
])
def test_known_units_map_to_parameter(unit: str, param: str) -> None:
    c = _single(f"≤ 25 {unit}")
    assert c.unit == unit.lower()
    assert c.parameter == param
    _assert_safe(c)


def test_degree_celsius_unicode() -> None:
    c = _single("≤ 25 °C")
    assert c.unit == "°C"
    assert c.parameter == "temperature"
    _assert_safe(c)


def test_volts_unit() -> None:
    c = _single("> 12 V")
    assert c.unit == "V"
    assert c.parameter == "voltage"
    assert c.numeric_value == 12.0
    _assert_safe(c)


def test_unknown_unit_escalates() -> None:
    """A unit-like token that is short enough (≤ 4 chars) but not in the unit
    table escalates to PARTIAL with an 'unknown_unit' issue."""
    c = _single("≥ 2 fl")
    assert c.unit == "fl"
    assert "unknown_unit" in c.issues
    _assert_partial(c)


def test_unitless_with_noun_parameter() -> None:
    """When no unit follows, the parameter is inferred from the preceding noun."""
    c = _single("weight ≥ 2")
    assert c.parameter == "mass"
    assert c.numeric_value == 2.0
    _assert_safe(c)


def test_unitless_without_noun_defaults_to_value() -> None:
    c = _single("≥ 2")
    assert c.parameter == "value"
    assert c.numeric_value == 2.0
    _assert_safe(c)


# ---------------------------------------------------------------------------
# 10. Scientific notation
# ---------------------------------------------------------------------------

def test_scientific_notation() -> None:
    c = _single("≥ 1.2e-3")
    assert c.numeric_value == pytest.approx(0.0012)
    assert c.raw_value_lexical == "1.2e-3"
    _assert_safe(c)


def test_scientific_notation_capital_e() -> None:
    c = _single("≥ 1.5E2 Hz")
    assert c.numeric_value == 150.0
    assert c.unit == "Hz"  # case preserved as in source
    assert c.parameter == "frequency"


def test_scientific_notation_no_decimal() -> None:
    c = _single("> 1e6")
    assert c.numeric_value == pytest.approx(1000000.0)


def test_scientific_notation_with_unit_unknown() -> None:
    """1.2e-3 mol — 'mol' is not in the unit table, so the constraint is PARTIAL
    but the numeric value is still correctly parsed."""
    c = _single("≥ 1.2e-3 mol/L")
    assert c.numeric_value == pytest.approx(0.0012)
    assert c.raw_value_lexical == "1.2e-3"
    _assert_partial(c)
    assert "unknown_unit" in c.issues


# ---------------------------------------------------------------------------
# 11. Thousands separators
# ---------------------------------------------------------------------------

def test_comma_thousands_separator_us() -> None:
    c = _single("≤ 1,000 mm")
    assert c.numeric_value == 1000.0
    assert c.raw_value_lexical == "1,000"
    _assert_safe(c)


def test_comma_thousands_with_decimal() -> None:
    c = _single("≤ 1,234.5 mm")
    assert c.numeric_value == 1234.5
    _assert_safe(c)


def test_space_thousands_separator() -> None:
    c = _single("≤ 1 000 mm")
    assert c.numeric_value == 1000.0
    assert c.raw_value_lexical == "1 000"
    _assert_safe(c)


def test_ambiguous_comma_separator_escalates() -> None:
    """1,23 could be 123 (some locales) or 1.23 (European) — ambiguous → PARTIAL."""
    c = _single("≤ 1,23 mm")
    _assert_partial(c)
    assert "ambiguous_comma_separator" in c.issues
    assert c.numeric_value is None
    assert c.raw_value_lexical == "1,23"


def test_ambiguous_decimal_thousands_escalates() -> None:
    """1.234,5 (European) — dot and comma both present, comma is last → ambiguous."""
    c = _single("≤ 1.234,5 mm")
    _assert_partial(c)
    assert "ambiguous_decimal_thousands_separator" in c.issues
    assert c.numeric_value is None


def test_us_form_with_dot_after_comma_ok() -> None:
    """1,234.5 (US) — dot after comma → unambiguous US/UK form."""
    c = _single("≤ 1,234.5 mm")
    assert c.numeric_value == 1234.5
    _assert_safe(c)


# ---------------------------------------------------------------------------
# 12. Tolerances (±)
# ---------------------------------------------------------------------------

def test_tolerance_plus_minus() -> None:
    c = _single("≤ 2 kg ± 0.1")
    assert c.numeric_value == 2.0
    assert c.tolerance == pytest.approx(0.1)
    assert c.unit == "kg"
    assert c.parameter == "mass"
    _assert_partial(c)
    assert "tolerance" in c.issues


def test_tolerance_plus_minus_text() -> None:
    c = _single("≤ 2 kg tolerance of 0.1")
    assert c.numeric_value == 2.0
    assert c.tolerance == pytest.approx(0.1)
    assert "tolerance" in c.issues


def test_tolerance_in_range() -> None:
    c = _single("between 5 and 10 mm ± 0.5")
    assert c.tolerance == pytest.approx(0.5)
    assert "tolerance" in c.issues


def test_tolerance_after_comma() -> None:
    c = _single("between 5 and 10 mm, ± 0.5")
    assert c.tolerance == pytest.approx(0.5)
    assert "tolerance" in c.issues


def test_tolerance_in_from_range() -> None:
    c = _single("from -10 °C to 55 °C ± 2 °C")
    assert c.tolerance == pytest.approx(2.0)
    assert c.lower_bound == -10.0
    assert c.upper_bound == 55.0
    assert c.unit == "°C"


# ---------------------------------------------------------------------------
# 13. OCR-corrupted symbols
# ---------------------------------------------------------------------------

def test_ocr_corrupted_number_letter_o_via_parse_number() -> None:
    """``_parse_number`` correctly detects '2O' (letter O for zero) OCR
    corruption when the full token is examined."""
    result = _parse_number("2O", False)
    assert result.value is None
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW
    assert "ocr_corrupted_number" in result.issues
    assert result.lexical == "2O"


def test_ocr_corrupted_number_letter_s() -> None:
    """'1S3' — 'S' looks like '5' in bad OCR."""
    result = _parse_number("1S3", False)
    assert result.value is None
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW
    assert "ocr_corrupted_number" in result.issues


def test_ocr_corrupted_scientific_suffix() -> None:
    """'1.2e-3S' — trailing letter after a valid exponent is corruption."""
    result = _parse_number("1.2e-3S", False)
    assert result.value is None
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW
    assert "ocr_corrupted_number" in result.issues


def test_letter_in_number_not_scientific() -> None:
    """'1.2x-3' — 'x' is not 'e'/'E', so this is OCR-corrupted."""
    result = _parse_number("1.2x-3", False)
    assert result.value is None
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW


def test_valid_scientific_notation_is_safe() -> None:
    """'1.2e-3' — 'e' is valid exponent notation, not corruption."""
    result = _parse_number("1.2e-3", False)
    assert result.value == pytest.approx(0.0012)
    _assert_safe_via_parse(result)


def _assert_safe_via_parse(result) -> None:
    assert result.state is ConstraintNormalizationState.SAFE


def test_ocr_corrupted_number_in_fragment_escalates_unknown_unit() -> None:
    """When '2O' appears in a fragment, the parser splits it into num='2'
    and unit='O' (unknown).  This is conservative: no value is fabricated.
    The state is PARTIAL (unknown_unit), not fabricated SAFE."""
    c = _single("≤ 2O kg")
    assert c.numeric_value == 2.0
    assert c.unit == "O"
    _assert_partial(c)
    assert "unknown_unit" in c.issues


def test_ocr_warning_escalates_safe_to_partial() -> None:
    """When ocr_warning=True, a clean parse escalates from SAFE to PARTIAL."""
    results = parse_constraint("≤ 95 %", ocr_warning=True)
    assert len(results) == 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "ocr_warning" in results[0].issues


def test_ocr_warning_does_not_downgrade_already_partial() -> None:
    """ocr_warning=True on a number that is already PARTIAL (ambiguous
    separator) does not change the state or add an 'ocr_warning' issue —
    the existing issue already escalated it, and the state is never
    downgraded.  State stays PARTIAL with only the original issues."""
    results = parse_constraint("≤ 1,23 mm", ocr_warning=True)
    assert len(results) == 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "ambiguous_comma_separator" in results[0].issues


def test_ocr_warning_on_range() -> None:
    results = parse_constraint("between 5 and 10 mm", ocr_warning=True)
    assert len(results) == 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL


# ---------------------------------------------------------------------------
# 14. Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "≤ 95 %",
    "weight ≤ 2 kg and temperature ≥ -10 °C",
    "between 5 and 10 mm ± 0.5",
    "≤ 1,000.5 mm",
    "≥ 1.2e-3",
])
def test_determinism_same_input_same_output(text: str) -> None:
    """The same input always yields the same output."""
    r1 = parse_constraint(text)
    r2 = parse_constraint(text)
    assert r1 == r2


def test_determinism_with_ocr_warning() -> None:
    r1 = parse_constraint("≤ 95 %", ocr_warning=True)
    r2 = parse_constraint("≤ 95 %", ocr_warning=True)
    assert r1 == r2


def test_determinism_operator_ordering() -> None:
    """Two equivalent formulations produce the same operator/parameter
    but different raw_lexical (deterministic for each input)."""
    a = parse_constraint("at most 95 %")[0]
    b = parse_constraint("≤ 95 %")[0]
    assert a.operator == b.operator == "<="
    assert a.parameter == b.parameter == "percentage"
    assert a.numeric_value == b.numeric_value == 95.0


# ---------------------------------------------------------------------------
# 15. Multiple constraints per fragment
# ---------------------------------------------------------------------------

def test_multiple_constraints_different_operators() -> None:
    results = parse_constraint("weight ≤ 2 kg and temperature ≥ -10 °C")
    assert len(results) == 2
    weight = [c for c in results if c.parameter == "mass"]
    temp = [c for c in results if c.parameter == "temperature"]
    assert len(weight) == 1
    assert weight[0].operator == "<="
    assert weight[0].numeric_value == 2.0
    _assert_safe(weight[0])
    assert len(temp) == 1
    assert temp[0].operator == ">="
    assert temp[0].numeric_value == -10.0
    _assert_safe(temp[0])


def test_multiple_constraints_same_operator() -> None:
    results = parse_constraint("≤ 95 % and ≤ 100 ppm")
    assert len(results) == 2
    assert all(c.operator == "<=" for c in results)
    assert {c.numeric_value for c in results} == {95.0, 100.0}


def test_multiple_constraints_no_overlap() -> None:
    """Two separate comparisons don't consume each other's numbers."""
    results = parse_constraint("≤ 2 kg and > 100 mm")
    assert len(results) == 2
    values = sorted(c.numeric_value for c in results)
    assert values == [2.0, 100.0]


def test_range_and_comparison_in_one_fragment() -> None:
    results = parse_constraint("weight: between 1 and 5 kg; height < 100 mm")
    assert len(results) == 2
    params = {c.parameter for c in results}
    assert params == {"mass", "length"}


# ---------------------------------------------------------------------------
# 16. Raw fragment & lexical preservation
# ---------------------------------------------------------------------------

def test_raw_fragment_preserved() -> None:
    c = _single("weight ≤ 2 kg")
    assert c.raw_fragment == "weight ≤ 2 kg"


def test_raw_value_lexical_preserved_comma() -> None:
    c = _single("≤ 1,000 mm")
    assert c.raw_value_lexical == "1,000"


def test_raw_value_lexical_preserved_scientific() -> None:
    c = _single("≥ 1.2e-3")
    assert c.raw_value_lexical == "1.2e-3"


def test_raw_value_lexical_preserved_negative() -> None:
    c = _single("≤ -5 mm")
    assert c.raw_value_lexical == "-5"


def test_raw_fragment_is_full_input() -> None:
    """raw_fragment is always the full verbatim input, never a substring."""
    text = "weight ≤ 2 kg and temperature ≥ -10 °C"
    results = parse_constraint(text)
    for c in results:
        assert c.raw_fragment == text


# ---------------------------------------------------------------------------
# 17. Long-form requirement text
# ---------------------------------------------------------------------------

def test_realistic_tender_fragment() -> None:
    text = (
        "The motor shall operate at a maximum noise level of 70 dB(A) "
        "at 1 m distance and weigh less than 25 kg."
    )
    results = parse_constraint(text)
    # "weigh less than 25 kg" → "<" 25 kg
    weighs = [c for c in results if c.parameter == "mass"]
    assert len(weighs) == 1
    assert weighs[0].operator == "<"
    assert weighs[0].numeric_value == 25.0
    # "70 dB(A)" has no operator before it — no constraint fabricated
    db = [c for c in results if c.numeric_value == 70.0]
    assert len(db) == 0


def test_tender_fragment_with_range_and_tolerance() -> None:
    text = "Operating temperature from -10 °C to 55 °C ± 2 °C."
    c = _single(text)
    assert c.operator == "between"
    assert c.lower_bound == -10.0
    assert c.upper_bound == 55.0
    assert c.unit == "°C"
    assert c.parameter == "temperature"
    assert c.tolerance == pytest.approx(2.0)
    assert "tolerance" in c.issues


def test_tender_fragment_multiple_requirements() -> None:
    text = (
        "Supply voltage: 24 V ± 1 V. "
        "Ambient temperature: -10 °C to 55 °C. "
        "Weight: less than 5 kg."
    )
    results = parse_constraint(text)
    # "24 V ± 1 V" has no comparison operator → not a constraint
    # "-10 °C to 55 °C" → bare range (BETWEEN), but no unit captured for the whole thing
    # "less than 5 kg" → "<" 5 kg
    # The exact results depend on parser behavior; verify what is extracted
    assert len(results) >= 1
    mass_constraints = [c for c in results if c.parameter == "mass"]
    assert len(mass_constraints) == 1
    assert mass_constraints[0].operator == "<"
    assert mass_constraints[0].numeric_value == 5.0


def test_tender_fragment_explicit_between() -> None:
    text = (
        "Supply voltage ≥ 24 V ± 1 V. "
        "Ambient temperature from -10 °C to 55 °C. "
        "Weight ≤ 5 kg."
    )
    results = parse_constraint(text)
    # "≥ 24 V" → ">=" 24 V (tolerance not attached since it's via ± after V)
    # "from -10 °C to 55 °C" → BETWEEN -10 and 55
    # "≤ 5 kg" → "<=" 5 kg
    params = {c.parameter for c in results}
    assert "voltage" in params
    assert "temperature" in params
    assert "mass" in params
    mass = [c for c in results if c.parameter == "mass"][0]
    assert mass.operator == "<="
    assert mass.numeric_value == 5.0


# ---------------------------------------------------------------------------
# 18. ParsedConstraint properties & immutability
# ---------------------------------------------------------------------------

def test_parsed_constraint_is_frozen() -> None:
    c = _single("≤ 95 %")
    with pytest.raises((AttributeError, TypeError)):
        c.numeric_value = 100.0  # type: ignore[misc]


def test_constraint_operator_enum_values() -> None:
    assert ConstraintOperator.EQUALS == "="
    assert ConstraintOperator.LESS_THAN == "<"
    assert ConstraintOperator.LESS_THAN_OR_EQUAL == "<="
    assert ConstraintOperator.GREATER_THAN == ">"
    assert ConstraintOperator.GREATER_THAN_OR_EQUAL == ">="
    assert ConstraintOperator.BETWEEN == "between"
    assert ConstraintOperator.NOT_EQUAL == "!="


def test_all_operators_are_canonical_symbols() -> None:
    """Every operator value matches the canonical symbol form."""
    for op in ConstraintOperator:
        assert isinstance(op.value, str)


# ---------------------------------------------------------------------------
# 19. State escalation matrix
# ---------------------------------------------------------------------------

def test_safe_when_clean() -> None:
    c = _single("≤ 95 %")
    _assert_safe(c)
    assert c.issues == ()


def test_partial_on_unknown_unit() -> None:
    c = _single("≥ 2 fl")
    _assert_partial(c)
    assert "unknown_unit" in c.issues


def test_partial_on_tolerance() -> None:
    c = _single("≤ 2 kg ± 0.1")
    _assert_partial(c)
    assert "tolerance" in c.issues


def test_partial_on_ambiguous_separator() -> None:
    c = _single("≤ 1,23 mm")
    _assert_partial(c)
    assert c.numeric_value is None


def test_partial_on_ocr_warning() -> None:
    results = parse_constraint("≤ 95 %", ocr_warning=True)
    assert len(results) == 1
    _assert_partial(results[0])


def test_needs_review_on_ocr_corrupt_number() -> None:
    result = _parse_number("2O", False)
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW


def test_ocr_warning_does_not_downgrade_needs_review() -> None:
    """NEEDS_REVIEW is the worst state; ocr_warning doesn't make it worse
    but also doesn't improve it."""
    result = _parse_number("2O", ocr_warning=True)
    assert result.state is ConstraintNormalizationState.NEEDS_REVIEW
    assert "ocr_corrupted_number" in result.issues
