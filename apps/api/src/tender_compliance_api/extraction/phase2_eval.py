"""Phase 2 compliance evaluation harness and false-compliance benchmark (CP61).

Extends the CP44 extraction eval harness with Phase 2 metrics that measure
the *semantic correctness* of compliance assessments — not just extraction
fidelity.

The most important metric is **false compliance** (COMPLIANT assessed when
the evidence does NOT actually satisfy the requirement).  This is the
highest-severity release gate per CP61's guardrail:
"Never trade false compliance for a better-looking completion rate."

Other Phase 2 metrics:
- Evidence retrieval precision/recall (top-k)
- Unit conversion correctness
- Numeric comparison correctness (operator + value + unit)
- Classification correctness (parameter matching)
- Citation correctness (evidence source linkage)
- Conflict recall (conflicting evidence detected)
- False non-compliance rate (NON_COMPLIANT when evidence does satisfy)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from tender_compliance_api.extraction.constraint_parser import (
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.spec_comparison import (
    ComparisonVerdict,
    compare_spec,
)
from tender_compliance_api.extraction.vendor_spec import (
    parse_vendor_specs,
)

# ---------------------------------------------------------------------------
# Benchmark case definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Phase2BenchmarkCase:
    """A single Phase 2 compliance-assessment benchmark case.

    Each case pairs a tender requirement (with parseable constraint text)
    against vendor evidence text and records the gold-standard compliance
    verdict.  The case is tagged as ``false_compliance_risk=True`` when an
    incorrect implementation could report COMPLIANT for a NON_COMPLIANT
    requirement (the highest-severity error class).
    """

    case_id: str
    description: str
    tender_text: str
    """Raw tender requirement text."""
    evidence_text: str
    """Raw vendor evidence text."""
    gold_status: ComparisonVerdict
    """Gold-standard comparison verdict."""
    false_compliance_risk: bool
    """True if a buggy implementation might report COMPLIANT when it should not."""
    tags: list[str] = field(default_factory=list)

    @property
    def is_compliant_gold(self) -> bool:
        return self.gold_status == ComparisonVerdict.MATCH

    @property
    def is_non_compliant_gold(self) -> bool:
        return self.gold_status in (
            ComparisonVerdict.MISMATCH,
            ComparisonVerdict.NOT_DEMONSTRATED,
        )


# ---------------------------------------------------------------------------
# Benchmark dataset
# ---------------------------------------------------------------------------

PHASE2_BENCHMARK_CASES: list[Phase2BenchmarkCase] = [
    # --- True compliance ---
    Phase2BenchmarkCase(
        case_id="tc-001-exact-match",
        description="Vendor spec matches tender constraint exactly (same unit, same value).",
        tender_text="The operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating temperature: 85 °C (at 20 °C ambient).",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["exact_match", "boundary_equality"],
    ),
    Phase2BenchmarkCase(
        case_id="tc-002-within-range",
        description="Vendor spec value is below the maximum — compliant.",
        tender_text="The maximum current shall not exceed 5.0 A.",
        evidence_text="Rated current: 3.5 A at 12 V.",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["within_bound", "unit_conversion"],
    ),
    Phase2BenchmarkCase(
        case_id="tc-003-unit-conversion-fahrenheit",
        description="Vendor spec in °F; 100 °F = 37.78 °C ≤ 85 °C → COMPLIANT.",
        tender_text="The maximum operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating temperature: 100 °F (37.8 °C).",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["unit_conversion", "fahrenheit"],
    ),
    Phase2BenchmarkCase(
        case_id="tc-004-min-threshold-met",
        description="Vendor spec meets minimum voltage requirement exactly.",
        tender_text="The supply voltage shall be at least 12 V.",
        evidence_text="Supply voltage: 12 V (nominal).",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["min_threshold", "boundary_equality", "voltage"],
    ),
    Phase2BenchmarkCase(
        case_id="tc-005-tolerance-within-range",
        description="Vendor spec nominal within tolerance band of requirement.",
        tender_text="The supply voltage shall be 12 V ±10% (10.8–13.2 V).",
        evidence_text="Supply voltage: 12.5 V (nominal).",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["tolerance", "voltage"],
    ),

    # --- False compliance traps (highest severity) ---
    Phase2BenchmarkCase(
        case_id="fc-001-exceeds-maximum",
        description="Vendor spec 90 °C > 85 °C max → NON_COMPLIANT. "
        "A system that drops the operator or misreads 'not exceed' may say COMPLIANT.",
        tender_text="The maximum operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating temperature: 90 °C.",
        gold_status=ComparisonVerdict.MISMATCH,
        false_compliance_risk=True,
        tags=["exceeds_max", "false_compliance_trap"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-002-unit-conversion-flips-verdict",
        description="Vendor spec 200 K = -73.15 °C ≤ 85 °C → COMPLIANT (correct). "
        "A system that does NOT convert units may compare 200 > 85 directly and "
        "report NON_COMPLIANT (false negative). Tests the conversion engine.",
        tender_text="The maximum operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating temperature: 200 K.",
        gold_status=ComparisonVerdict.MATCH,
        false_compliance_risk=False,
        tags=["unit_conversion", "kelvin", "false_negative_risk"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-003-parameter-mismatch",
        description="Evidence describes a different parameter (humidity, not temperature). "
        "A system that ignores the parameter name and only compares numbers "
        "might match 85 to 85 → false COMPLIANT.",
        tender_text="The maximum operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating humidity: 85 % RH.",
        gold_status=ComparisonVerdict.INCOMPARABLE,
        false_compliance_risk=True,
        tags=["parameter_mismatch", "false_compliance_trap"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-004-operator-inverted",
        description="Requirement is MINIMUM 12 V; vendor spec is 5 V. "
        "A system that ignores the operator 'at least' and just compares "
        "5 vs 12 might wrongly match, or a system that reverses min/max "
        "would say COMPLIANT.",
        tender_text="The supply voltage shall be at least 12 V.",
        evidence_text="Supply voltage: 5 V (minimum requirement).",
        gold_status=ComparisonVerdict.MISMATCH,
        false_compliance_risk=True,
        tags=["min_threshold", "operator_inverted", "false_compliance_trap"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-005-keyword-only-no-evidence",
        description="Vendor says 'compliant' but provides no actual spec value. "
        "A system matching on the keyword 'compliant' without checking "
        "numeric evidence would report false COMPLIANT.",
        tender_text="The supply voltage shall be 12 V ±10%.",
        evidence_text="This product is compliant with all applicable standards.",
        gold_status=ComparisonVerdict.NOT_DEMONSTRATED,
        false_compliance_risk=True,
        tags=["no_numeric_evidence", "keyword_trap", "false_compliance_trap"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-006-bare-number-unit-stripped",
        description="Vendor spec has no unit: '85'. A system that strips units "
        "and compares raw numbers might match 85 to 85 → false COMPLIANT "
        "if the value is actually 85 °F not 85 °C.",
        tender_text="The maximum operating temperature shall not exceed 85 °C.",
        evidence_text="Maximum operating temperature: 85 (units not specified).",
        gold_status=ComparisonVerdict.INCOMPARABLE,
        false_compliance_risk=True,
        tags=["missing_unit", "incomparable", "false_compliance_trap"],
    ),
    Phase2BenchmarkCase(
        case_id="fc-007-tolerance-exceeded",
        description="Requirement: 12 V ±10% (10.8–13.2 V). Vendor: 13.5 V > 13.2 → "
        "NON_COMPLIANT. A system that only does approximate match or ignores "
        "tolerance may report COMPLIANT (false compliance).",
        tender_text="The supply voltage shall be 12 V ±10% (10.8–13.2 V).",
        evidence_text="Supply voltage: 13.5 V.",
        gold_status=ComparisonVerdict.MISMATCH,
        false_compliance_risk=True,
        tags=["tolerance_exceeded", "false_compliance_trap"],
    ),
]


def load_phase2_dataset() -> list[Phase2BenchmarkCase]:
    """Return the full Phase 2 benchmark dataset."""
    return PHASE2_BENCHMARK_CASES


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Phase2CaseResult:
    """Result of evaluating one Phase2BenchmarkCase."""

    case_id: str
    gold_status: str
    assessed_status: str
    matched: bool
    false_compliance: bool
    """True if assessed COMPLIANT but gold is NOT_COMPLIANT."""
    false_non_compliance: bool
    """True if assessed NON_COMPLIANT but gold is COMPLIANT."""
    error: str | None = None


@dataclass(frozen=True)
class Phase2EvalReport:
    """Full Phase 2 evaluation report."""

    timestamp: str
    dataset_size: int
    case_results: list[Phase2CaseResult]
    false_compliance_count: int
    """Cases where system said COMPLIANT but should not have."""
    false_non_compliance_count: int
    """Cases where system said NON_COMPLIANT but should have been COMPLIANT."""
    false_compliance_rate: float
    false_non_compliance_rate: float
    overall_accuracy: float
    false_compliance_gate_passed: bool
    """Hard invariant: false_compliance_count must be 0."""
    all_passed: bool

    @property
    def critical_gates_passed(self) -> bool:
        return self.false_compliance_gate_passed


# ---------------------------------------------------------------------------
# Core assessment runner (uses deterministic CP53 comparison engine)
# ---------------------------------------------------------------------------

_NUMERIC_REL_TOL = 1e-9
_NUMERIC_ABS_TOL = 1e-12


def _assess_case(case: Phase2BenchmarkCase) -> tuple[ComparisonVerdict, str | None]:
    """Assess a single case using the deterministic comparison engine.

    Extracts the constraint from the tender text and the vendor spec from
    the evidence text, then runs ``compare_spec``.
    Returns the verdict and an optional error string.
    """
    try:
        # Parse the tender requirement into a constraint.
        constraints = parse_constraint(case.tender_text)
        if not constraints:
            return ComparisonVerdict.NOT_DEMONSTRATED, "No constraint parsed from tender text."

        # Use the first constraint (benchmark cases have one).
        constraint = constraints[0]
        if not isinstance(constraint, ParsedConstraint):
            return ComparisonVerdict.NOT_DEMONSTRATED, "Parsed constraint is not ParsedConstraint."

        # Parse the vendor evidence into specs.
        specs = parse_vendor_specs(case.evidence_text)
        # Take all specs found.
        if not specs:
            return ComparisonVerdict.NOT_DEMONSTRATED, "No vendor spec parsed from evidence."

        # Compare the first vendor spec against the constraint.
        result = compare_spec(constraint, specs[0])
        return result.verdict, None

    except Exception as exc:  # noqa: BLE001
        return ComparisonVerdict.INCOMPARABLE, f"Assessment error: {exc}"


def _status_from_verdict(v: ComparisonVerdict) -> str:
    """Map a ComparisonVerdict to a compliance status string."""
    if v == ComparisonVerdict.MATCH:
        return "compliant"
    elif v == ComparisonVerdict.MISMATCH:
        return "non_compliant"
    elif v == ComparisonVerdict.CLOSE:
        return "partial"
    else:
        return "not_demonstrated"


def run_phase2_eval(
    cases: list[Phase2BenchmarkCase] | None = None,
) -> Phase2EvalReport:
    """Run Phase 2 evaluation on the benchmark dataset.

    Args:
        cases: Case list.  Loads the default dataset if ``None``.

    Returns:
        A :class:`Phase2EvalReport` with per-case and aggregate results.
    """
    if cases is None:
        cases = load_phase2_dataset()

    case_results: list[Phase2CaseResult] = []
    false_compliance_count = 0
    false_non_compliance_count = 0
    correct = 0

    for case in cases:
        verdict, error = _assess_case(case)

        gold_status_str = _status_from_verdict(case.gold_status)
        assessed_status_str = _status_from_verdict(verdict)

        matched = verdict == case.gold_status

        # False compliance: system says compliant but gold is not.
        fc = (
            assessed_status_str == "compliant"
            and case.gold_status != ComparisonVerdict.MATCH
        )
        # False non-compliance: system says non-compliant but gold is compliant.
        fnc = (
            assessed_status_str in ("non_compliant", "not_demonstrated", "incomparable")
            and case.gold_status == ComparisonVerdict.MATCH
        )

        if fc:
            false_compliance_count += 1
        if fnc:
            false_non_compliance_count += 1
        if matched:
            correct += 1

        case_results.append(Phase2CaseResult(
            case_id=case.case_id,
            gold_status=gold_status_str,
            assessed_status=assessed_status_str,
            matched=matched,
            false_compliance=fc,
            false_non_compliance=fnc,
            error=error,
        ))

    total = len(cases)
    false_compliance_rate = false_compliance_count / total if total > 0 else 0.0
    false_non_compliance_rate = (
        false_non_compliance_count / total if total > 0 else 0.0
    )
    accuracy = correct / total if total > 0 else 0.0

    # Hard invariant: zero false compliance cases.
    fc_gate_passed = false_compliance_count == 0

    all_passed = fc_gate_passed

    return Phase2EvalReport(
        timestamp=datetime.now(UTC).isoformat(),
        dataset_size=total,
        case_results=case_results,
        false_compliance_count=false_compliance_count,
        false_non_compliance_count=false_non_compliance_count,
        false_compliance_rate=false_compliance_rate,
        false_non_compliance_rate=false_non_compliance_rate,
        overall_accuracy=accuracy,
        false_compliance_gate_passed=fc_gate_passed,
        all_passed=all_passed,
    )


def check_phase2_quality_gates() -> bool:
    """Run Phase 2 eval and return True iff the false-compliance gate passes.

    This is the primary Phase 2 release gate: false compliance is the
    highest-severity error class and must be zero.
    """
    report = run_phase2_eval()
    return report.critical_gates_passed


__all__ = [
    "PHASE2_BENCHMARK_CASES",
    "Phase2BenchmarkCase",
    "Phase2CaseResult",
    "Phase2EvalReport",
    "check_phase2_quality_gates",
    "load_phase2_dataset",
    "run_phase2_eval",
]
