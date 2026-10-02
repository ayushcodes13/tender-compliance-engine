"""Deterministic vendor specification extraction from OEM evidence (CP52).

This module extracts structured vendor specifications from the verbatim text
of accepted OEM evidence segments.  It reuses the deterministic number/unit/
tolerance parsing from CP33 (``constraint_parser``) and the qualitative
condition patterns from CP34 (``qualitative``).

Design principles (AGENTS.md Phase 2 guardrails):
* **Never fabricate.** A spec is only extracted when the source text
  carries an explicit label and a value — vague prose like "high accuracy"
  never produces a vendor fact.
* **Trace to source.** Every :class:`ParsedVendorSpec` carries the verbatim
  ``source_text``, ``source_page_number``, and character offsets so the fact
  can always be traced back to OEM source material.
* **Preserve distinctions.** ``accuracy`` and ``resolution`` are separate
  parameters even though they may share a unit (e.g. both in %).
* **Escalate ambiguity.** OCR noise or ambiguous separators escalate the
  normalization state to PARTIAL / NEEDS_REVIEW, never silently corrected.
* **Every fact points to evidence.** Persistence is refused unless the spec
  can be linked to an accepted :class:`Evidence` row (enforced at the
  service layer).

The extraction operates on the text of a single :class:`OemTextSegment`
and returns zero or more :class:`ParsedVendorSpec` records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.constraint_parser import (
    _TOK_NUM,
    ConstraintOperator,
    _is_real_unit,
    _parse_number,
    _quantity_for_unit,
    parse_constraint,
)
from tender_compliance_api.extraction.qualitative import (
    parse_qualitative_conditions,
)

#: Version of this extraction ruleset — recorded on every VendorSpec row.
VENDOR_SPEC_VERSION = "cp52-deterministic-v1"

#: Mapping of common OEM spec labels to canonical parameter names.
#: Keys are lowercased; matching is prefix/suffix-tolerant.
_SPEC_LABELS: dict[str, str] = {
    "accuracy": "accuracy",
    "resolution": "resolution",
    "precision": "precision",
    "sensitivity": "sensitivity",
    "temperature": "temperature",
    "operating temperature": "operating_temperature",
    "storage temperature": "storage_temperature",
    "ambient temperature": "ambient_temperature",
    "humidity": "humidity",
    "relative humidity": "relative_humidity",
    "pressure": "pressure",
    "atmospheric pressure": "atmospheric_pressure",
    "voltage": "voltage",
    "supply voltage": "supply_voltage",
    "input voltage": "input_voltage",
    "output voltage": "output_voltage",
    "current": "current",
    "operating current": "operating_current",
    "supply current": "supply_current",
    "frequency": "frequency",
    "sampling frequency": "sampling_frequency",
    "update rate": "update_rate",
    "data rate": "data_rate",
    "throughput": "throughput",
    "power": "power",
    "power consumption": "power_consumption",
    "power supply": "power_supply",
    "weight": "mass",
    "mass": "mass",
    "dimensions": "dimensions",
    "size": "dimensions",
    "length": "length",
    "distance": "length",
    "response time": "response_time",
    "rise time": "rise_time",
    "fall time": "fall_time",
    "settling time": "settling_time",
    "range": "range",
    "measurement range": "measurement_range",
    "stroke": "length",
    "stroke length": "length",
    "display size": "display_size",
    "screen size": "display_size",
    "baud rate": "baud_rate",
    "repeatability": "repeatability",
    "linearity": "linearity",
    "hysteresis": "hysteresis",
    "offset": "offset",
    "gain": "gain",
    "input": "input",
    "output": "output",
    "capacitance": "capacitance",
    "inductance": "inductance",
    "resistance": "resistance",
    "impedance": "impedance",
    "power factor": "power_factor",
    "insulation resistance": "insulation_resistance",
    "dielectric strength": "dielectric_strength",
    "common mode rejection": "cmrr",
    "signal to noise ratio": "snr",
    "signal-to-noise ratio": "snr",
    "resolution bandwidth": "resolution_bandwidth",
}

# Pattern: "Label: <value>" where <value> starts with a number, ±, or operator.
# The value must contain a number to be a spec.  We capture the label
# (everything before the colon) and the value (rest of line up to newline).
# Note: _TOK_NUM is wrapped in (?:...) because it contains an alternation
# ("|") that would otherwise split the pattern and prevent [^.\n]* from
# applying to the full number match.
# We use [^\n]* (not [^.\n]*) because vendor spec values frequently contain
# decimal periods (e.g. "5 V ± 0.5 V") that would be truncated by a period-
# excluding character class.
_OP_CHAR = r"≤|≥|>=|≤|<|>|=|≠|!="
_SPEC_COLON_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z][A-Za-z\s/-]+?)"
    r"\s*:\s*"
    r"(?P<value>(?:±|" + _OP_CHAR + r")?\s*(?:" + _TOK_NUM + r")\b[^\n]*)",
    re.IGNORECASE,
)

# Pattern: "Label <operator> <value>" (no colon), e.g. "Resolution ≤ 0.01 mm"
# The value captures everything up to end-of-line.
_SPEC_OPERATOR_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z][A-Za-z\s/-]+?)"
    r"\s*"
    r"(?:" + _OP_CHAR + r")"
    r"\s*"
    r"(?P<value>(?:" + _TOK_NUM + r")\s*[^\n]*)",
    re.IGNORECASE,
)

# Pattern for entity extraction: "Model XYZ-123", "Part No. ABC123"
_ENTITY_RE = re.compile(
    r"\b(?:Model|Part\s+No\.?|Part\s+Number|SKU|SKU\s*No\.|Type)\s*"
    r"[:#]?\s*([A-Z0-9][A-Z0-9\-\.]+)",
    re.IGNORECASE,
)

# Pattern for operating conditions: "at 25 °C", "under 85 % RH"
_CONDITION_RE = re.compile(
    r"\b(?:at|under|in|within)\s+"
    r"(?:([+-]?\d+(?:\.\d+)?)\s*(?:°[CFcf]|°?C|°?F|%|RH|%?RH|ppm)\b)"
    r"(?:\s+to\s+([+-]?\d+(?:\.\d+)?)\s*(°[CFcf]|°?C|°?F|%|RH|%?RH|ppm))?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parsed vendor spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedVendorSpec:
    """A structured vendor fact extracted from an OEM text segment (CP52).

    ``parameter`` is the canonical conceptual quantity (e.g. ``accuracy``,
    ``resolution``) — never collapsed with the unit.  ``value``,
    ``lower_bound``, ``upper_bound``, ``tolerance``, and ``unit`` carry the
    parsed measurement.  ``qualitative_statement`` holds non-numeric specs
    (e.g. "CE marked").  ``conditions`` holds operating-condition context.

    Every field is anchored to ``source_text`` and ``char_start`` /
    ``char_end`` — never fabricated.
    """

    parameter: str
    entity: str | None = None
    value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    unit: str | None = None
    tolerance: float | None = None
    qualitative_statement: str | None = None
    conditions: dict[str, Any] | None = None
    source_text: str = ""
    source_page_number: int = 1
    char_start: int | None = None
    char_end: int | None = None
    ocr_confidence: float | None = None
    location_type: str = "approximate"
    extraction_method: str = "deterministic"
    extraction_version: str = VENDOR_SPEC_VERSION
    normalization_state: ConstraintNormalizationState = (
        ConstraintNormalizationState.SAFE
    )
    issues: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------


def _parse_spec_value(
    value_text: str,
    fragment: str,
    ocr_warning: bool,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    str | None,
    tuple[str, ...],
    ConstraintNormalizationState,
]:
    """Parse the value portion of a spec.

    Returns ``(value, lower, upper, tolerance, unit, issues, state)``.
    Reuses the deterministic number/unit parsing from CP33.
    """

    # Try using parse_constraint first — it handles operators, ranges,
    # tolerances, and scientific notation with full OCR escalation.
    constraints = parse_constraint(value_text, ocr_warning=ocr_warning)

    if constraints:
        # Use the first (and usually only) constraint.
        c = constraints[0]
        issues_list = list(c.issues)

        if c.operator == ConstraintOperator.BETWEEN.value:
            # Range: use lower/upper bounds.
            # Workaround: parse_constraint's _SPAN_RE uses \b before _TOK_NUM,
            # which prevents matching a leading negative sign ("-10 to +55").
            # If the returned lower_bound is positive but the text has a
            # negative sign before it, negate the lower bound.
            lower = c.lower_bound
            if lower is not None and lower > 0 and value_text.lstrip().startswith("-"):
                lower = -lower
                issues_list.append("negative_sign_recovered")
            return (
                None,
                lower,
                c.upper_bound,
                c.tolerance,
                c.unit,
                tuple(issues_list),
                c.normalization_state,
            )
        else:
            # Single-value comparison (=, ≠, !=, <, <=, >, >=).
            # The vendor states a value or bound — capture it as a fact.
            # For vendor specs, a tolerance is a legitimate part of the spec
            # (e.g. "Accuracy: ±0.5 %"), not an issue — strip the "tolerance"
            # issue flag that CP33's constraint parser adds, and downgrade
            # the state back to SAFE if tolerance was the only issue.
            cleaned_issues = [
                i for i in issues_list if i != "tolerance"
            ]
            cleaned_state = c.normalization_state
            # If the only issues were "tolerance", the state was PARTIAL
            # only because of that — downgrade to SAFE for vendor specs.
            if (
                not cleaned_issues
                and cleaned_state is ConstraintNormalizationState.PARTIAL
            ):
                cleaned_state = ConstraintNormalizationState.SAFE
            return (
                c.numeric_value,
                None,
                None,
                c.tolerance,
                c.unit,
                tuple(cleaned_issues),
                cleaned_state,
            )

    # If parse_constraint didn't find anything, try a bare number + unit.
    # This handles "Resolution: 0.01 mm" where there's no comparison operator.
    # parse_constraint won't extract a bare number, but vendor specs DO state
    # values as facts.
    return _parse_bare_number_value(value_text, ocr_warning)


def _parse_bare_number_value(
    value_text: str,
    ocr_warning: bool,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
    str | None,
    tuple[str, ...],
    ConstraintNormalizationState,
]:
    """Parse a bare number (no comparison operator) with optional unit.

    Vendor specifications frequently state values without operators
    ("Resolution: 0.01 mm").  This is valid vendor evidence, unlike tender
    requirements which require an operator (CP33).
    """

    issues: list[str] = []

    # Match: optional ±, number, optional unit.
    # _TOK_NUM is wrapped in (?:...) to contain its internal alternation ("|")
    # so the unit group (group 3) is positioned correctly after the number.
    bare_re = re.compile(
        r"^(±|\+/-)?\s*(" + "(?:" + _TOK_NUM + r")" + r")\s*"
        + r"(°[CFcf]|%|µ?[a-zA-Z²³µ°]+)?",
        re.IGNORECASE,
    )
    m = bare_re.match(value_text.strip())
    if not m:
        return (None, None, None, None, None, (), ConstraintNormalizationState.SAFE)

    sign = m.group(1)
    num_tok = m.group(2)
    unit_tok = m.group(3)

    num = _parse_number(num_tok, ocr_warning)

    # If there's a ± sign, this is a tolerance spec.
    if sign and num.value is not None:
        return (
            num.value,
            None,
            None,
            num.value,  # tolerance equals the value
            _is_real_unit(unit_tok),
            tuple(num.issues),
            num.state,
        )

    # If the unit token isn't a recognized measurement unit, flag it.
    unit = _is_real_unit(unit_tok)
    if unit_tok and unit is None:
        issues.append("unknown_unit")

    # Parameter is derived from the label in the caller, not from the unit.
    # But if unit is non-null but unrecognized, flag it.
    if unit is not None and _quantity_for_unit(unit) is None:
        issues.append("unknown_unit")

    # A bare number with no unit is ambiguous in a vendor spec context.
    if unit is None and num.value is not None:
        issues.append("no_unit")

    state = num.state
    if issues:
        if state is ConstraintNormalizationState.SAFE:
            state = ConstraintNormalizationState.PARTIAL

    if ocr_warning and state is ConstraintNormalizationState.SAFE:
        state = ConstraintNormalizationState.PARTIAL

    return (
        num.value,
        None,
        None,
        None,
        unit,
        tuple(issues + list(num.issues)),
        state,
    )


# ---------------------------------------------------------------------------
# Spec label normalization
# ---------------------------------------------------------------------------


def _normalize_spec_label(label: str) -> str | None:
    """Normalize a spec label to a canonical parameter name.

    Returns None if the label is not recognized as a known spec parameter.
    Matching is case-insensitive, order-independent (token set comparison).
    """

    normalized = label.strip().lower()
    # Direct lookup
    if normalized in _SPEC_LABELS:
        return _SPEC_LABELS[normalized]

    # Try removing common trailing words
    for key, val in sorted(_SPEC_LABELS.items(), key=lambda x: -len(x[0])):
        if normalized == key or normalized.endswith(" " + key):
            return val
        # Token-set matching for multi-word labels
        label_tokens = set(normalized.split())
        key_tokens = set(key.split())
        if label_tokens == key_tokens and len(label_tokens) >= 2:
            return val

    return None


# ---------------------------------------------------------------------------
# Conditions extraction
# ---------------------------------------------------------------------------


def _extract_conditions(text: str) -> dict[str, Any] | None:
    """Extract operating conditions from text (e.g. 'at 25 °C').

    Returns a dict with parsed conditions, or None if no conditions found.
    Only recognizes explicit, structured patterns — never infers.
    """

    conditions: dict[str, Any] = {}
    for m in _CONDITION_RE.finditer(text):
        lo = m.group(1)
        unit = m.group(3)
        hi = m.group(2)
        if lo:
            if hi and unit:
                conditions["operating_temperature"] = f"{lo} to {hi} {unit}"
            elif unit:
                if "°" in unit or unit.lower().startswith("c") or unit.lower().startswith("f"):
                    conditions["operating_temperature"] = f"{lo} {unit}"
                elif "%" in unit or "rh" in unit.lower():
                    conditions["relative_humidity"] = f"{lo} {unit}"
                else:
                    conditions["condition"] = f"{lo} {unit}"

    return conditions if conditions else None


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


def _extract_entity(text: str, value_start: int) -> str | None:
    """Try to find an entity/model designation near the spec.

    Looks in the text before the spec value for patterns like
    "Model XYZ-123" or "Part No. ABC123".
    """

    # Search in the 80 chars before the value
    search_region = text[max(0, value_start - 80) : value_start]
    matches = list(_ENTITY_RE.finditer(search_region))
    if matches:
        # Return the last entity found (closest to the spec)
        return matches[-1].group(0).strip()
    return None


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------


def parse_vendor_specs(
    fragment: str,
    *,
    ocr_warning: bool = False,
    source_page_number: int = 1,
    char_start: int | None = None,
    char_end: int | None = None,
    ocr_confidence: float | None = None,
    location_type: str = "approximate",
) -> list[ParsedVendorSpec]:
    """Extract structured vendor specifications from a verbatim text segment.

    Deterministically parses explicit spec patterns (``Label: value``,
    ``Label <operator> value``, ``± value``, bare ``value unit``) and delegates
    qualitative conditions to the CP34 qualitative extractor.

    Args:
        fragment: The verbatim text of an OEM text segment.
        ocr_warning: When True, all results are escalated to PARTIAL.
        source_page_number: Page number for source linkage.
        char_start: Character offset of the segment start in the page.
        char_end: Character offset of the segment end in the page.
        ocr_confidence: OCR confidence of the segment (if OCR-derived).
        location_type: "exact" or "approximate".

    Returns:
        A list of :class:`ParsedVendorSpec` records (may be empty).
    """

    if not fragment or not fragment.strip():
        return []

    results: list[ParsedVendorSpec] = []
    used_spans: list[tuple[int, int]] = []

    def _is_used(start: int, end: int) -> bool:
        return any(s < end and e > start for s, e in used_spans)

    def _mark_used(start: int, end: int) -> None:
        used_spans.append((start, end))

    def _abs_offset(rel: int) -> int:
        """Convert a relative offset within ``fragment`` to absolute page offset."""
        if char_start is not None:
            return char_start + rel
        return rel

    # --- 1. Coloned specs: "Label: <value>" ---
    for m in _SPEC_COLON_RE.finditer(fragment):
        start, end = m.span()
        if _is_used(start, end):
            continue

        label = m.group("label").strip()
        value_text = m.group("value").strip()
        label_param = _normalize_spec_label(label)

        # If the label isn't a known spec parameter, skip (don't fabricate).
        if label_param is None:
            # Still mark as used so we don't try to parse it again.
            _mark_used(start, end)
            continue

        _mark_used(start, end)

        entity = _extract_entity(fragment, m.start("value"))
        conditions = _extract_conditions(value_text)

        value, lower, upper, tol, unit, issues, state = _parse_spec_value(
            value_text, fragment, ocr_warning
        )

        # If nothing could be parsed, fall through to qualitative.
        if value is None and lower is None and upper is None and unit is None:
            continue

        all_issues = list(issues)
        if ocr_warning:
            all_issues.append("ocr_warning")

        final_state = state
        if ocr_warning and final_state is ConstraintNormalizationState.SAFE:
            final_state = ConstraintNormalizationState.PARTIAL
        if all_issues and final_state is ConstraintNormalizationState.SAFE:
            final_state = ConstraintNormalizationState.PARTIAL

        # Determine if OCR affected this: char offsets of the segment.
        spec_rel_start = m.start()
        spec_rel_end = m.end()

        results.append(
            ParsedVendorSpec(
                parameter=label_param,
                entity=entity,
                value=value,
                lower_bound=lower,
                upper_bound=upper,
                tolerance=tol,
                unit=unit,
                source_text=m.group(0).strip(),
                source_page_number=source_page_number,
                char_start=_abs_offset(spec_rel_start),
                char_end=_abs_offset(spec_rel_end),
                ocr_confidence=ocr_confidence,
                location_type=location_type,
                extraction_method="deterministic",
                extraction_version=VENDOR_SPEC_VERSION,
                normalization_state=final_state,
                issues=tuple(all_issues),
                conditions=conditions,
            )
        )

    # --- 2. Operator specs: "Label <operator> <value>" ---
    for m in _SPEC_OPERATOR_RE.finditer(fragment):
        start, end = m.span()
        if _is_used(start, end):
            continue

        label = m.group("label").strip()
        value_text = m.group("value").strip()
        label_param = _normalize_spec_label(label)

        if label_param is None:
            _mark_used(start, end)
            continue

        _mark_used(start, end)

        entity = _extract_entity(fragment, m.start("value"))
        conditions = _extract_conditions(value_text)

        value, lower, upper, tol, unit, issues, state = _parse_spec_value(
            value_text, fragment, ocr_warning
        )

        if value is None and lower is None and upper is None and unit is None:
            continue

        all_issues = list(issues)
        if ocr_warning:
            all_issues.append("ocr_warning")

        final_state = state
        if ocr_warning and final_state is ConstraintNormalizationState.SAFE:
            final_state = ConstraintNormalizationState.PARTIAL
        if all_issues and final_state is ConstraintNormalizationState.SAFE:
            final_state = ConstraintNormalizationState.PARTIAL

        spec_rel_start = m.start()
        spec_rel_end = m.end()

        results.append(
            ParsedVendorSpec(
                parameter=label_param,
                entity=entity,
                value=value,
                lower_bound=lower,
                upper_bound=upper,
                tolerance=tol,
                unit=unit,
                source_text=m.group(0).strip(),
                source_page_number=source_page_number,
                char_start=_abs_offset(spec_rel_start),
                char_end=_abs_offset(spec_rel_end),
                ocr_confidence=ocr_confidence,
                location_type=location_type,
                extraction_method="deterministic",
                extraction_version=VENDOR_SPEC_VERSION,
                normalization_state=final_state,
                issues=tuple(all_issues),
                conditions=conditions,
            )
        )

    # --- 3. Qualitative conditions (certifications, IP ratings, materials, etc.) ---
    for cond in parse_qualitative_conditions(fragment, ocr_warning=ocr_warning):
        # Check if this condition overlaps with an already-used span.
        # QualitativeCondition doesn't carry char offsets, so we do a text
        # search to find the span.
        cond_start = fragment.find(cond.condition)
        cond_end = cond_start + len(cond.condition) if cond_start >= 0 else -1

        if cond_start >= 0 and cond_end > 0:
            if _is_used(cond_start, cond_end):
                continue
            _mark_used(cond_start, cond_end)
        else:
            # Can't determine span — still extract but without offsets.
            pass

        # Map qualitative parameters to vendor spec parameters.
        param_map = {
            "certification": "certification",
            "environmental_rating": "environmental_rating",
            "material": "material",
            "interface": "interface",
            "documentation": "documentation",
            "construction": "construction",
            "performance": "performance",
        }
        param = param_map.get(cond.parameter, cond.parameter)

        all_issues = list(cond.issues)
        final_state = cond.normalization_state
        if ocr_warning and final_state is ConstraintNormalizationState.SAFE:
            final_state = ConstraintNormalizationState.PARTIAL

        spec_rel_start = cond_start if cond_start >= 0 else 0
        spec_rel_end = cond_end if cond_end > 0 else len(fragment)

        results.append(
            ParsedVendorSpec(
                parameter=param,
                qualitative_statement=cond.condition,
                source_text=cond.raw_fragment,
                source_page_number=source_page_number,
                char_start=_abs_offset(spec_rel_start),
                char_end=_abs_offset(spec_rel_end),
                ocr_confidence=ocr_confidence,
                location_type=location_type,
                extraction_method="deterministic",
                extraction_version=VENDOR_SPEC_VERSION,
                normalization_state=final_state,
                issues=tuple(all_issues),
            )
        )

    # Sort by char_start for deterministic ordering.
    results.sort(key=lambda r: (r.char_start or 0))

    return results


__all__ = [
    "VENDOR_SPEC_VERSION",
    "ParsedVendorSpec",
    "parse_vendor_specs",
]
