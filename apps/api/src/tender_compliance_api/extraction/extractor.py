"""Requirement-candidate extraction orchestration (CP28).

Bridges the CP27 :class:`SourceWindow` chunks to the CP26
:class:`LlmAdapter`, producing validated :class:`CandidateRecord`s — one per
model-proposed :class:`RequirementCandidate` — anchored to their trusted source
window.  The orchestrator is **pure logic** (no I/O); persistence is delegated
to :class:`~tender_compliance_api.document.DocumentService` and audit logging
to a caller-supplied ``log_call`` callback, so the extraction behavior is
unit-testable without a database (via :class:`FakeLlmAdapter`).

Behaviour mapped to CP28:

1. *Extract explicit requirements only* — the LLM receives a bounded window;
   nothing is invented from empty input.
2. *Preserve numbers/units/conditions/modal language* — the candidate schema
   (CP25) carries them through unchanged.
3. *Split / group* — the model emits one candidate per independent obligation
   (split) or one candidate spanning several sentences (group); the orchestrator
   preserves both shapes.
4. *Parent/child* — `group_hint` is passed through for CP29 grouping.
6. *Abstention* — ABSTAIN candidates are produced by the model and marked
   non-persistable (``is_persistable=False``); they are not silently dropped,
   so "invented requirement rate" (verification) is measurable.
7. *Flag OCR/structure uncertainty* — a candidate drawn from a window whose
   :attr:`SourceWindow.ocr_warning` is set is elevated from ``CONFIRMED`` to
   ``UNCERTAIN`` (never presented as certain when its source text is
   unreliable).
8. *Validate before reconciliation* — each candidate is paired with its
   window's primary :class:`TrustedSourceContext` and
   :meth:`SourcedRequirementCandidate.validate_source` enforces that
   ``raw_source`` is a real substring of the trusted window text (CP25
   boundary).  Candidates that fail are recorded ``is_valid=False`` with a
   ``rejection_reason`` (audit signal for the invented-requirement rate).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from tender_compliance_api.errors import PROCESSING_STAGE_FAILURE
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallError,
    LlmCallResult,
)
from tender_compliance_api.extraction.chunking import SourceWindow
from tender_compliance_api.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionResponse,
)
from tender_compliance_api.extraction.schema import (
    CandidateValidationError,
    RequirementCandidate,
    SourcedRequirementCandidate,
    UncertaintyLevel,
)

#: Marker on LlmCallConfig identifying the extraction entry point (CP28).
_EXTRACT_CALL_SITE = "extract_candidates"


@dataclass(frozen=True)
class CandidateRecord:
    """A single model-proposed requirement, ready to persist (CP28).

    One row maps directly to ``extraction_candidates`` (see
    :meth:`DocumentService.store_extraction_candidates`).  ``is_valid`` is
    False when the candidate failed source validation (a potential
    fabrication); such rows are recorded for audit but are never promoted to a
    persisted requirement by CP30.
    """

    chunk_id: str
    sources_json: list[dict[str, Any]]
    window_text: str
    normalized_text: str
    raw_source: str
    requirement_type: str
    uncertainty: str
    clause_number: str | None
    group_hint: str | None
    ocr_warning: bool
    is_valid: bool
    persistable: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class ExtractionOutcome:
    """Result of extracting candidates across one or more windows."""

    candidates: list[CandidateRecord]
    llm_calls: list[LlmCallResult]


def _compose_input(window: SourceWindow) -> str:
    """Assemble the user payload for one window (overlap then content).

    The untrusted overlap text (the previous window's tail) is included so a
    cross-boundary requirement has context, but it is still passed only as the
    user message — document text never reaches system instructions.
    """

    if window.overlap:
        return f"{window.overlap}\n\n{window.text}"
    return window.text


def _bump_uncertainty(
    candidate: RequirementCandidate, ocr_warning: bool
) -> RequirementCandidate:
    """Elevate CONFIRMED -> UNCERTAIN when the source window is unreliable.

    A candidate drawn from an OCR-derived / structurally-errored page must not
    be presented as certain (CP28.7 / AGENTS: "unreviewed uncertainty
    presented as certain" is a highest-risk failure).
    """

    if ocr_warning and candidate.uncertainty is UncertaintyLevel.CONFIRMED:
        return candidate.model_copy(
            update={"uncertainty": UncertaintyLevel.UNCERTAIN}
        )
    return candidate


def _iter_candidates(result: ExtractResult) -> list[RequirementCandidate]:
    """Extract the candidate list from a parsed LLM response."""

    response = cast(ExtractionResponse, result.response)
    return list(response.candidates)


def _to_record(window: SourceWindow, candidate: RequirementCandidate) -> CandidateRecord:
    """Convert a model candidate into a validated, source-anchored record.

    Uses the window's primary source context (``sources[0]``) — which carries
    the window's full trusted text as ``source_text`` — so
    :meth:`SourcedRequirementCandidate.validate_source` enforces the CP25
    citation-substring boundary.  ABSTAIN candidates are kept (marking
    ``persistable=False``) so the invented/non-requirement rate is measurable.
    """

    primary = window.sources[0] if window.sources else None
    adjusted = _bump_uncertainty(candidate, window.ocr_warning)

    is_valid = False
    rejection_reason: str | None = None
    if primary is not None:
        sourced = SourcedRequirementCandidate(candidate=adjusted, source=primary)
        try:
            sourced.validate_source()
            is_valid = True
        except CandidateValidationError as exc:
            # raw_source is not a substring of the trusted window -> the model
            # relocated/invented a citation.  Record for audit, do not persist
            # as a requirement (AGENTS: "never fabricate a citation").
            rejection_reason = str(exc)

    persistable = is_valid and (
        adjusted.uncertainty is UncertaintyLevel.CONFIRMED
    )

    return CandidateRecord(
        chunk_id=window.chunk_id,
        sources_json=[s.model_dump(mode="json") for s in window.sources],
        window_text=window.text,
        normalized_text=adjusted.normalized_text,
        raw_source=adjusted.raw_source,
        requirement_type=adjusted.requirement_type.value,
        uncertainty=adjusted.uncertainty.value,
        clause_number=adjusted.clause_section,
        group_hint=adjusted.group_hint,
        ocr_warning=window.ocr_warning,
        is_valid=is_valid,
        persistable=persistable,
        rejection_reason=rejection_reason,
    )


async def extract_from_windows(
    windows: list[SourceWindow],
    llm: LlmAdapter,
    *,
    log_call: Callable[[LlmCallResult], Awaitable[Any]],
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION,
) -> ExtractionOutcome:
    """Extract requirement candidates from a list of source windows.

    Args:
        windows: Ordered, trusted source windows (from CP27).
        llm: The adapter to call (FakeLlmAdapter in tests, OpenAiLlmAdapter in
            production).
        log_call: Audit callback invoked once per LLM call (success or
            failure) with the :class:`LlmCallResult` to persist (CP26
            ``extraction_runs``).
        prompt_version / schema_version: Recorded on every audit row.

    Returns:
        One :class:`CandidateRecord` per proposed candidate, plus the list of
        audited :class:`LlmCallResult`s.  Per-window LLM failures
        (:class:`LlmCallError`) are logged and the window is skipped — the
        stage still completes so a transient provider outage does not strand
        the whole document version (CP31 hardens retry semantics).
    """

    if not windows:
        return ExtractionOutcome(candidates=[], llm_calls=[])

    config = LlmCallConfig(
        provider=llm.provider,
        model=llm.model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        call_site=_EXTRACT_CALL_SITE,
    )

    candidates: list[CandidateRecord] = []
    llm_calls: list[LlmCallResult] = []

    for window in windows:
        user_text = _compose_input(window)
        try:
            result = await llm.extract(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_text=user_text,
                response_model=ExtractionResponse,
                config=config,
            )
        except LlmCallError:
            # Log the failed call (audit) and move on rather than failing the
            # whole stage — candidates from other windows may still be valid.
            failed = LlmCallResult(
                provider=config.provider,
                model=config.model,
                prompt_version=config.prompt_version,
                schema_version=config.schema_version,
                latency_ms=0,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                cost_usd=None,
                finish_reason=None,
                status="failed",
                error_message=PROCESSING_STAGE_FAILURE,
                call_site=config.call_site,
            )
            await log_call(failed)
            llm_calls.append(failed)
            continue

        await log_call(result.call)
        llm_calls.append(result.call)

        for cand in _iter_candidates(result):
            candidates.append(_to_record(window, cand))

    return ExtractionOutcome(candidates=candidates, llm_calls=llm_calls)


__all__ = ["CandidateRecord", "ExtractionOutcome", "extract_from_windows"]
