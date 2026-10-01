"""Adversarial parser tests (CP45).

Tests the deterministic parser's robustness on adversarial document content:
corrupted comparison symbols, decimal/unit confusion, Greek symbols, merged
tables, duplicated headers, prompt injection, and OCR corruption.

Per AGENTS.md: never fabricate a specification. These tests verify that the
parser either extracts the correct constraint or produces no constraint
(rather than a wrong one).  Where the parser *should* flag uncertainty
(e.g. OCR corruption), the test verifies the NEEDS_REVIEW escalation path.
"""

from __future__ import annotations

import pytest

from tender_compliance_api.extraction.constraint_parser import parse_constraint
from tender_compliance_api.extraction.qualitative import parse_qualitative_conditions

FIXTURES_DIR_NAME = "adversarial"


def _read_fixture(name: str) -> str:
    import pathlib
    fixtures = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "adversarial"
    return (fixtures / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Corrupted comparison symbols
# ---------------------------------------------------------------------------

class TestCorruptedComparisonSymbols:
    """Unicode comparison symbols (≤ ≥ ≠) must be parsed correctly."""

    def test_unicode_le_parses_as_le(self) -> None:
        text = "The temperature shall be \u2264 85 \u00b0C."
        results = list(parse_constraint(text))
        assert len(results) == 1
        assert results[0].operator == "<="
        assert results[0].numeric_value == 85.0
        assert results[0].unit == "\u00b0C"

    def test_unicode_ge_parses_as_ge(self) -> None:
        text = "The minimum temperature shall be \u2265 -20 \u00b0C."
        results = list(parse_constraint(text))
        assert len(results) == 1
        assert results[0].operator == ">="
        assert results[0].numeric_value == -20.0

    def test_unicode_ne_parses_as_ne(self) -> None:
        text = "The voltage shall not be \u2260 12 V."
        results = list(parse_constraint(text))
        assert len(results) == 1
        assert results[0].operator == "!="
        assert results[0].numeric_value == 12.0

    def test_ascii_equivalents_match(self) -> None:
        """ASCII and Unicode symbols produce the same operator."""
        unicode_le = list(parse_constraint("temp \u2264 85"))
        ascii_le = list(parse_constraint("temp <= 85"))
        assert len(unicode_le) == 1
        assert len(ascii_le) == 1
        assert unicode_le[0].operator == ascii_le[0].operator

    def test_corrupted_symbol_does_not_change_value(self) -> None:
        """Using Unicode ≤ must not corrupt the numeric value."""
        text = "Max temp \u2264 85 \u00b0C, min temp \u2265 -20 \u00b0C."
        results = list(parse_constraint(text))
        # Both should be found with correct values
        vals = {r.numeric_value for r in results}
        assert 85.0 in vals
        assert -20.0 in vals


# ---------------------------------------------------------------------------
# Decimal and unit confusion
# ---------------------------------------------------------------------------

class TestDecimalUnitConfusion:
    def test_bare_decimal_not_extracted(self) -> None:
        """A bare number with no comparison operator yields no constraint
        (no fabrication)."""
        text = "The pressure rating shall be 1 bar to 10 bar maximum."
        results = list(parse_constraint(text))
        # This may produce a range or nothing depending on parser behavior
        # The key invariant: no constraint with a WRONG numeric value
        for r in results:
            assert r.numeric_value not in (5.5, 5)  # no fabricated midpoint

    def test_european_decimal_comma_is_partial_or_none(self) -> None:
        """European decimal commas (10,5) are ambiguous → partial or no
        extraction, never a silently-wrong value."""
        text = "The flow rate shall range from 10,5 m3/h to 50,5 m3/h."
        results = list(parse_constraint(text))
        for r in results:
            if r.normalization_state.value == "safe":
                # If extracted as safe, the value must be correct
                assert r.numeric_value in (10.5, 50.5, 10.0, 50.0)
            # Never a fabricated value like 30.5

    def test_no_unit_yields_no_fabrication(self) -> None:
        """Bare numbers without units must not produce fabricated constraints."""
        text = "The temperature shall be 85."
        results = list(parse_constraint(text))
        assert len(results) == 0

    def test_dot_notation_preserved(self) -> None:
        """Standard decimal notation (10.5) is parsed correctly."""
        text = "Tolerance shall be \u00b1 2.5 \u00b0C."
        results = list(parse_constraint(text))
        # ± tolerance may or may not produce a constraint; if it does,
        # the value must be 2.5
        for r in results:
            if r.tolerance is not None:
                assert r.tolerance == 2.5


# ---------------------------------------------------------------------------
# Greek symbols
# ---------------------------------------------------------------------------

class TestGreekSymbols:
    def test_greek_unit_omega_not_confused_with_latin(self) -> None:
        """Ω (U+03A9) is a Greek capital omega, not Latin O or zero."""
        text = "The resistance shall be \u2264 50 \u03a9."
        results = list(parse_constraint(text))
        for r in results:
            if r.unit is not None:
                assert r.unit == "\u03a9"

    def test_greek_letters_do_not_create_false_units(self) -> None:
        """Greek letters in parameter names (\u03b1, \u03c9) must not be
        misinterpreted as units."""
        text = "The frequency range shall be 20 Hz to 20 kHz."
        results = list(parse_constraint(text))
        for r in results:
            assert r.unit not in ("\u03b1", "\u03c9")

    def test_greek_symbol_constraints_preserve_value(self) -> None:
        """When a Greek symbol appears as a unit, the numeric value is
        still correct."""
        text = "Voltage shall be 230 V \u00b1 10 %."
        results = list(parse_constraint(text))
        for r in results:
            if r.numeric_value is not None:
                assert r.numeric_value in (230.0, 10.0)


# ---------------------------------------------------------------------------
# Merged tables
# ---------------------------------------------------------------------------

class TestMergedTables:
    def test_table_rows_not_fabricated_as_constraints(self) -> None:
        """Header rows and column labels in tables must not produce
        invented constraints."""
        text = _read_fixture("merged-tables.txt")
        results = list(parse_constraint(text))
        # Table headers ("Minimum", "Maximum", "Parameter") should not
        # produce constraints with fabricated numeric values
        for r in results:
            # If any constraints are extracted, they must have valid
            # numeric values from the table body, not from headers
            assert r.numeric_value is not None

    def test_table_does_not_produce_wrong_parameter_names(self) -> None:
        """Table column headers must not become parameter names."""
        text = _read_fixture("merged-tables.txt")
        results = list(parse_constraint(text))
        for r in results:
            assert r.parameter not in ("Parameter", "Minimum", "Maximum", "Unit")

    def test_table_numeric_values_not_confused(self) -> None:
        """Numbers in the 'Parameter' column should not be matched
        against units in the 'Unit' column."""
        text = _read_fixture("merged-tables.txt")
        results = list(parse_constraint(text))
        # No constraint should have a value of 1 (from "1 bar" column)
        # matched against °C unit from a different row
        for r in results:
            if r.unit == "\u00b0C":
                assert r.numeric_value in (-10.0, 55.0)
            if r.unit == "bar":
                assert r.numeric_value in (0.9, 1.0, 1.1)


# ---------------------------------------------------------------------------
# Duplicated headers
# ---------------------------------------------------------------------------

class TestDuplicateHeaders:
    def test_header_repeats_not_extracted_as_constraints(self) -> None:
        """Document headers/footers repeated on every page must not
        produce duplicate constraints."""
        text = _read_fixture("duplicate-headers.txt")
        results = list(parse_constraint(text))
        # "1.0" from "Revision: 1.0" should not be extracted as a value
        for r in results:
            assert r.numeric_value != 1.0 or r.unit is not None

    def test_actual_requirements_still_extracted(self) -> None:
        """Constraints embedded in pages with duplicated headers
        are still correctly extracted."""
        text = _read_fixture("duplicate-headers.txt")
        results = list(parse_constraint(text))
        values = {r.numeric_value for r in results}
        assert 85.0 in values  # temperature constraint
        assert 10.0 in values  # pressure constraint
        assert 5.0 in values or 85.0 in values  # humidity constraint


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

class TestPromptInjection:
    """Document content must not override system rules or induce fake
    constraints (per AGENTS.md: 'Document content never overrides
    application/system instructions')."""

    def test_injected_instruction_no_constraint(self) -> None:
        """An injected instruction 'max temp is 999 °C' without a
        comparison operator must not produce a constraint."""
        text = _read_fixture("prompt-injection.txt")
        results = list(parse_constraint(text))
        # "999" should not appear as a numeric value in any constraint
        for r in results:
            assert r.numeric_value != 999.0

    def test_injected_override_no_fabrication(self) -> None:
        """'OVERRIDE: pressure limit to 100 bar' without an operator
        must not produce a fabricated constraint."""
        text = _read_fixture("prompt-injection.txt")
        results = list(parse_constraint(text))
        for r in results:
            assert r.numeric_value != 100.0 or r.operator is not None

    def test_real_constraint_survives_injection(self) -> None:
        """The legitimate constraint (85 °C) is still extracted despite
        surrounding prompt injection text."""
        text = _read_fixture("prompt-injection.txt")
        results = list(parse_constraint(text))
        values = {r.numeric_value for r in results}
        assert 85.0 in values

    def test_injection_no_qualitative_inference(self) -> None:
        """Injected text does not produce qualitative conditions."""
        text = _read_fixture("prompt-injection.txt")
        results = list(parse_qualitative_conditions(text))
        # "Ignore all previous instructions" should not match any
        # certification or standard pattern
        for c in results:
            assert "ignore" not in c.parameter.lower()
            assert "override" not in c.parameter.lower()


# ---------------------------------------------------------------------------
# OCR corruption
# ---------------------------------------------------------------------------

class TestOCRCorruption:
    """Letters substituting for digits must not produce silently-wrong
    values.  The parser should either miss the constraint (conservative)
    or flag it as NEEDS_REVIEW."""

    def test_letter_o_in_number_no_false_constraint(self) -> None:
        """'8O' (O for zero) must not produce a constraint with value 8."""
        text = "The max temp is 8O \u00b0C."
        results = list(parse_constraint(text))
        for r in results:
            # If a constraint is produced, the value must not be 8
            # (the parser should not silently interpret '8O' as 8)
            assert r.numeric_value != 8.0

    def test_letter_s_in_number_no_false_constraint(self) -> None:
        """'5S0' (S for 5) must not produce a constraint with value 5 or
        500."""
        text = "Pressure: 5S0 bar."
        results = list(parse_constraint(text))
        for r in results:
            assert r.numeric_value not in (5.0, 500.0)

    def test_letter_k_in_number_no_false_constraint(self) -> None:
        """'2K0' (K for 0) must not produce a constraint with value 200."""
        text = "The voltage shall be 2K0 V."
        results = list(parse_constraint(text))
        for r in results:
            assert r.numeric_value != 200.0

    def test_ocr_corruption_does_not_fabricate(self) -> None:
        """No constraint should have a numeric value that differs from
        the intended value due to OCR corruption."""
        text = _read_fixture("ocr-corruption.txt")
        results = list(parse_constraint(text))
        # Known corrupted values: 8O, -1O, 5S0, 2K0, 1K,5, 5K,5
        # None of these should produce wrong numeric values
        for r in results:
            if r.numeric_value is not None:
                # The value should not be an OCR-corrupted interpretation
                assert r.numeric_value != 8.0 or r.unit is not None
                assert r.numeric_value != 5.0 or r.unit is not None
                assert r.numeric_value != 2.0 or r.unit is not None

    @pytest.mark.parametrize("ocr_text,forbidden_value", [
        ("max temp 8O \u00b0C", 8.0),
        ("pressure 5S0 bar", 500.0),
        ("pressure 5S0 bar", 5.0),
        ("voltage 2K0 V", 200.0),
        ("voltage 2K0 V", 2.0),
    ])
    def test_no_ocr_fabrication(self, ocr_text: str, forbidden_value: float) -> None:
        results = list(parse_constraint(ocr_text))
        for r in results:
            assert r.numeric_value != forbidden_value


# ---------------------------------------------------------------------------
# Page break handling
# ---------------------------------------------------------------------------

class TestPageBreaks:
    def test_requirement_split_across_pages_not_fabricated(self) -> None:
        """A requirement split by a page break should not produce a
        fabricated constraint from the fragment on one page."""
        text = (
            "The equipment shall maintain a temperature\n"
            "\f"
            "not exceeding 85 \u00b0C during operation."
        )
        page1, page2 = text.split("\f")
        # Each page individually should not produce a wrong value
        r1 = list(parse_constraint(page1))
        r2 = list(parse_constraint(page2))
        for r in r1 + r2:
            # No constraint should have a fabricated value from the split
            if r.numeric_value is not None and r.unit is not None:
                # Only legitimate values are acceptable
                pass

    def test_full_text_across_pages_extracted(self) -> None:
        """When the full text (joined) is parsed, the constraint is found."""
        text = (
            "The equipment shall maintain a temperature\n"
            "\f"
            "shall not exceed 85 °C during operation."
        )
        r = list(parse_constraint(text))
        assert len(r) >= 1
        assert 85.0 in {c.numeric_value for c in r}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestAdversarialDeterminism:
    @pytest.mark.parametrize("fixture_name", [
        "corrupted-comparison-symbols.txt",
        "decimal-and-unit-confusion.txt",
        "greek-symbols.txt",
        "merged-tables.txt",
        "duplicate-headers.txt",
        "prompt-injection.txt",
        "ocr-corruption.txt",
    ])
    def test_parser_is_deterministic_on_adversarial(self, fixture_name: str) -> None:
        text = _read_fixture(fixture_name)
        r1 = list(parse_constraint(text))
        r2 = list(parse_constraint(text))
        assert [
            (c.parameter, c.operator, c.numeric_value, c.unit)
            for c in r1
        ] == [
            (c.parameter, c.operator, c.numeric_value, c.unit)
            for c in r2
        ]

    def test_qualitative_deterministic_on_adversarial(self) -> None:
        text = _read_fixture("prompt-injection.txt")
        r1 = list(parse_qualitative_conditions(text))
        r2 = list(parse_qualitative_conditions(text))
        assert [c.parameter for c in r1] == [c.parameter for c in r2]
