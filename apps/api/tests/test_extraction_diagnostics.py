"""Tests for CP31 extraction diagnostics (pure logic, no DB).

Verifies `compute_diagnostics` count aggregation from an `ExtractionOutcome`:
accepted/rejected/ocr-warning/deduped/promoted, rejection-breakdown grouping,
provider/model/prompt/schema capture from audited LLM calls, and the
reconciliation wiring — without a database or a live provider.
"""

from __future__ import annotations

from tender_compliance_api.extraction.adapter import LlmCallResult
from tender_compliance_api.extraction.diagnostics import compute_diagnostics

# CandidateRecord is a frozen dataclass: import the real thing.
from tender_compliance_api.extraction.extractor import CandidateRecord, ExtractionOutcome
from tender_compliance_api.extraction.prompts import PROMPT_VERSION, SCHEMA_VERSION
from tender_compliance_api.extraction.reconcile import ReconciliationResult


def _call(
    status: str = "completed",
    provider: str = "fake",
    model: str = "fake",
    error: str | None = None,
) -> LlmCallResult:
    return LlmCallResult(
        provider=provider,
        model=model,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        latency_ms=10,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=None,
        finish_reason="stop" if status == "completed" else None,
        status=status,
        error_message=error,
        call_site="extract_candidates",
    )


def _cand(
    *,
    normalized_text: str = "req",
    raw_source: str = "req",
    valid: bool = True,
    persistable: bool = True,
    uncertainty: str = "confirmed",
    requirement_type: str = "obligation",
    ocr_warning: bool = False,
    rejection_reason: str | None = None,
    verbatim_validation: dict[str, object] | None = None,
) -> CandidateRecord:
    return CandidateRecord(
        chunk_id="c1",
        sources_json=None,
        window_text="req",
        normalized_text=normalized_text,
        raw_source=raw_source,
        requirement_type=requirement_type,
        uncertainty=uncertainty,
        clause_number=None,
        group_hint=None,
        ocr_warning=ocr_warning,
        is_valid=valid,
        persistable=persistable,
        rejection_reason=rejection_reason,
        verbatim_validation=verbatim_validation,
    )


# ---------------------------------------------------------------------------
# 1. Counts aggregate correctly across the candidate matrix.
# ---------------------------------------------------------------------------

def test_counts_accepted_rejected_ocr_warning() -> None:
    outcome = ExtractionOutcome(
        candidates=[
            _cand(valid=True, persistable=True),          # accepted
            _cand(raw_source="missing", valid=True, persistable=True),  # accepted
            _cand(valid=False, persistable=False, rejection_reason="fabrication"),  # rejected
            _cand(valid=False, persistable=False, rejection_reason=None),  # rejected, no reason
            _cand(
                valid=True, persistable=False, uncertainty="uncertain",
                ocr_warning=True,
            ),  # ocr warning, not accepted (uncertain)
        ],
        llm_calls=[_call()],
    )
    s = compute_diagnostics(outcome, promoted_count=1)
    assert s.total_candidates == 5
    assert s.accepted_candidates == 2     # valid + persistable
    assert s.rejected_candidates == 2     # not valid
    assert s.ocr_warning_candidates == 1
    assert s.promoted_requirements == 1
    assert s.total_windows == 1
    assert s.total_llm_calls == 1


def test_rejection_breakdown_groups_reasons() -> None:
    outcome = ExtractionOutcome(
        candidates=[
            _cand(valid=False, persistable=False, rejection_reason="fabrication"),
            _cand(valid=False, persistable=False, rejection_reason="fabrication"),
            _cand(valid=False, persistable=False, rejection_reason="no_citation"),
            _cand(valid=False, persistable=False, rejection_reason=None),
            _cand(
                valid=True,
                persistable=True,
                verbatim_validation={"status": "recovered_for_human_review"},
            ),
        ],
        llm_calls=[_call()],
    )
    s = compute_diagnostics(outcome)
    assert s.rejection_breakdown == {
        "fabrication": 2,
        "no_citation": 1,
        "unknown": 1,
        "verbatim_fallback_recovered_for_human_review": 1,
    }
    assert s.rejected_candidates == 4
    assert s.accepted_candidates == 1


def test_ocr_warning_is_independent_of_acceptance() -> None:
    # An OCR-derived candidate that is still valid+persistable keeps both flags.
    outcome = ExtractionOutcome(
        candidates=[
            _cand(valid=True, persistable=True, ocr_warning=True),
        ],
        llm_calls=[_call()],
    )
    s = compute_diagnostics(outcome, promoted_count=1)
    assert s.accepted_candidates == 1
    assert s.ocr_warning_candidates == 1
    assert s.promoted_requirements == 1


# ---------------------------------------------------------------------------
# 2. Versions captured from the first audited LLM call.
# ---------------------------------------------------------------------------

def test_versions_captured_from_first_call() -> None:
    outcome = ExtractionOutcome(
        candidates=[_cand()],
        llm_calls=[_call(provider="openai", model="gpt-4o")],
    )
    s = compute_diagnostics(outcome)
    assert s.provider == "openai"
    assert s.model == "gpt-4o"
    assert s.prompt_version == PROMPT_VERSION
    assert s.schema_version == SCHEMA_VERSION


def test_versions_none_when_no_calls() -> None:
    outcome = ExtractionOutcome(candidates=[_cand()], llm_calls=[])
    s = compute_diagnostics(outcome)
    assert s.total_windows == 0
    assert s.total_llm_calls == 0
    assert s.provider is None
    assert s.model is None
    assert s.promoted_requirements == 0


def test_failed_call_still_provides_versions() -> None:
    outcome = ExtractionOutcome(
        candidates=[],
        llm_calls=[_call(status="failed", error="boom")],
    )
    s = compute_diagnostics(outcome)
    assert s.provider == "fake"
    assert s.model == "fake"
    assert s.total_candidates == 0
    assert s.rejected_candidates == 0


# ---------------------------------------------------------------------------
# 3. Reconciliation wiring (deduped count + summary passthrough).
# ---------------------------------------------------------------------------

def test_deduped_and_summary_from_reconciliation_outcome() -> None:
    outcome = ExtractionOutcome(
        candidates=[
            _cand(),  # window1 -> valid, persistable
            _cand(),  # window2 -> same fingerprint, valid, persistable (deduped)
        ],
        llm_calls=[_call(), _call()],
    )
    recon = ReconciliationResult(
        groups=[],
        input_count=2,
        deduped_count=1,
        flagged_count=0,
        singleton_count=1,
    )
    s = compute_diagnostics(outcome, promoted_count=1, reconciliation_outcome=recon)
    assert s.deduped_candidates == recon.removed_count  # == deduped 1
    assert s.reconciliation_summary == recon.summary()


def test_reconciliation_none_defaults_deduped_zero_summary_none() -> None:
    outcome = ExtractionOutcome(
        candidates=[_cand()], llm_calls=[_call()]
    )
    s = compute_diagnostics(outcome)
    assert s.deduped_candidates == 0
    assert s.reconciliation_summary is None
