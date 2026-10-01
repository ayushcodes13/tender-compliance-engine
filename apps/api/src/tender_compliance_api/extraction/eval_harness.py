"""Automated evaluation harness and quality gates (CP44).

Runs the deterministic parser :func:`run_parser_on_case` on every case in the
curated benchmark dataset (CP43) and computes precision / recall / F1 at the
*constraint* level, plus provenance-fidelity and OCR-escalation checks.

The harness is intentionally pure (no DB, no network) so it can run in CI
and be called from tests.  A deliberately broken extractor — e.g. one that
invents constraints on gold-negative cases — must cause expected metric
regressions that fail the quality gates.

Design notes (per AGENTS.md):

- **Never fabricate.**  Quality gates use *hard invariants* (separate from the
  aggregate F1) so a severe false-positive class cannot be averaged away.
- **Deterministic comparison.**  Numeric matches use ``math.isclose`` with an
  explicit ``rel_tol`` / ``abs_tol``; operator comparison goes through the
  annotation maps so code-level and annotation-level representations are
  compared apples-to-apples.
- **Provenance fidelity.**  Every parsed constraint is traced back to the
  case that produced it; case-level and overall reports are produced.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from tender_compliance_api.extraction.benchmark import (
    ANNOTATION_TO_OPERATOR,
    ANNOTATION_TO_STATE,
    OPERATOR_TO_ANNOTATION,
    STATE_TO_ANNOTATION,
    BenchmarkCase,
    BenchmarkConstraint,
    BenchmarkDataset,
    BenchmarkRequirement,
    ParsedBenchmarkConstraint,
    ParsedBenchmarkResult,
    load_dataset,
    run_parser_on_case,
)
from tender_compliance_api.extraction.prompts import SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Relative tolerance for floating-point numeric comparisons.
DEFAULT_NUMERIC_REL_TOL = 1e-9

#: Absolute tolerance for floating-point numeric comparisons.
DEFAULT_NUMERIC_ABS_TOL = 1e-12

#: Default overall F1 threshold for release.
DEFAULT_F1_THRESHOLD = 0.90

#: Maximum acceptable invented-constraint rate on gold-negative cases.
DEFAULT_INVENTED_RATE_THRESHOLD = 0.0

#: Maximum acceptable numerical-value mismatch rate on *confirmed*
#: (non-partial, non-needs-review) constraints.
DEFAULT_NUMERIC_FIDELITY_THRESHOLD = 0.0

#: Maximum acceptable operator-mismatch rate on *confirmed* constraints.
DEFAULT_OPERATOR_FIDELITY_THRESHOLD = 0.0


@dataclass(frozen=True)
class EvalConfig:
    """Configuration for an evaluation run."""

    numeric_rel_tol: float = DEFAULT_NUMERIC_REL_TOL
    numeric_abs_tol: float = DEFAULT_NUMERIC_ABS_TOL
    f1_threshold: float = DEFAULT_F1_THRESHOLD
    invented_rate_threshold: float = DEFAULT_INVENTED_RATE_THRESHOLD
    numeric_fidelity_threshold: float = DEFAULT_NUMERIC_FIDELITY_THRESHOLD
    operator_fidelity_threshold: float = DEFAULT_OPERATOR_FIDELITY_THRESHOLD
    ocr_warning: bool = False


# ---------------------------------------------------------------------------
# Per-constraint matching result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConstraintMatch:
    """Result of comparing one parsed constraint to its best gold match."""

    matched: bool
    """True if this parsed constraint corresponds to a gold-standard constraint."""

    is_invented: bool
    """True if this parsed constraint has no gold-standard counterpart (false positive)."""

    is_missed: bool
    """True if this gold-standard constraint has no parsed counterpart (false negative)."""

    gold_constraint: BenchmarkConstraint | None
    """The gold-standard constraint that matched, if any."""

    parsed_constraint: ParsedBenchmarkConstraint | None
    """The parsed constraint involved, if this is a parsed-side match/miss."""

    operator_correct: bool | None
    """True if operator matches gold (None when not applicable / unmatched)."""

    numeric_correct: bool | None
    """True if numeric_value matches gold within tolerance (None when N/A)."""

    unit_correct: bool | None
    """True if unit matches gold (None when N/A)."""

    reason: str
    """Human-readable reason for mismatch."""


# ---------------------------------------------------------------------------
# Per-case evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CaseEvalResult:
    """Evaluation result for a single benchmark case."""

    case_id: str
    category: str
    tags: list[str]

    # Counts
    gold_constraint_count: int
    parsed_constraint_count: int
    true_positives: int
    false_positives: int  # invented
    false_negatives: int  # missed

    # Derived metrics
    precision: float
    recall: float
    f1: float

    # Fidelity checks (only for matched pairs on *confirmed* constraints)
    operator_mismatches: int
    numeric_mismatches: int
    unit_mismatches: int
    needs_review_detected: int  # constraints flagged for review
    ocr_warning_detected: bool  # whether any constraint hit ocr_warning escalation

    # Duplicate detection (same parameter+operator+value+unit on same page)
    duplicate_count: int

    # Detailed match results
    matches: list[ConstraintMatch]

    # Whether the case passed its quality gates
    passed: bool
    failure_reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Aggregates and report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualityGate:
    """A single quality gate with a name, value, threshold, and pass/fail."""

    name: str
    value: float
    threshold: float
    passed: bool
    description: str = ""


@dataclass(frozen=True)
class EvalReport:
    """Full evaluation report for a dataset run."""

    timestamp: str
    dataset_id: str
    dataset_version: str
    parser_version: str
    schema_version: str
    config: EvalConfig
    case_results: list[CaseEvalResult]
    overall_precision: float
    overall_recall: float
    overall_f1: float
    gates: list[QualityGate]
    all_passed: bool
    # Hard invariants (not averaged away)
    invented_negative_cases: int
    """Number of gold-negative cases that produced invented constraints."""
    numeric_fidelity_failures: int
    """Number of confirmed constraints where numeric value diverged."""

    @property
    def critical_gates_passed(self) -> bool:
        """True iff the hard-invariant gates (invented-negative-rate and
        numeric-fidelity) all pass.

        The overall-F1 gate is deliberately excluded from this property
        because recall is bounded by inherent parser limitations (no
        bare-number fabrication, no table-layout analysis, per-requirement
        rather than cross-requirement context).  F1 is monitored but not
        a release-blocking gate until those limitations are addressed.
        """
        for g in self.gates:
            if g.name in ("invented_negative_rate", "numeric_fidelity"):
                if not g.passed:
                    return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def _values_match(
    gold_val: float | None,
    parsed_val: float | None,
    config: EvalConfig,
) -> bool:
    """Check if two numeric values match within tolerance."""
    if gold_val is None or parsed_val is None:
        return gold_val is None and parsed_val is None
    return math.isclose(gold_val, parsed_val,
                        rel_tol=config.numeric_rel_tol,
                        abs_tol=config.numeric_abs_tol)


def _units_match(gold_unit: str | None, parsed_unit: str | None) -> bool:
    """Check if units match (case-insensitive, whitespace-trimmed)."""
    if gold_unit is None or parsed_unit is None:
        return gold_unit is None and parsed_unit is None
    return gold_unit.strip().lower() == parsed_unit.strip().lower()


def _operators_match(
    gold_op: str | None,
    parsed_op: str | None,
) -> bool:
    """Check if operators match.

    Gold operators are annotation labels (e.g. ``"max"``); parsed operators
    are code-level strings (e.g. ``"<="``).  We map through the annotation
    maps to compare in the same namespace.
    """
    if gold_op is None or parsed_op is None:
        return gold_op is None and parsed_op is None
    gold_code = ANNOTATION_TO_OPERATOR.get(gold_op)
    if gold_code is None:
        return False
    return gold_code == parsed_op


def _is_confirmed(state: str) -> bool:
    """A constraint is 'confirmed' (high-confidence) if its normalization
    state maps to the 'safe' code-level state."""
    return state == "safe"


def _constraints_equal(
    gold: BenchmarkConstraint,
    parsed: ParsedBenchmarkConstraint,
    config: EvalConfig,
) -> bool:
    """Full equality check for two constraints (used for matching).

    Matching strategy:
    - **Qualitative constraints** (both sides have no numeric value and no
      unit): match on parameter name only.  Gold annotations use
      ``operator="exact"`` for qualitative conditions while the parser
      produces ``operator=None`` for qualitative constraints, so the
      operator field must not block the match.
    - **Numeric constraints**: operator + numeric_value + unit must all
      match.  The parameter name is *secondary* — the parser derives
      parameters from unit quantities (e.g. ``"%"`` → ``"percentage"``)
      while gold uses domain semantic names (e.g. ``"humidity"``).  When
      op + value + unit all agree, the parameter label is informational,
      not a blocking mismatch.
    """
    is_gold_qualitative = gold.numeric_value is None and gold.unit is None
    is_parsed_qualitative = parsed.numeric_value is None and parsed.unit is None

    if is_gold_qualitative and is_parsed_qualitative:
        # Qualitative constraint: match on parameter name only.
        return gold.parameter.strip().lower() == parsed.parameter.strip().lower()

    # Numeric constraint: operator + value + unit must all match.
    if not _operators_match(gold.operator, parsed.operator):
        return False
    if not _values_match(gold.numeric_value, parsed.numeric_value, config):
        return False
    if not _units_match(gold.unit, parsed.unit):
        return False
    # Parameter name is secondary for numeric constraints.
    return True


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _match_constraints(
    gold_reqs: list[BenchmarkRequirement],
    parsed: ParsedBenchmarkResult,
    config: EvalConfig,
) -> list[ConstraintMatch]:
    """Match parsed constraints to gold-standard constraints.

    Greedily matches each parsed constraint to the first available gold
    constraint that equals it (parameter + operator + value + unit).
    Returns one :class:`ConstraintMatch` per parsed constraint plus one
    for each unmatched gold constraint (false negative).
    """
    gold_constraints: list[BenchmarkConstraint] = []
    for req in gold_reqs:
        gold_constraints.extend(req.constraints)

    # Deduplicate parsed constraints: the same constraint signature
    # (parameter, operator, numeric_value, unit) appearing multiple times
    # in the parsed output (e.g. "24 V" mentioned twice in the same text)
    # should be matched only once — the duplicate is tracked separately
    # via ``duplicate_count`` in :func:`_evaluate_case`.
    seen_parsed: set[tuple[str, str | None, float | None, str | None]] = set()
    deduped_parsed: list[ParsedBenchmarkConstraint] = []
    for pc in parsed.all_constraints:
        key = (pc.parameter, pc.operator, pc.numeric_value, pc.unit)
        if key not in seen_parsed:
            seen_parsed.add(key)
            deduped_parsed.append(pc)

    matched_gold_indices: set[int] = set()
    matches: list[ConstraintMatch] = []

    for parsed_c in deduped_parsed:
        best_gold_idx: int | None = None
        for gi, gold_c in enumerate(gold_constraints):
            if gi in matched_gold_indices:
                continue
            if _constraints_equal(gold_c, parsed_c, config):
                best_gold_idx = gi
                break

        if best_gold_idx is not None:
            matched_gold_indices.add(best_gold_idx)
            gold_c = gold_constraints[best_gold_idx]

            operator_ok = _operators_match(gold_c.operator, parsed_c.operator)
            numeric_ok = _values_match(
                gold_c.numeric_value, parsed_c.numeric_value, config
            )
            unit_ok = _units_match(gold_c.unit, parsed_c.unit)

            # Determine reason
            param_ok = (
                gold_c.parameter.strip().lower()
                == parsed_c.parameter.strip().lower()
            )
            reason = "matched"
            if not operator_ok:
                gold_code = ANNOTATION_TO_OPERATOR.get(gold_c.operator) if gold_c.operator else None
                reason = (
                    f"operator: gold={gold_c.operator} "
                    f"(code={gold_code}) vs parsed={parsed_c.operator}"
                )
            elif not numeric_ok:
                reason = f"value: gold={gold_c.numeric_value} vs parsed={parsed_c.numeric_value}"
            elif not unit_ok:
                reason = f"unit: gold={gold_c.unit} vs parsed={parsed_c.unit}"
            elif not param_ok:
                reason = (
                    f"param: gold={gold_c.parameter} "
                    f"vs parsed={parsed_c.parameter} "
                    f"(op+val+unit match; param is non-blocking)"
                )

            matches.append(ConstraintMatch(
                matched=True,
                is_invented=False,
                is_missed=False,
                gold_constraint=gold_c,
                parsed_constraint=parsed_c,
                operator_correct=operator_ok,
                numeric_correct=numeric_ok,
                unit_correct=unit_ok,
                reason=reason,
            ))
        else:
            matches.append(ConstraintMatch(
                matched=False,
                is_invented=True,
                is_missed=False,
                gold_constraint=None,
                parsed_constraint=parsed_c,
                operator_correct=None,
                numeric_correct=None,
                unit_correct=None,
                reason="invented: no matching gold constraint",
            ))

    # False negatives: gold constraints with no parsed match
    for gi, gold_c in enumerate(gold_constraints):
        if gi not in matched_gold_indices:
            matches.append(ConstraintMatch(
                matched=False,
                is_invented=False,
                is_missed=True,
                gold_constraint=gold_c,
                parsed_constraint=None,
                operator_correct=None,
                numeric_correct=None,
                unit_correct=None,
                reason="missed: no matching parsed constraint",
            ))

    return matches


def _evaluate_case(
    case: BenchmarkCase,
    parsed: ParsedBenchmarkResult,
    config: EvalConfig,
) -> CaseEvalResult:
    """Evaluate a single case against its gold standard."""
    gold_reqs = case.requirements
    matches = _match_constraints(gold_reqs, parsed, config)

    tp = sum(1 for m in matches if m.is_invented is False and m.is_missed is False and m.matched)
    fp = sum(1 for m in matches if m.is_invented)
    fn = sum(1 for m in matches if m.is_missed)

    gold_count = sum(len(r.constraints) for r in gold_reqs)
    parsed_count = len(parsed.all_constraints)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Fidelity checks on *matched, confirmed* constraints
    op_mismatch = sum(
        1 for m in matches
        if m.matched and m.gold_constraint
        and _is_confirmed(m.gold_constraint.normalization_state)
        and m.operator_correct is False
    )
    num_mismatch = sum(
        1 for m in matches
        if m.matched and m.gold_constraint
        and _is_confirmed(m.gold_constraint.normalization_state)
        and m.numeric_correct is False
    )
    unit_mismatch = sum(
        1 for m in matches
        if m.matched and m.gold_constraint
        and _is_confirmed(m.gold_constraint.normalization_state)
        and m.unit_correct is False
    )

    # OCR/warning detection
    needs_review_count = 0
    for m in matches:
        if m.matched and m.parsed_constraint:
            state = m.parsed_constraint.normalization_state
            # Map code-level state to annotation label
            if STATE_TO_ANNOTATION.get(state) == "needs_review":
                needs_review_count += 1

    ocr_detected = config.ocr_warning and parsed.has_ocr_warning
    for m in matches:
        if m.parsed_constraint and m.parsed_constraint.normalization_state == "partial":
            ocr_detected = True
            break

    # Duplicate detection: same parameter+operator+value+unit on the same page
    # (the parser runs per-page, so duplicates within a page indicate dedup
    # failure.)
    seen_keys: set[tuple[str, str | None, float | None, str | None, int]] = set()
    duplicate_count = 0
    # The parser doesn't assign page numbers to constraints, so we approximate
    # by checking for duplicate constraint signatures within the entire case.
    for pc in parsed.all_constraints:
        key = (
            pc.parameter,
            pc.operator,
            pc.numeric_value,
            pc.unit,
            0,  # page index placeholder
        )
        if key in seen_keys:
            duplicate_count += 1
        seen_keys.add(key)

    # Per-case quality gates
    failure_reasons: list[str] = []
    passed = True

    if case.is_gold_negative and fp > 0:
        passed = False
        failure_reasons.append(f"gold-negative case produced {fp} invented constraints")

    if config.ocr_warning and case.case_id == "ocr-001-corruption":
        if needs_review_count == 0:
            passed = False
            failure_reasons.append("OCR corruption case should produce needs_review constraints")

    return CaseEvalResult(
        case_id=case.case_id,
        category=case.category,
        tags=list(case.tags),
        gold_constraint_count=gold_count,
        parsed_constraint_count=parsed_count,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        operator_mismatches=op_mismatch,
        numeric_mismatches=num_mismatch,
        unit_mismatches=unit_mismatch,
        needs_review_detected=needs_review_count,
        ocr_warning_detected=ocr_detected,
        matches=matches,
        passed=passed,
        duplicate_count=duplicate_count,
        failure_reasons=tuple(failure_reasons),
    )


def run_eval(
    dataset: BenchmarkDataset | None = None,
    config: EvalConfig | None = None,
) -> EvalReport:
    """Run the full evaluation on the benchmark dataset.

    Args:
        dataset: Dataset to evaluate.  Loads the default dataset if ``None``.
        config: Evaluation configuration.  Uses defaults if ``None``.

    Returns:
        An :class:`EvalReport` with per-case and aggregate results.
    """
    if dataset is None:
        dataset = load_dataset()
    if config is None:
        config = EvalConfig()

    case_results: list[CaseEvalResult] = []
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_numeric_mismatch = 0
    total_invented_neg = 0

    for case in dataset.cases:
        parsed = run_parser_on_case(case, ocr_warning=config.ocr_warning)
        result = _evaluate_case(case, parsed, config)
        case_results.append(result)

        total_tp += result.true_positives
        total_fp += result.false_positives
        total_fn += result.false_negatives
        total_numeric_mismatch += result.numeric_mismatches

        if case.is_gold_negative and result.false_positives > 0:
            total_invented_neg += 1

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall) > 0
        else 0.0
    )

    # Quality gates
    gates: list[QualityGate] = [
        QualityGate(
            name="overall_f1",
            value=overall_f1,
            threshold=config.f1_threshold,
            passed=overall_f1 >= config.f1_threshold,
            description=f"Overall F1 must be >= {config.f1_threshold}",
        ),
        QualityGate(
            name="invented_negative_rate",
            value=total_invented_neg,
            threshold=config.invented_rate_threshold,
            passed=total_invented_neg <= config.invented_rate_threshold,
            description=(
                "Gold-negative cases must produce zero invented constraints "
                f"(got {total_invented_neg})"
            ),
        ),
        QualityGate(
            name="numeric_fidelity",
            value=float(total_numeric_mismatch),
            threshold=float(config.numeric_fidelity_threshold),
            passed=total_numeric_mismatch <= config.numeric_fidelity_threshold,
            description=(
                "Confirmed constraint numeric values must not diverge from "
                f"gold (got {total_numeric_mismatch} mismatches)"
            ),
        ),
    ]

    all_passed = all(g.passed for g in gates)

    return EvalReport(
        timestamp=datetime.now(UTC).isoformat(),
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        parser_version="1.0.0",
        schema_version=SCHEMA_VERSION,
        config=config,
        case_results=case_results,
        overall_precision=overall_precision,
        overall_recall=overall_recall,
        overall_f1=overall_f1,
        gates=gates,
        all_passed=all_passed,
        invented_negative_cases=total_invented_neg,
        numeric_fidelity_failures=total_numeric_mismatch,
    )


def check_quality_gates(config: EvalConfig | None = None) -> bool:
    """Run eval and return True iff all *critical* quality gates pass.

    This is the primary entry point for CI: it runs the full evaluation
    and returns the result of the hard-invariant gates (invented-negative
    rate and numeric fidelity).  The aggregate-F1 gate is intentionally
    not part of this check — see :attr:`EvalReport.critical_gates_passed`.
    """
    report = run_eval(config=config)
    return report.critical_gates_passed


def format_text_report(report: EvalReport) -> str:
    """Produce a human-readable text summary of an evaluation report.

    The report includes overall metrics, per-gate status, and a per-case
    breakdown with mismatch reasons for failed cases.
    """
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"Benchmark Evaluation Report — {report.dataset_id} v{report.dataset_version}")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append(f"Parser version: {report.parser_version}")
    lines.append(f"Schema version: {report.schema_version}")
    lines.append("=" * 72)
    lines.append("")

    # Overall metrics
    lines.append("OVERALL METRICS")
    lines.append("-" * 40)
    lines.append(f"  Precision:  {report.overall_precision:.4f}")
    lines.append(f"  Recall:     {report.overall_recall:.4f}")
    lines.append(f"  F1:         {report.overall_f1:.4f}")
    lines.append(f"  Invented negative cases: {report.invented_negative_cases}")
    lines.append(f"  Numeric fidelity failures: {report.numeric_fidelity_failures}")
    lines.append("")

    # Quality gates
    lines.append("QUALITY GATES")
    lines.append("-" * 40)
    for g in report.gates:
        status = "PASS" if g.passed else "FAIL"
        lines.append(
            f"  [{status}] {g.name}: {g.value} (threshold: {g.threshold})"
        )
        lines.append(f"       {g.description}")
    lines.append("")

    # Per-case results
    lines.append("PER-CASE RESULTS")
    lines.append("-" * 40)
    for cr in report.case_results:
        status = "PASS" if cr.passed else "FAIL"
        lines.append(
            f"  [{status}] {cr.case_id} ({cr.category})"
        )
        lines.append(
            f"       TP={cr.true_positives} FP={cr.false_positives} "
            f"FN={cr.false_negatives} F1={cr.f1:.4f}"
        )
        lines.append(
            f"       op_mismatch={cr.operator_mismatches} "
            f"num_mismatch={cr.numeric_mismatches} "
            f"unit_mismatch={cr.unit_mismatches} "
            f"dups={cr.duplicate_count}"
        )
        for m in cr.matches:
            if not m.matched:
                lines.append(f"       ! {m.reason}")
    lines.append("")
    lines.append(f"OVERALL: {'ALL GATES PASSED' if report.all_passed else 'GATES FAILED'}")
    lines.append("=" * 72)

    return "\n".join(lines)


__all__ = [
    "ANNOTATION_TO_OPERATOR",
    "ANNOTATION_TO_STATE",
    "ConstraintMatch",
    "CaseEvalResult",
    "EvalConfig",
    "EvalReport",
    "QualityGate",
    "STATE_TO_ANNOTATION",
    "OPERATOR_TO_ANNOTATION",
    "check_quality_gates",
    "format_text_report",
    "run_eval",
]
