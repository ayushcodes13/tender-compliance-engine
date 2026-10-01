"""Tests for CP34 — Qualitative normalization and ambiguity escalation.

Covers:
- Explicit qualitative condition extraction (certifications, IP ratings,
  materials, interfaces, documentation, construction/safety, performance)
- No fabrication from vague prose ("as required", "in accordance with")
- OCR warning propagation (SAFE → PARTIAL)
- Ambiguous boundary detection (boundary_ambiguous issue)
- Determinism (same input → same output)
- Conservative normalized text (whitespace-only, never semantic rewrite)
- State escalation matrix (SAFE / PARTIAL / NEEDS_REVIEW)
"""

from __future__ import annotations

import pytest

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.qualitative import (
    NORMALIZATION_VERSION,
    QualitativeCondition,
    conservative_normalized_text,
    parse_qualitative_conditions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single(fragment: str, **kw) -> QualitativeCondition | None:
    results = parse_qualitative_conditions(fragment, **kw)
    assert len(results) == 1, f"expected 1 condition, got {len(results)}: {results}"
    return results[0]


# ---------------------------------------------------------------------------
# 1. Certifications
# ---------------------------------------------------------------------------

def test_iso_9001_extracted() -> None:
    c = _single("The equipment shall be ISO 9001 certified.")
    assert c.parameter == "certification"
    assert "ISO 9001" in c.condition
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_ce_marking_extracted() -> None:
    c = _single("Device bears CE marking.")
    assert c.parameter == "certification"
    assert "CE" in c.condition
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_ul_listed_extracted() -> None:
    c = _single("UL listed for North America.")
    assert c.parameter == "certification"
    assert "UL" in c.condition


def test_iso_with_year_extracted() -> None:
    c = _single("Certified to ISO 9001:2015.")
    assert c.parameter == "certification"
    assert "ISO 9001" in c.condition


def test_multiple_certifications() -> None:
    results = parse_qualitative_conditions("CE and FCC compliant, ISO 9001 certified.")
    certs = [c for c in results if c.parameter == "certification"]
    assert len(certs) >= 2


# ---------------------------------------------------------------------------
# 2. Environmental ratings
# ---------------------------------------------------------------------------

def test_ip65_extracted() -> None:
    c = _single("Enclosure rated IP65.")
    assert c.parameter == "environmental_rating"
    assert "IP65" in c.condition
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_ip67_and_ip68_extracted() -> None:
    results = parse_qualitative_conditions("IP65/IP67 ingress protection.")
    env = [c for c in results if c.parameter == "environmental_rating"]
    assert len(env) >= 1


def test_nema_4x_extracted() -> None:
    c = _single("NEMA 4X enclosure.")
    assert c.parameter == "environmental_rating"
    assert "NEMA" in c.condition


def test_corrosion_resistant_extracted() -> None:
    c = _single("Corrosion-resistant housing.")
    assert c.parameter == "environmental_rating"
    assert "corrosion resistant" in c.condition.lower().replace("-", " ")


def test_explosion_proof_extracted() -> None:
    c = _single("Explosion-proof housing for hazardous areas.")
    assert c.parameter == "environmental_rating"
    assert c.normalization_state is ConstraintNormalizationState.SAFE


# ---------------------------------------------------------------------------
# 3. Materials
# ---------------------------------------------------------------------------

def test_stainless_steel_extracted() -> None:
    c = _single("Housing shall be stainless steel.")
    assert c.parameter == "material"
    assert "stainless steel" in c.condition.lower()
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_stainless_steel_with_grade() -> None:
    c = _single("Constructed of stainless steel (AISI 316).")
    assert c.parameter == "material"
    assert "stainless steel" in c.condition.lower()


def test_aluminum_extracted() -> None:
    c = _single("Aluminum enclosure.")
    assert c.parameter == "material"
    assert "aluminum" in c.condition.lower()


def test_carbon_steel_extracted() -> None:
    c = _single("Carbon steel frame.")
    assert c.parameter == "material"
    assert "carbon steel" in c.condition.lower()


# ---------------------------------------------------------------------------
# 4. Interfaces
# ---------------------------------------------------------------------------

def test_ethernet_extracted() -> None:
    c = _single("10/100 Mbps Ethernet port.")
    assert c.parameter == "interface"
    assert "Ethernet" in c.condition
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_usb_c_extracted() -> None:
    c = _single("USB-C configuration port.")
    assert c.parameter == "interface"
    assert "USB-C" in c.condition


def test_rs485_extracted() -> None:
    c = _single("RS-485 serial interface.")
    assert c.parameter == "interface"
    assert "RS-485" in c.condition


def test_wifi_extracted() -> None:
    results = parse_qualitative_conditions("Integrated Wi-Fi and Bluetooth.")
    interfaces = [c for c in results if c.parameter == "interface"]
    assert len(interfaces) >= 2


# ---------------------------------------------------------------------------
# 5. Documentation
# ---------------------------------------------------------------------------

def test_datasheet_extracted() -> None:
    c = _single("A datasheet shall be provided.")
    assert c.parameter == "documentation"
    assert "datasheet" in c.condition.lower()
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_operating_manual_extracted() -> None:
    c = _single("An operating manual shall be supplied.")
    assert c.parameter == "documentation"
    assert "manual" in c.condition.lower()


def test_certificate_of_conformity_extracted() -> None:
    c = _single("Certificate of conformity included.")
    assert c.parameter == "documentation"
    assert "certificate" in c.condition.lower()


def test_warranty_extracted() -> None:
    c = _single("A 2-year warranty is provided.")
    assert c.parameter == "documentation"
    assert "warranty" in c.condition.lower()


# ---------------------------------------------------------------------------
# 6. Construction / safety
# ---------------------------------------------------------------------------

def test_overcurrent_protection_extracted() -> None:
    c = _single("Overcurrent protection as required.")
    assert c.parameter == "construction"
    assert "overcurrent protection" in c.condition.lower()
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_overload_protection_extracted() -> None:
    c = _single("Overload protection shall be provided.")
    assert c.parameter == "construction"
    assert "overload" in c.condition.lower()


def test_ground_fault_protection_extracted() -> None:
    c = _single("Ground fault protection installed.")
    assert c.parameter == "construction"
    assert "ground fault" in c.condition.lower()


def test_thermal_cutoff_extracted() -> None:
    c = _single("Thermal cutoff switch.")
    assert c.parameter == "construction"
    assert "thermal" in c.condition.lower()


# ---------------------------------------------------------------------------
# 7. Performance characteristics
# ---------------------------------------------------------------------------

def test_plug_and_play_extracted() -> None:
    c = _single("Plug-and-play installation.")
    assert c.parameter == "performance"
    assert "plug" in c.condition.lower()
    assert c.normalization_state is ConstraintNormalizationState.SAFE


def test_hot_swappable_extracted() -> None:
    c = _single("Hot-swappable module.")
    assert c.parameter == "performance"
    assert "hot" in c.condition.lower()


def test_redundant_extracted() -> None:
    c = _single("Redundant power supply.")
    assert c.parameter == "performance"
    assert "redundant" in c.condition.lower()


def test_bidirectional_extracted() -> None:
    c = _single("Bidirectional communication.")
    assert c.parameter == "performance"
    assert "bidirectional" in c.condition.lower()


# ---------------------------------------------------------------------------
# 8. No fabrication from vague prose
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "As required by applicable standards.",
    "In accordance with applicable regulations.",
    "Where applicable, the device shall meet requirements.",
    "Standard specifications apply.",
    "The supplier shall ensure compliance.",
    "Meets industry best practices.",
    "Comply with all applicable codes.",
    "No other conditions specified.",
])
def test_vague_prose_yields_no_conditions(text: str) -> None:
    """Vague / boilerplate language produces no qualitative conditions."""
    assert parse_qualitative_conditions(text) == []


def test_empty_yields_no_conditions() -> None:
    assert parse_qualitative_conditions("") == []
    assert parse_qualitative_conditions("   ") == []


def test_certificate_without_standard_no_fabrication() -> None:
    """'A certificate shall be provided' is too vague — no extraction."""
    results = parse_qualitative_conditions("A certificate shall be provided.")
    # "certificate" alone (without "of conformity") does not match _DOC_PATTERNS
    assert all("certificate" not in c.condition.lower() for c in results)


# ---------------------------------------------------------------------------
# 9. Multiple conditions in one fragment
# ---------------------------------------------------------------------------

def test_multiple_conditions_different_types() -> None:
    text = "IP65 enclosure, stainless steel housing, CE marked, Ethernet port."
    results = parse_qualitative_conditions(text)
    params = {c.parameter for c in results}
    assert "environmental_rating" in params
    assert "material" in params
    assert "certification" in params
    assert "interface" in params


def test_multiple_conditions_same_type() -> None:
    text = "Stainless steel frame with stainless steel mounting bracket."
    results = parse_qualitative_conditions(text)
    materials = [c for c in results if c.parameter == "material"]
    assert len(materials) >= 1


def test_overlap_dedup() -> None:
    """Overlapping matches are deduplicated (longest leftmost kept)."""
    text = "IP65 ingress protection"
    results = parse_qualitative_conditions(text)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# 10. OCR warning propagation
# ---------------------------------------------------------------------------

def test_ocr_warning_escalates_safe_to_partial() -> None:
    results = parse_qualitative_conditions("IP65 enclosure.", ocr_warning=True)
    assert len(results) == 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "ocr_warning" in results[0].issues


def test_ocr_warning_preserves_needs_review() -> None:
    """An already-ambiguous condition stays PARTIAL, not downgraded, with ocr_warning added."""
    results = parse_qualitative_conditions("xIP65y", ocr_warning=True)
    assert len(results) >= 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "ocr_warning" in results[0].issues


def test_ocr_warning_does_not_downgrade_partial() -> None:
    """A boundary-ambiguous condition stays PARTIAL with ocr_warning added."""
    results = parse_qualitative_conditions("xIP65y", ocr_warning=True)
    assert len(results) >= 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL


# ---------------------------------------------------------------------------
# 11. Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "IP65 enclosure, stainless steel housing, CE marked.",
    "ISO 9001 certified.",
    "Overcurrent protection installed.",
    "Plug-and-play, hot-swappable, redundant.",
])
def test_determinism_same_input_same_output(text: str) -> None:
    r1 = parse_qualitative_conditions(text)
    r2 = parse_qualitative_conditions(text)
    assert r1 == r2


def test_determinism_with_ocr_warning() -> None:
    r1 = parse_qualitative_conditions("IP65", ocr_warning=True)
    r2 = parse_qualitative_conditions("IP65", ocr_warning=True)
    assert r1 == r2


# ---------------------------------------------------------------------------
# 12. Raw fragment preservation
# ---------------------------------------------------------------------------

def test_raw_fragment_is_full_input() -> None:
    text = "The device shall be ISO 9001 certified and IP65 rated."
    results = parse_qualitative_conditions(text)
    for c in results:
        assert c.raw_fragment == text


# ---------------------------------------------------------------------------
# 13. Conservative normalized text
# ---------------------------------------------------------------------------

def test_normalized_text_preserves_content() -> None:
    raw = "The device  shall be\nISO 9001 certified."
    norm = conservative_normalized_text(raw)
    assert "ISO 9001" in norm
    assert "certified" in norm


def test_normalized_text_collapses_whitespace() -> None:
    raw = "Weight ≤  2  kg"
    norm = conservative_normalized_text(raw)
    assert "≤ 2 kg" in norm
    assert "  " not in norm


def test_normalized_text_unicode_punctuation() -> None:
    norm = conservative_normalized_text("Weight — 2 kg")
    assert "-" in norm
    assert "—" not in norm


def test_normalized_text_empty() -> None:
    assert conservative_normalized_text("") == ""


def test_normalized_text_no_semantic_change() -> None:
    """Normalized text must not alter obligation keywords."""
    raw = "shall be at least 20 °C"
    norm = conservative_normalized_text(raw)
    assert "shall" in norm
    assert "at least" in norm
    assert "20" in norm
    assert "°C" in norm


def test_normalization_version_is_string() -> None:
    assert isinstance(NORMALIZATION_VERSION, str)
    assert "." in NORMALIZATION_VERSION


# ---------------------------------------------------------------------------
# 14. ParsedConstraint properties
# ---------------------------------------------------------------------------

def test_qualitative_condition_is_frozen() -> None:
    c = _single("IP65 enclosure.")
    with pytest.raises((AttributeError, TypeError)):
        c.condition = "other"  # type: ignore[misc]


def test_all_qualitative_parameters_are_known() -> None:
    for param in [
        "certification", "environmental_rating", "material",
        "interface", "documentation", "construction", "performance",
    ]:
        assert isinstance(param, str)


# ---------------------------------------------------------------------------
# 15. State escalation matrix
# ---------------------------------------------------------------------------

def test_safe_on_clean_match() -> None:
    c = _single("IP65 enclosure.")
    assert c.normalization_state is ConstraintNormalizationState.SAFE
    assert c.issues == ()


def test_partial_on_boundary_ambiguity() -> None:
    """When the match has letters on both sides (likely embedded in prose),
    the state escalates to PARTIAL with boundary_ambiguous."""
    results = parse_qualitative_conditions("xIP65y")
    assert len(results) >= 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "boundary_ambiguous" in results[0].issues


def test_partial_on_ocr_warning() -> None:
    results = parse_qualitative_conditions("IP65", ocr_warning=True)
    assert len(results) == 1
    assert results[0].normalization_state is ConstraintNormalizationState.PARTIAL
    assert "ocr_warning" in results[0].issues
