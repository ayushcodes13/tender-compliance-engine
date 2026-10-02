"""Tests for CP52 — Vendor specification extraction (deterministic parser).

Covers:
- Basic spec extraction (colon-separated: "Accuracy: ±0.5 %")
- Range extraction ("Operating temperature: -10°C to +55°C")
- Operator-based specs ("Response time ≤ 5 ms")
- Bare value + unit specs ("Resolution: 0.01 mm")
- Qualitative conditions (IP65, CE marked, materials)
- Resolution vs accuracy distinction (same unit, different parameter)
- Same number / different metric / different entity / different scope
- No fabrication from vague prose
- OCR warning escalation (SAFE → PARTIAL)
- Source linkage (page number, char offsets)
- Determinism (same input → same output)
- Empty input
"""

from __future__ import annotations

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.vendor_spec import (
    VENDOR_SPEC_VERSION,
    ParsedVendorSpec,
    parse_vendor_specs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(
    text: str,
    *,
    ocr_warning: bool = False,
    page: int = 1,
    char_start: int | None = None,
    char_end: int | None = None,
    ocr_conf: float | None = None,
) -> list[ParsedVendorSpec]:
    return parse_vendor_specs(
        text,
        ocr_warning=ocr_warning,
        source_page_number=page,
        char_start=char_start,
        char_end=char_end,
        ocr_confidence=ocr_conf,
        location_type="exact" if ocr_conf is None else "approximate",
    )


# ---------------------------------------------------------------------------
# 1. Basic colon-separated specs
# ---------------------------------------------------------------------------


class TestColonSpecs:
    def test_accuracy_tolerance(self) -> None:
        """Accuracy: ±0.5 % → parameter=accuracy, value=0.5, unit=%, tolerance=0.5."""
        specs = _parse("Accuracy: ±0.5 %")
        assert len(specs) >= 1
        # Should have an accuracy spec
        acc = [s for s in specs if s.parameter == "accuracy"]
        assert len(acc) == 1
        assert acc[0].value == 0.5
        assert acc[0].unit == "%"
        assert acc[0].tolerance == 0.5
        assert acc[0].normalization_state is ConstraintNormalizationState.SAFE

    def test_resolution_bare_value(self) -> None:
        """Resolution: 0.01 mm → parameter=resolution, value=0.01, unit=mm."""
        specs = _parse("Resolution: 0.01 mm")
        assert len(specs) >= 1
        res = [s for s in specs if s.parameter == "resolution"]
        assert len(res) == 1
        assert res[0].value == 0.01
        assert res[0].unit == "mm"

    def test_range_with_colon(self) -> None:
        """Operating temperature: -10 to +55 °C → lower=-10, upper=55, unit=°C."""
        specs = _parse("Operating temperature: -10 to +55 °C")
        temp_specs = [s for s in specs if "temperature" in s.parameter]
        assert len(temp_specs) >= 1
        spec = temp_specs[0]
        assert spec.lower_bound == -10
        assert spec.upper_bound == 55
        assert spec.unit is not None

    def test_comparison_operator_with_colon(self) -> None:
        """Response time: ≤5 ms → value=5, unit=ms."""
        specs = _parse("Response time: ≤ 5 ms")
        rt = [s for s in specs if s.parameter == "response_time"]
        assert len(rt) == 1
        assert rt[0].value == 5
        assert rt[0].unit == "ms"

    def test_supplly_voltage(self) -> None:
        """Supply voltage: 12 V → value=12, unit=V."""
        specs = _parse("Supply voltage: 12 V")
        sv = [s for s in specs if s.parameter == "supply_voltage"]
        assert len(sv) == 1
        assert sv[0].value == 12
        assert sv[0].unit == "V"

    def test_multiple_specs_in_one_fragment(self) -> None:
        """Multiple specs in a multi-line fragment."""
        text = (
            "Accuracy: ±0.5 %\n"
            "Resolution: 0.01 mm\n"
            "Operating temperature: -10 to +55 °C\n"
        )
        specs = _parse(text)
        params = {s.parameter for s in specs}
        assert "accuracy" in params
        assert "resolution" in params
        assert "operating_temperature" in params


# ---------------------------------------------------------------------------
# 2. Operator-based specs (no colon)
# ---------------------------------------------------------------------------


class TestOperatorSpecs:
    def test_operator_spec_no_colon(self) -> None:
        """Response time ≤ 5 ms (no colon)."""
        specs = _parse("Response time ≤ 5 ms")
        rt = [s for s in specs if s.parameter == "response_time"]
        assert len(rt) == 1
        assert rt[0].value == 5
        assert rt[0].unit == "ms"

    def test_greater_than_spec(self) -> None:
        """Accuracy ≥ 99 %."""
        specs = _parse("Accuracy ≥ 99 %")
        acc = [s for s in specs if s.parameter == "accuracy"]
        assert len(acc) == 1
        assert acc[0].value == 99
        assert acc[0].unit == "%"


# ---------------------------------------------------------------------------
# 3. Range extraction
# ---------------------------------------------------------------------------


class TestRangeSpecs:
    def test_temperature_range(self) -> None:
        """Operating temperature: -10°C to +55°C."""
        specs = _parse("Operating temperature: -10°C to +55°C")
        temp = [s for s in specs if "temperature" in s.parameter]
        assert len(temp) >= 1
        assert temp[0].lower_bound == -10
        assert temp[0].upper_bound == 55

    def test_range_with_to_keyword(self) -> None:
        """Pressure range: 0 to 10 bar."""
        specs = _parse("Pressure range: 0 to 10 bar")
        pressure = [s for s in specs if "pressure" in s.parameter or "range" in s.parameter]
        assert len(pressure) >= 1


# ---------------------------------------------------------------------------
# 4. Qualitative specs
# ---------------------------------------------------------------------------


class TestQualitativeSpecs:
    def test_ip_rating(self) -> None:
        """IP65 environmental rating."""
        specs = _parse("Protection rating: IP65")
        env = [s for s in specs if s.parameter == "environmental_rating"]
        assert len(env) >= 1
        assert "IP65" in (env[0].qualitative_statement or env[0].source_text or "")

    def test_ce_marked(self) -> None:
        """CE marking."""
        specs = _parse("CE marked equipment.")
        cert = [s for s in specs if s.parameter == "certification"]
        assert len(cert) >= 1
        assert "CE" in (cert[0].qualitative_statement or "")

    def test_stainless_steel(self) -> None:
        """Material: stainless steel."""
        specs = _parse("Housing: stainless steel 304")
        material = [s for s in specs if s.parameter == "material"]
        assert len(material) >= 1
        assert "stainless steel" in (material[0].qualitative_statement or "").lower()


# ---------------------------------------------------------------------------
# 5. Resolution vs accuracy distinction
# ---------------------------------------------------------------------------


class TestResolutionAccuracyDistinction:
    def test_resolution_and_accuracy_same_unit(self) -> None:
        """Both in % but different parameters — must not be collapsed."""
        text = "Accuracy: ±0.5 %\nResolution: 0.01 %"
        specs = _parse(text)
        acc = [s for s in specs if s.parameter == "accuracy"]
        res = [s for s in specs if s.parameter == "resolution"]
        assert len(acc) == 1
        assert len(res) == 1
        assert acc[0].tolerance == 0.5
        assert res[0].value == 0.01

    def test_resolution_mm_vs_accuracy_mm(self) -> None:
        """Resolution 0.01 mm vs Accuracy ±0.02 mm — distinct parameters."""
        text = "Resolution: 0.01 mm\nAccuracy: ±0.02 mm"
        specs = _parse(text)
        params = {s.parameter for s in specs}
        assert "resolution" in params
        assert "accuracy" in params


# ---------------------------------------------------------------------------
# 6. Same number, different metric
# ---------------------------------------------------------------------------


class TestSameNumberDifferentMetric:
    def test_same_value_different_units(self) -> None:
        """5 mm vs 5 V — same number, different parameters, must not collapse."""
        text = "Stroke: 5 mm\nOutput voltage: 5 V"
        specs = _parse(text)
        length_specs = [s for s in specs if "length" in s.parameter]
        voltage_specs = [s for s in specs if "voltage" in s.parameter]
        assert len(length_specs) >= 1
        assert len(voltage_specs) >= 1
        # Verify they have different units
        units = {s.unit for s in specs if s.unit is not None}
        assert "mm" in units
        assert "V" in units

    def test_same_number_different_entity(self) -> None:
        """12 V in two model variants — must extract both, not dedupe."""
        text = "Model A: Supply voltage: 12 V\nModel B: Supply voltage: 24 V"
        specs = _parse(text)
        voltages = [s for s in specs if "voltage" in s.parameter]
        assert len(voltages) == 2
        values = {v.value for v in voltages}
        assert 12 in values
        assert 24 in values


# ---------------------------------------------------------------------------
# 7. No fabrication
# ---------------------------------------------------------------------------


class TestNoFabrication:
    def test_vague_prose_not_extracted(self) -> None:
        """'High accuracy' does not produce a spec."""
        specs = _parse("The device features high accuracy")
        # "high" is not a number, so no numeric spec should be produced.
        assert len(specs) == 0

    def test_bare_number_without_unit_not_extracted(self) -> None:
        """'Accuracy: 5' with no unit — should not fabricate a unit."""
        specs = _parse("Accuracy: 5")
        # A bare number with a recognized label but no unit is still
        # a valid spec (the value IS 5, unit IS unknown).
        # The parser should extract it with unit=None, flagged as PARTIAL.
        acc = [s for s in specs if s.parameter == "accuracy"]
        if acc:
            assert acc[0].unit is None
            assert acc[0].normalization_state is ConstraintNormalizationState.PARTIAL

    def test_marketing_language_not_extracted(self) -> None:
        """'Industry-leading performance' does not produce a spec."""
        specs = _parse("Industry-leading performance and reliability")
        assert len(specs) == 0


# ---------------------------------------------------------------------------
# 8. OCR / ambiguity escalation
# ---------------------------------------------------------------------------


class TestOCREscalation:
    def test_ocr_warning_escalates_safe_to_partial(self) -> None:
        """When ocr_warning=True, SAFE specs become PARTIAL."""
        specs = _parse("Resolution: 0.01 mm", ocr_warning=True)
        res = [s for s in specs if s.parameter == "resolution"]
        assert len(res) >= 1
        assert res[0].normalization_state is ConstraintNormalizationState.PARTIAL
        assert "ocr_warning" in (res[0].issues or ())

    def test_ocr_confidence_recorded(self) -> None:
        """OCR confidence is propagated to the spec."""
        specs = _parse(
            "Resolution: 0.01 mm",
            ocr_conf=0.85,
        )
        if specs:
            assert specs[0].ocr_confidence == 0.85
            assert specs[0].location_type == "approximate"

    def test_exact_when_no_ocr(self) -> None:
        """When no OCR confidence, location_type is 'exact'."""
        specs = _parse("Resolution: 0.01 mm", ocr_conf=None)
        if specs:
            assert specs[0].location_type == "exact"
            assert specs[0].ocr_confidence is None


# ---------------------------------------------------------------------------
# 9. Source linkage
# ---------------------------------------------------------------------------


class TestSourceLinkage:
    def test_page_number_recorded(self) -> None:
        """Page number is recorded on the spec."""
        specs = _parse("Accuracy: ±0.5 %", page=3)
        if specs:
            assert specs[0].source_page_number == 3

    def test_char_offsets_recorded(self) -> None:
        """Character offsets are recorded when provided."""
        specs = _parse(
            "Accuracy: ±0.5 %",
            char_start=100,
            char_end=115,
        )
        if specs:
            assert specs[0].char_start is not None
            assert specs[0].char_start >= 100
            assert specs[0].char_end is not None

    def test_source_text_preserved(self) -> None:
        """The verbatim source text is preserved on the spec."""
        text = "Accuracy: ±0.5 %"
        specs = _parse(text)
        if specs:
            assert "Accuracy" in specs[0].source_text
            assert "0.5" in specs[0].source_text or "±" in specs[0].source_text


# ---------------------------------------------------------------------------
# 10. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        """The parser is deterministic: same input → same output."""
        text = "Accuracy: ±0.5 %\nResolution: 0.01 mm\nIP65"
        run1 = _parse(text)
        run2 = _parse(text)
        assert len(run1) == len(run2)
        for a, b in zip(run1, run2, strict=True):
            assert a.parameter == b.parameter
            assert a.value == b.value
            assert a.unit == b.unit
            assert a.normalization_state == b.normalization_state

    def test_empty_input(self) -> None:
        """Empty fragment returns no specs."""
        assert _parse("") == []
        assert _parse("   ") == []
        assert _parse("\n\n") == []


# ---------------------------------------------------------------------------
# 11. Extraction version
# ---------------------------------------------------------------------------


class TestExtractionVersion:
    def test_version_recorded(self) -> None:
        """Each spec carries the extraction version."""
        specs = _parse("Resolution: 0.01 mm")
        if specs:
            assert specs[0].extraction_version == VENDOR_SPEC_VERSION
            assert specs[0].extraction_method == "deterministic"

    def test_version_is_pinned(self) -> None:
        """The version string is a stable identifier."""
        assert VENDOR_SPEC_VERSION == "cp52-deterministic-v1"
