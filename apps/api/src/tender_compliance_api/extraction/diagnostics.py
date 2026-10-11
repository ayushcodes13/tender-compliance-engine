"""CP31 — extraction diagnostics (pure, no IO).

Computes a single, developer-facing summary of *why* an EXTRACT stage produced
the candidates it did: how many windows/calls/candidates, how many were
accepted vs rejected (fabrications) vs OCR-uncertain, how many duplicates
reconciliation removed, and how many were promoted to requirements.  Provider /
model / prompt / schema versions are taken from the audited LLM calls so an
operator can reproduce the exact extraction configuration.

This module is pure logic — `DocumentService.capture_extraction_diagnostics`
persists the result; the computation is unit-testable without a database.

Phase 1 boundary: this is diagnostic metadata only — no vendor-compliance
verdicts and no document bodies (rejection reasons are short codes, never raw
text).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from tender_compliance_api.extraction.adapter import LlmCallResult  # noqa: F401  (typing)
from tender_compliance_api.extraction.extractor import ExtractionOutcome
from tender_compliance_api.extraction.reconcile import ReconciliationResult

#: How a diagnostic count is partitioned in ``rejection_breakdown``.
_REJECTION_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExtractionDiagnosticsSummary:
    """Derived, auditable counts for one version's EXTRACT pass (CP31)."""

    total_windows: int
    total_llm_calls: int
    total_candidates: int
    accepted_candidates: int
    rejected_candidates: int
    deduped_candidates: int
    promoted_requirements: int
    ocr_warning_candidates: int
    provider: str | None
    model: str | None
    prompt_version: str | None
    schema_version: str | None
    rejection_breakdown: dict[str, int]
    reconciliation_summary: dict[str, Any] | None


def _versions_from_calls(
    calls: list[LlmCallResult],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Provider/model/prompt/schema versions come from the first audited call.

    All calls in a single EXTRACT pass share the same adapter configuration, so
    the first call (success or failure) is representative.  Returns all-None when
    no calls were made (e.g. zero windows).
    """

    if not calls:
        return None, None, None, None
    first = calls[0]
    return first.provider, first.model, first.prompt_version, first.schema_version


def compute_diagnostics(
    outcome: ExtractionOutcome,
    *,
    promoted_count: int = 0,
    reconciliation_outcome: ReconciliationResult | None = None,
) -> ExtractionDiagnosticsSummary:
    """Build the CP31 diagnostics summary from a stage's extraction outcome.

    Args:
        outcome: The orchestrator result for the version.
        promoted_count: Requirements promoted from these candidates (CP30 return).
        reconciliation_outcome: The CP29 reconciliation result, if run — supplies
            the deduped count and the reconcilation summary JSON.

    Counts:
        - total_windows counts every source window, including literal table
          rows that do not require a primary model call. Fallback validation
          calls are included only in total_llm_calls.
        - accepted  = candidates that are valid AND persistable (promotable).
        - rejected  = candidates that failed source validation (fabrication guard).
        - ocr_warning = candidates drawn from an OCR/structurally-unreliable window
          (regardless of accept/reject).
    """

    candidates = outcome.candidates
    total_candidates = len(candidates)
    accepted = sum(
        1 for c in candidates if c.is_valid and c.persistable
    )
    rejected = sum(1 for c in candidates if not c.is_valid)
    ocr_warning = sum(1 for c in candidates if c.ocr_warning)

    rejection_breakdown: Counter[str] = Counter()
    for c in candidates:
        if not c.is_valid:
            rejection_breakdown[c.rejection_reason or _REJECTION_UNKNOWN] += 1
        fallback_status = (c.verbatim_validation or {}).get("status")
        if fallback_status in {
            "recovered_for_human_review",
            "rejected",
            "provider_failure",
            "fallback_budget_exhausted",
        }:
            rejection_breakdown[f"verbatim_fallback_{fallback_status}"] += 1

    provider, model, prompt_version, schema_version = _versions_from_calls(
        outcome.llm_calls
    )

    recon_summary = (
        reconciliation_outcome.summary()
        if reconciliation_outcome is not None
        else None
    )
    deduped = (
        reconciliation_outcome.removed_count
        if reconciliation_outcome is not None
        else 0
    )

    return ExtractionDiagnosticsSummary(
        total_windows=max(
            len(outcome.window_results),
            sum(1 for call in outcome.llm_calls if call.call_site == "extract_candidates"),
        ),
        total_llm_calls=len(outcome.llm_calls),
        total_candidates=total_candidates,
        accepted_candidates=accepted,
        rejected_candidates=rejected,
        deduped_candidates=deduped,
        promoted_requirements=promoted_count,
        ocr_warning_candidates=ocr_warning,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        rejection_breakdown=dict(rejection_breakdown),
        reconciliation_summary=recon_summary,
    )


__all__ = [
    "ExtractionDiagnosticsSummary",
    "compute_diagnostics",
]
