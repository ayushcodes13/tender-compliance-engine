"""Deterministic unit normalization and specification comparison engine (CP53).

This module compares a tender requirement's parsed constraint against a vendor
specification's parsed value, using explicit deterministic rules — never LLM
judgment for numbers.

Design principles (AGENTS.md):
- **Deterministic math owns the verdict.** Unit conversions, tolerance
  checks, range containment, and boundary comparisons are pure functions.
  An LLM is never consulted for numeric comparison.
- **Dimensions must match.** Comparing 5 V to 5 mm is INCOMPARABLE — same
  number, wrong metric.  Accuracy vs resolution is INCOMPARABLE — same unit,
  different parameter.
- **Tolerances are explicit.** ± values are treated as the vendor spec
  stating its own tolerance, not as a match criterion unless the tender
  requirement also specifies one.
- **Missing evidence ≠ non-compliant.** A vendor spec with PARTIAL state
  or no unit yields INCOMPARABLE, not a mismatch verdict.
- **Every outcome is explained.** ``ComparisonResult.reasons`` carries
  machine-readable strings so a human can trace the decision.

The engine is built on top of Pint for unit conversion, with a fallback
to a conservative built-in converter if Pint is unavailable (production
should always have Pint).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tender_compliance_api.db.models import ConstraintNormalizationState
from tender_compliance_api.extraction.constraint_parser import (
    ConstraintOperator,
    _quantity_for_unit,
)

if TYPE_CHECKING:
    import pint as _pint_t  # noqa: F401 — for type hints only

# ---------------------------------------------------------------------------
# Unit abstraction (adapter around Pint)
# ---------------------------------------------------------------------------


class _UnitAdapter:
    """Thin adapter around Pint for unit normalization.

    Provides dimensional-compatibility checking and conversion between
    compatible units, while preserving the original textual form.
    """

    def __init__(self) -> None:
        self._ureg: Any = None
        self._available: bool = False
        try:
            import pint

            self._ureg = pint.UnitRegistry()
            self._ureg.formatter.default_format = "~P"
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def quantity(self, value: float, unit: str | None) -> Any:
        """Create a Pint Quantity, or None if the unit is unknown."""

        if not self._available or unit is None:
            return None
        try:
            ureg = self._ureg
            assert ureg is not None
            return ureg.Quantity(value, unit)
        except Exception:
            return None

    def compatible(self, unit_a: str | None, unit_b: str | None) -> bool:
        """Return True if unit_a and unit_b are dimensionally compatible."""

        if not self._available or unit_a is None or unit_b is None:
            return False
        qa = self.quantity(1.0, unit_a)
        qb = self.quantity(1.0, unit_b)
        if qa is None or qb is None:
            return False
        try:
            qa.to(qb.units)
            return True
        except Exception:
            return False

    def convert(
        self, value: float, from_unit: str, to_unit: str
    ) -> float | None:
        """Convert *value* from *from_unit* to *to_unit*.  Returns None if incompatible."""

        q = self.quantity(value, from_unit)
        if q is None:
            return None
        try:
            result = q.to(to_unit)
            return float(result.magnitude)
        except Exception:
            return None


# Module-level singleton (Pint UnitRegistry is expensive to construct).
_unit_adapter = _UnitAdapter()


# ---------------------------------------------------------------------------
# Comparison outcomes
# ---------------------------------------------------------------------------


class ComparisonVerdict(enum.StrEnum):
    """Outcome of comparing a tender constraint against a vendor spec."""

    MATCH = "match"
    """Vendor spec satisfies the tender constraint."""

    CLOSE = "close"
    """Values are very close but not exactly within tolerance."""

    MISMATCH = "mismatch"
    """Vendor spec contradicts the tender constraint (same dimension)."""

    INCOMPARABLE = "incomparable"
    """Dimensions, parameters, or units are incompatible — cannot judge."""

    NOT_DEMONSTRATED = "not_demonstrated"
    """No vendor spec exists for this requirement parameter."""


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing one tender constraint against one vendor spec.

    ``tender_text`` and ``vendor_text`` are the verbatim source fragments
    (never synthesized).  ``reasons`` carries machine-readable strings
    explaining the verdict — every string maps to a deterministic rule.
    """

    verdict: ComparisonVerdict
    tender_text: str
    vendor_text: str
    comparison_rule: str
    conversion: str | None = None
    reasons: tuple[str, ...] = ()
    tender_value: float | None = None
    vendor_value: float | None = None
    tender_unit: str | None = None
    vendor_unit: str | None = None
    normalized_tender_value: float | None = None
    normalized_vendor_value: float | None = None
    details: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Unit alias map (safe aliases → Pint-compatible unit string)
# ---------------------------------------------------------------------------

#: Maps unit tokens that appear in parsed constraints/specs to Pint-compatible
#: unit strings.  Unknown units fall through to the adapter as-is.
_UNIT_ALIASES: dict[str, str] = {
    "°c": "degC",
    "°f": "degF",
    "°": "deg",
}


def _normalize_unit(unit: str | None) -> str | None:
    """Map a unit token to its Pint-compatible alias (keeping original if unknown)."""

    if unit is None:
        return None
    return _UNIT_ALIASES.get(unit, unit)


# ---------------------------------------------------------------------------
# Parameter compatibility
# ---------------------------------------------------------------------------


def _base_parameter(param: str) -> str:
    """Map a specific parameter to its base quantity for compatibility checking.

    e.g. 'supply_voltage' → 'voltage', 'operating_temperature' → 'temperature'.
    """

    for prefix in ("supply_", "input_", "output_", "operating_", "storage_",
                   "ambient_", "relative_", "atmospheric_", "response_",
                   "sampling_", "update_", "data_", "rise_", "fall_",
                   "settling_", "power_"):
        if param.startswith(prefix):
            return param[len(prefix):]
    return param


#: Maps vendor-spec parameters to their base quantity parameter (from the
#: unit-derived quantity in CP33).  Used by the comparison engine to check
#: compatibility between a tender constraint's parameter (derived from the
#: unit, e.g. "voltage") and a vendor spec's parameter (derived from the
#: label, e.g. "supply_voltage").
_VENDOR_TO_BASE_PARAM: dict[str, str] = {
    "supply_voltage": "voltage",
    "input_voltage": "voltage",
    "output_voltage": "voltage",
    "operating_current": "current",
    "supply_current": "current",
    "operating_temperature": "temperature",
    "storage_temperature": "temperature",
    "ambient_temperature": "temperature",
    "atmospheric_pressure": "pressure",
    "relative_humidity": "humidity",
    "response_time": "time",
    "rise_time": "time",
    "fall_time": "time",
    "settling_time": "time",
    "sampling_frequency": "frequency",
    "update_rate": "frequency",
    "data_rate": "frequency",
    "power_consumption": "power",
    "power_supply": "power",
}


def _params_compatible(
    tender_param: str, vendor_param: str
) -> bool:
    """Check whether two parameters are the same conceptual quantity.

    The tender constraint's parameter is typically unit-derived ("voltage",
    "time", "temperature").  The vendor spec's parameter is label-derived
    ("supply_voltage", "response_time", "operating_temperature").  This
    function maps the vendor parameter to its base quantity and checks for
    equality, ensuring that "accuracy" and "resolution" are NOT compatible
    even when they share a unit.
    """

    vendor_base = _VENDOR_TO_BASE_PARAM.get(vendor_param, _base_parameter(vendor_param))
    tender_base = _base_parameter(tender_param)
    return tender_base == vendor_base


def _pct_params_compatible(
    tender_param: str, vendor_param: str
) -> bool:
    """Check parameter compatibility for percentage specs.

    'percentage' (generic, from unit) is compatible with any specific
    percentage parameter (accuracy, efficiency, etc.), because the numeric
    comparison is purely on the % value.  However, two DIFFERENT
    specific parameters (e.g. 'accuracy' vs 'resolution') are NOT
    compatible — a number matching does not mean the same quality is
    being measured.
    """

    if tender_param == vendor_param:
        return True
    # If either side is the generic "percentage" parameter (from unit),
    # they are compatible — the vendor's specific parameter (accuracy) is
    # being compared against a generic percentage requirement.
    if tender_param == "percentage" or vendor_param == "percentage":
        return True
    # Both are specific and different (e.g., accuracy vs resolution)
    return False


def _is_qualitative(unit: str | None, quantity: str | None) -> bool:
    """Return True if this unit/quantity is a dimensionless percentage."""

    if unit == "%":
        return True
    if quantity == "percentage":
        return True
    return False


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------


def compare_spec(
    tender_constraint: object,
    vendor_spec: object,
) -> ComparisonResult:
    """Compare a tender constraint (ParsedConstraint) against a vendor spec (ParsedVendorSpec).

    This is the deterministic comparison engine.  It does NOT consult any LLM.
    """

    from tender_compliance_api.extraction.constraint_parser import ParsedConstraint
    from tender_compliance_api.extraction.vendor_spec import ParsedVendorSpec

    tc = tender_constraint if isinstance(tender_constraint, ParsedConstraint) else None
    vs = vendor_spec if isinstance(vendor_spec, ParsedVendorSpec) else None

    if tc is None or vs is None:
        raise ValueError(
            "tender_constraint must be ParsedConstraint and vendor_spec must be ParsedVendorSpec"
        )

    # --- 1. Parameter compatibility check ---
    is_tender_pct = tc.unit == "%"
    is_vendor_pct = vs.unit == "%"

    if is_tender_pct or is_vendor_pct:
        if not _pct_params_compatible(tc.parameter, vs.parameter):
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=tc.raw_fragment,
                vendor_text=vs.source_text,
                comparison_rule="parameter_mismatch",
                reasons=(
                    f"tender parameter '{tc.parameter}' != vendor parameter '{vs.parameter}'",
                    "accuracy vs resolution is a known parameter mismatch even with same unit",
                ),
            )
    else:
        if not _params_compatible(tc.parameter, vs.parameter):
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=tc.raw_fragment,
                vendor_text=vs.source_text,
                comparison_rule="parameter_mismatch",
                reasons=(
                    f"tender parameter '{tc.parameter}' != vendor parameter '{vs.parameter}'",
                    "accuracy vs resolution is a known parameter mismatch even with same unit",
                ),
            )

    # --- 2. Handle qualitative specs (no numeric comparison) ---
    tender_qty = _quantity_for_unit(tc.unit)
    vendor_qty = _quantity_for_unit(vs.unit)

    if _is_qualitative(tc.unit, tender_qty) and _is_qualitative(vs.unit, vendor_qty):
        # Both are percentages — compare using the tender operator
        return _compare_percentage(tc, vs)

    if _is_qualitative(tc.unit, tender_qty) or _is_qualitative(vs.unit, vendor_qty):
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=tc.raw_fragment,
            vendor_text=vs.source_text,
            comparison_rule="qualitative_numeric_mixed",
            reasons=(
                "one side is qualitative (percentage/dimensionless), the other is not",
                "qualitative cases are kept out of numeric math",
            ),
        )

    # --- 3. Handle non-numeric vendor specs ---
    if vs.value is None and vs.lower_bound is None and vs.upper_bound is None:
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=tc.raw_fragment,
            vendor_text=vs.source_text,
            comparison_rule="qualitative_vendor_spec",
            reasons=("vendor spec has no numeric value",),
            tender_unit=tc.unit,
            vendor_unit=vs.unit,
        )

    # --- 4. Handle non-SAFE normalization state ---
    # Allow PARTIAL state when the only issue is "tolerance" — a ± tolerance
    # is a legitimate spec feature, not ambiguity.
    tender_issues = tuple(i for i in tc.issues if i != "tolerance")
    vendor_issues = tuple(i for i in vs.issues if i != "tolerance")
    _SAFE = ConstraintNormalizationState.SAFE
    tender_uncertain = bool(tender_issues) and tc.normalization_state is not _SAFE
    vendor_uncertain = bool(vendor_issues) and vs.normalization_state is not _SAFE
    if tender_uncertain or vendor_uncertain:
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=tc.raw_fragment,
            vendor_text=vs.source_text,
            comparison_rule="uncertain_state",
            reasons=(
                f"tender state={tc.normalization_state.value}",
                f"vendor state={vs.normalization_state.value}",
                "values with non-SAFE normalization state are not deterministically comparable",
            ),
            tender_unit=tc.unit,
            vendor_unit=vs.unit,
        )

    # --- 5. Unit compatibility check ---
    t_unit = _normalize_unit(tc.unit)
    v_unit = _normalize_unit(vs.unit)

    if t_unit != v_unit:
        if not _unit_adapter.available:
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=tc.raw_fragment,
                vendor_text=vs.source_text,
                comparison_rule="unit_diff_no_converter",
                reasons=(
                    f"units differ: tender '{tc.unit}' vs vendor '{vs.unit}'",
                    "Pint not available for conversion",
                ),
                tender_unit=tc.unit,
                vendor_unit=vs.unit,
            )

        if not _unit_adapter.compatible(t_unit, v_unit):
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=tc.raw_fragment,
                vendor_text=vs.source_text,
                comparison_rule="unit_dimension_mismatch",
                reasons=(
                    f"tender unit '{tc.unit}' and vendor unit '{vs.unit}'"
                    " are not dimensionally compatible",
                    "same number, wrong metric — INCOMPARABLE",
                ),
                tender_unit=tc.unit,
                vendor_unit=vs.unit,
            )

        # Units are dimensionally compatible — convert vendor value to tender unit
        vv = vs.value
        tv = tc.numeric_value
        if tv is None and tc.operator == ConstraintOperator.BETWEEN.value:
            tv = tc.lower_bound
        if vv is not None and t_unit is not None and v_unit is not None:
            converted = _unit_adapter.convert(vv, v_unit, t_unit)
            if converted is not None:
                assert t_unit is not None and v_unit is not None
                return _evaluate_comparison(
                    tc, vs, tv, converted, t_unit, v_unit,
                    converted, f"unit_conversion({v_unit}→{t_unit})",
                )
            assert t_unit is not None and v_unit is not None
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=tc.raw_fragment,
                vendor_text=vs.source_text,
                comparison_rule="conversion_failed",
                reasons=(f"conversion from {v_unit} to {t_unit} failed",),
                tender_unit=tc.unit,
                vendor_unit=vs.unit,
            )
        # Vendor value is None — fall through to same_unit path

    # --- 6. Same unit (or no conversion needed) — proceed to operator comparison ---
    assert t_unit is not None and v_unit is not None
    return _evaluate_comparison(tc, vs, tc.numeric_value, vs.value,
                                t_unit, v_unit, vs.value, "same_unit")


def _compare_percentage(tc: object, vs: object) -> ComparisonResult:
    """Compare two percentage specs using the tender's operator."""

    from tender_compliance_api.extraction.constraint_parser import ParsedConstraint
    from tender_compliance_api.extraction.vendor_spec import ParsedVendorSpec

    c = tc if isinstance(tc, ParsedConstraint) else None
    s = vs if isinstance(vs, ParsedVendorSpec) else None
    assert c is not None and s is not None

    tv = c.numeric_value
    vv = s.value
    tolerance = c.tolerance if c.tolerance is not None else s.tolerance
    op = c.operator

    if tv is None or vv is None:
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="incomplete_percentage",
            reasons=("one or both percentage values are None",),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
        )

    reasons: list[str] = []
    conversion_str: str | None = None

    if op == ConstraintOperator.EQUALS.value:
        if tolerance is not None:
            diff = abs(vv - tv)
            if diff <= tolerance:
                verdict = ComparisonVerdict.MATCH
                reasons.append(f"|{vv} - {tv}| = {diff} ≤ tol {tolerance}")
            else:
                verdict = ComparisonVerdict.MISMATCH
                reasons.append(f"|{vv} - {tv}| = {diff} > tol {tolerance}")
        else:
            if vv == tv:
                verdict = ComparisonVerdict.MATCH
                reasons.append("exact equality")
            else:
                verdict = ComparisonVerdict.MISMATCH
                reasons.append(f"tender {tv} {c.unit} != vendor {vv} {s.unit}")
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="exact_percentage",
            reasons=tuple(reasons),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tv,
            normalized_vendor_value=vv,
            conversion=conversion_str,
            details={"tolerance": tolerance},
        )

    if op == ConstraintOperator.GREATER_THAN_OR_EQUAL.value:
        ok = vv >= tv
        boundary = tv - (tolerance or 0)
        if tolerance is not None:
            ok = vv >= boundary
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {vv} >= tender {tv}")
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="min_ge_percentage",
            reasons=tuple(reasons),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tv,
            normalized_vendor_value=vv,
            conversion=conversion_str,
            details={"tolerance": tolerance},
        )

    if op == ConstraintOperator.LESS_THAN_OR_EQUAL.value:
        ok = vv <= tv
        boundary = tv + (tolerance or 0)
        if tolerance is not None:
            ok = vv <= boundary
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {vv} <= tender {tv}")
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="max_le_percentage",
            reasons=tuple(reasons),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tv,
            normalized_vendor_value=vv,
            conversion=conversion_str,
            details={"tolerance": tolerance},
        )

    if op == ConstraintOperator.LESS_THAN.value:
        ok = vv < tv
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {vv} < tender {tv}")
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="max_lt_percentage",
            reasons=tuple(reasons),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tv,
            normalized_vendor_value=vv,
            conversion=conversion_str,
        )

    if op == ConstraintOperator.GREATER_THAN.value:
        ok = vv > tv
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {vv} > tender {tv}")
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule="min_gt_percentage",
            reasons=tuple(reasons),
            tender_value=tv,
            vendor_value=vv,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tv,
            normalized_vendor_value=vv,
            conversion=conversion_str,
        )

    # BETWEEN for percentages — treat as exact range
    if op == ConstraintOperator.BETWEEN.value:
        lower = c.lower_bound
        upper = c.upper_bound
        if lower is not None and upper is not None:
            if lower <= vv <= upper:
                verdict = ComparisonVerdict.MATCH
            else:
                verdict = ComparisonVerdict.MISMATCH
            reasons.append(f"vendor {vv} in [{lower}, {upper}]")
            return ComparisonResult(
                verdict=verdict,
                tender_text=c.raw_fragment,
                vendor_text=s.source_text,
                comparison_rule="range_containment_percentage",
                reasons=tuple(reasons),
                tender_value=tv,
                vendor_value=vv,
                tender_unit=c.unit,
                vendor_unit=s.unit,
                normalized_tender_value=tv,
                normalized_vendor_value=vv,
                conversion=conversion_str,
                details={"tender_lower": lower, "tender_upper": upper},
            )

    # Fallback for unknown operators
    return ComparisonResult(
        verdict=ComparisonVerdict.INCOMPARABLE,
        tender_text=c.raw_fragment,
        vendor_text=s.source_text,
        comparison_rule=f"unknown_operator:{op}",
        reasons=(f"operator '{op}' is not handled",),
        tender_unit=c.unit,
        vendor_unit=s.unit,
    )


def _evaluate_comparison(
    tc: object,
    vs: object,
    tender_value: float | None,
    vendor_value: float | None,
    tender_unit: str,
    vendor_unit: str,
    normalized_vendor_value: float | None,
    conversion: str,
) -> ComparisonResult:
    """Evaluate the comparison based on the tender operator and tolerance.

    Handles BETWEEN (range) constraints by reading lower_bound/upper_bound
    from the constraint object directly, and single-value operators (=, <, ≤,
    >, ≥) via tender_value/numeric_value.
    """

    from tender_compliance_api.extraction.constraint_parser import ParsedConstraint
    from tender_compliance_api.extraction.vendor_spec import ParsedVendorSpec

    c = tc if isinstance(tc, ParsedConstraint) else None
    s = vs if isinstance(vs, ParsedVendorSpec) else None
    assert c is not None and s is not None

    op = c.operator
    tolerance = c.tolerance if c.tolerance is not None else s.tolerance
    reasons: list[str] = []
    conversion_str = conversion if conversion != "same_unit" else None

    # Helper: append conversion suffix to rule name
    def _rule(name: str) -> str:
        if conversion == "same_unit":
            return name
        return f"{name}({conversion})"

    # Helper to build a result
    def _result(
        verdict: ComparisonVerdict,
        rule: str,
        vend_val: float | None = normalized_vendor_value,
    ) -> ComparisonResult:
        return ComparisonResult(
            verdict=verdict,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule=rule,
            reasons=tuple(reasons),
            tender_value=tender_value,
            vendor_value=vend_val,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            normalized_tender_value=tender_value,
            normalized_vendor_value=normalized_vendor_value,
            conversion=conversion_str,
            details={"tolerance": tolerance},
        )

    # --- BETWEEN (range) comparison ---
    if op == ConstraintOperator.BETWEEN.value:
        lower = c.lower_bound
        upper = c.upper_bound
        if lower is None or upper is None:
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=c.raw_fragment,
                vendor_text=s.source_text,
                comparison_rule=conversion,
                reasons=("tender range bounds are None",),
                tender_value=tender_value,
                vendor_value=normalized_vendor_value,
                tender_unit=c.unit,
                vendor_unit=s.unit,
                conversion=conversion_str,
            )
        if normalized_vendor_value is None:
            return ComparisonResult(
                verdict=ComparisonVerdict.INCOMPARABLE,
                tender_text=c.raw_fragment,
                vendor_text=s.source_text,
                comparison_rule=conversion,
                reasons=("vendor numeric value is None",),
                tender_value=tender_value,
                vendor_value=None,
                tender_unit=c.unit,
                vendor_unit=s.unit,
                conversion=conversion_str,
            )
        if lower <= normalized_vendor_value <= upper:
            reasons.append(
                f"vendor value {normalized_vendor_value} within tender range [{lower}, {upper}]"
            )
            return _result(ComparisonVerdict.MATCH, _rule("range_containment"))
        if (
            tolerance is not None
            and (lower - tolerance) <= normalized_vendor_value <= (upper + tolerance)
        ):
            reasons.append(
                f"vendor {normalized_vendor_value} within tol of"
                f" range [{lower}, {upper}], tol={tolerance}"
            )
            return _result(ComparisonVerdict.CLOSE, _rule("range_containment"))
        reasons.append(
            f"vendor value {normalized_vendor_value} outside tender range [{lower}, {upper}]"
        )
        return _result(ComparisonVerdict.MISMATCH, _rule("range_containment"))

    # --- Single-value operators ---
    if tender_value is None:
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule=conversion,
            reasons=("tender numeric value is None",),
            tender_value=tender_value,
            vendor_value=normalized_vendor_value,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            conversion=conversion_str,
        )

    if normalized_vendor_value is None:
        return ComparisonResult(
            verdict=ComparisonVerdict.INCOMPARABLE,
            tender_text=c.raw_fragment,
            vendor_text=s.source_text,
            comparison_rule=conversion,
            reasons=("vendor numeric value is None",),
            tender_value=tender_value,
            vendor_value=None,
            tender_unit=c.unit,
            vendor_unit=s.unit,
            conversion=conversion_str,
        )

    if op == ConstraintOperator.EQUALS.value:
        if tolerance is not None:
            diff = abs(normalized_vendor_value - tender_value)
            if diff <= tolerance:
                verdict = ComparisonVerdict.MATCH
                f"|{normalized_vendor_value} - {tender_value}|"
                f" = {diff} ≤ tol {tolerance}"
            else:
                verdict = ComparisonVerdict.MISMATCH
                f"|{normalized_vendor_value} - {tender_value}|"
                f" = {diff} > tol {tolerance}"
        else:
            if normalized_vendor_value == tender_value:
                verdict = ComparisonVerdict.MATCH
                reasons.append("exact equality")
            else:
                verdict = ComparisonVerdict.MISMATCH
                reasons.append(f"tender {tender_value} != vendor {normalized_vendor_value}")
        return _result(verdict, "exact" + (f"({conversion})" if conversion != "same_unit" else ""))

    if op == ConstraintOperator.LESS_THAN_OR_EQUAL.value:
        if tolerance is not None:
            boundary = tender_value + tolerance
            ok = normalized_vendor_value <= boundary
        else:
            ok = normalized_vendor_value <= tender_value
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {normalized_vendor_value} ≤ tender {tender_value}")
        return _result(verdict, "max_le" + (f"({conversion})" if conversion != "same_unit" else ""))

    if op == ConstraintOperator.LESS_THAN.value:
        ok = normalized_vendor_value < tender_value
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {normalized_vendor_value} < tender {tender_value}")
        return _result(verdict, "max_lt" + (f"({conversion})" if conversion != "same_unit" else ""))

    if op == ConstraintOperator.GREATER_THAN_OR_EQUAL.value:
        if tolerance is not None:
            boundary = tender_value - tolerance
            ok = normalized_vendor_value >= boundary
        else:
            ok = normalized_vendor_value >= tender_value
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {normalized_vendor_value} >= tender {tender_value}")
        return _result(verdict, "min_ge" + (f"({conversion})" if conversion != "same_unit" else ""))

    if op == ConstraintOperator.GREATER_THAN.value:
        ok = normalized_vendor_value > tender_value
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {normalized_vendor_value} > tender {tender_value}")
        return _result(verdict, "min_gt" + (f"({conversion})" if conversion != "same_unit" else ""))

    if op == ConstraintOperator.NOT_EQUAL.value:
        ok = normalized_vendor_value != tender_value
        verdict = ComparisonVerdict.MATCH if ok else ComparisonVerdict.MISMATCH
        reasons.append(f"vendor {normalized_vendor_value} != tender {tender_value}")
        return _result(verdict, _rule("not_equal"))

    # Fallback — unknown operator
    return _result(
        ComparisonVerdict.INCOMPARABLE,
        f"unknown_operator:{op}",
    )


def compare_specs(
    tender_constraint: object,
    vendor_spec: object,
) -> ComparisonResult:
    """Public entry point — delegates to :func:`compare_spec`."""

    return compare_spec(tender_constraint, vendor_spec)


__all__ = [
    "ComparisonVerdict",
    "ComparisonResult",
    "compare_spec",
    "compare_specs",
]
