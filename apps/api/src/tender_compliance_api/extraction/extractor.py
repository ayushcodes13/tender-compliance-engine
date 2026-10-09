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

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
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
from tender_compliance_api.extraction.coverage_audit import (
    audit_page_image_coverage,
    audit_window_coverage,
    quote_is_present_in_source,
)
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
from tender_compliance_api.extraction.verbatim_validation import (
    MAX_FALLBACKS_PER_WINDOW,
    _valid_positive,
    validate_candidate,
)

#: Marker on LlmCallConfig identifying the extraction entry point (CP28).
_EXTRACT_CALL_SITE = "extract_candidates"
MAX_CONCURRENT_EXTRACTION_WINDOWS = 4


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
    verbatim_validation: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExtractionOutcome:
    """Result of extracting candidates across one or more windows."""

    candidates: list[CandidateRecord]
    llm_calls: list[LlmCallResult]
    window_results: list[WindowExtractionResult] = field(default_factory=list)


@dataclass(frozen=True)
class WindowExtractionResult:
    """Auditable call outcome for one deterministic source window."""

    chunk_id: str
    window_index: int
    call_status: str
    candidate_count: int
    ocr_warning: bool
    source_spans: list[dict[str, Any]]
    coverage_status: str = "not_run"
    coverage_error_category: str | None = None
    potential_omissions: list[dict[str, Any]] = field(default_factory=list)


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
        verbatim_validation=None,
    )


async def extract_from_windows(
    windows: list[SourceWindow],
    llm: LlmAdapter,
    *,
    log_call: Callable[[LlmCallResult], Awaitable[Any]],
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION,
    enable_verbatim_fallback: bool = False,
    enable_obligation_coverage_audit: bool = False,
    coverage_page_images: Mapping[int, bytes] | None = None,
    coverage_page_texts: Mapping[int, str] | None = None,
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

    @dataclass(frozen=True)
    class _WindowOutcome:
        candidates: list[CandidateRecord]
        calls: list[LlmCallResult]
        result: WindowExtractionResult

    async def audit_text_coverage(
        window: SourceWindow, emitted_quotes: list[str]
    ) -> tuple[str, list[dict[str, Any]], LlmCallResult]:
        """Audit one source-bounded text window and retain its page if unique."""
        result = await audit_window_coverage(window.text, emitted_quotes, llm)
        page_texts = coverage_page_texts or {}
        page_numbers = sorted(
            {source.page_number for source in window.sources if source.page_number is not None}
        )
        text_omissions: list[dict[str, Any]] = []
        for quote in result.potential_omissions:
            matches = [
                page_number
                for page_number in page_numbers
                if page_number in page_texts
                and quote_is_present_in_source(page_texts[page_number], quote)
            ]
            text_omissions.append(
                {
                    "page_number": matches[0] if len(matches) == 1 else None,
                    "source_quote": quote,
                }
            )
        return result.status, text_omissions, result.call

    async def process_window(
        window_index: int, window: SourceWindow, semaphore: asyncio.Semaphore
    ) -> _WindowOutcome:
        async with semaphore:
            calls: list[LlmCallResult] = []
            window_candidates: list[CandidateRecord] = []
            source_spans = [
                {
                    "page_number": source.page_number,
                    "clause_number": source.clause_number,
                    "char_start": source.char_start,
                    "char_end": source.char_end,
                }
                for source in window.sources
            ]
            coverage_status = "not_run"
            coverage_error_category: str | None = None
            try:
                result = await llm.extract(
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    user_text=_compose_input(window),
                    response_model=ExtractionResponse,
                    config=config,
                )
            except LlmCallError:
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
                calls.append(failed)
                failed_omissions: list[dict[str, Any]] = []
                if enable_obligation_coverage_audit and not window.ocr_warning:
                    coverage_status, failed_omissions, coverage_call = await audit_text_coverage(
                        window, []
                    )
                    calls.append(coverage_call)
                    coverage_error_category = coverage_call.error_category
                return _WindowOutcome(
                    candidates=[],
                    calls=calls,
                    result=WindowExtractionResult(
                        chunk_id=window.chunk_id,
                        window_index=window_index,
                        call_status="failed",
                        candidate_count=0,
                        ocr_warning=window.ocr_warning,
                        source_spans=source_spans,
                        coverage_status=coverage_status,
                        coverage_error_category=coverage_error_category,
                        potential_omissions=failed_omissions,
                    ),
                )

            calls.append(result.call)
            fallback_calls = 0
            for cand in _iter_candidates(result):
                record = _to_record(window, cand)
                if not record.is_valid and enable_verbatim_fallback:
                    trusted_text = window.sources[0].source_text if window.sources else None
                    if trusted_text and len(window.sources) == 1:
                        if fallback_calls >= MAX_FALLBACKS_PER_WINDOW:
                            record = replace(
                                record, verbatim_validation={"status": "fallback_budget_exhausted"}
                            )
                        else:
                            fallback_calls += 1
                            validation, fallback_call = await validate_candidate(
                                cand, trusted_text, llm
                            )
                            calls.append(fallback_call)
                            if validation is not None and _valid_positive(
                                cand, validation, trusted_text
                            ):
                                recovered = cand.model_copy(
                                    update={
                                        "raw_source": validation.matched_source,
                                        "uncertainty": UncertaintyLevel.UNCERTAIN,
                                    }
                                )
                                recovered_record = _to_record(window, recovered)
                                if recovered_record.is_valid:
                                    record = replace(
                                        recovered_record,
                                        persistable=True,
                                        rejection_reason=None,
                                        verbatim_validation={
                                            "status": "recovered_for_human_review",
                                            "confidence": float(validation.confidence),
                                            "original_quote": cand.raw_source,
                                        },
                                    )
                            else:
                                record = replace(
                                    record,
                                    verbatim_validation={
                                        "status": "rejected"
                                        if validation is not None
                                        else "provider_failure",
                                        "verdict": validation.verdict
                                        if validation is not None
                                        else None,
                                        "confidence": float(validation.confidence)
                                        if validation is not None
                                        else None,
                                    },
                                )
                window_candidates.append(record)

            window_omissions: list[dict[str, Any]] = []
            if enable_obligation_coverage_audit and not window.ocr_warning:
                emitted_quotes = [
                    record.raw_source for record in window_candidates if record.is_valid
                ]
                coverage_status, window_omissions, coverage_call = await audit_text_coverage(
                    window, emitted_quotes
                )
                calls.append(coverage_call)
                coverage_error_category = coverage_call.error_category

            return _WindowOutcome(
                candidates=window_candidates,
                calls=calls,
                result=WindowExtractionResult(
                    chunk_id=window.chunk_id,
                    window_index=window_index,
                    call_status="completed" if result.call.status == "completed" else "failed",
                    candidate_count=len(window_candidates),
                    ocr_warning=window.ocr_warning,
                    source_spans=source_spans,
                    coverage_status=coverage_status,
                    coverage_error_category=coverage_error_category,
                    potential_omissions=window_omissions,
                ),
            )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTION_WINDOWS)
    outcomes = await asyncio.gather(
        *(process_window(index, window, semaphore) for index, window in enumerate(windows, start=1))
    )
    candidates = [candidate for outcome in outcomes for candidate in outcome.candidates]
    llm_calls = [call for outcome in outcomes for call in outcome.calls]
    window_results = [outcome.result for outcome in outcomes]
    # AsyncSession-backed callbacks are not safe to invoke concurrently. Persist
    # model-call audit rows in deterministic window/call order after inference.
    for call in llm_calls:
        await log_call(call)

    if enable_obligation_coverage_audit:
        image_fallback_window_indexes = {
            index
            for index, result in enumerate(window_results)
            if result.coverage_status == "invalid"
            and result.coverage_error_category == "source_quote_not_found"
        }
        page_to_windows: dict[int, list[int]] = {}
        for index, window in enumerate(windows):
            if not window.ocr_warning and index not in image_fallback_window_indexes:
                continue
            for source in window.sources:
                if source.page_number is not None:
                    page_to_windows.setdefault(source.page_number, []).append(index)

        page_results: dict[int, tuple[str, list[dict[str, Any]], str | None]] = {}
        for page_number in sorted(page_to_windows):
            page_text = (coverage_page_texts or {}).get(page_number, "")
            emitted_page_quotes = [
                record.raw_source
                for record in candidates
                if record.is_valid
                and page_text
                and quote_is_present_in_source(page_text, record.raw_source)
                and any(
                    isinstance(source, dict) and source.get("page_number") == page_number
                    for source in record.sources_json
                )
            ]
            audit = await audit_page_image_coverage(
                page_number,
                (coverage_page_images or {}).get(page_number),
                emitted_page_quotes,
                llm,
            )
            await log_call(audit.call)
            llm_calls.append(audit.call)
            page_bboxes = dict(audit.potential_omission_bboxes)
            page_findings = [
                {
                    "page_number": page_number,
                    "source_quote": quote,
                    **({"bbox": page_bboxes[quote]} if quote in page_bboxes else {}),
                }
                for quote in audit.potential_omissions
            ]
            page_results[page_number] = (
                audit.status,
                page_findings,
                audit.call.error_category,
            )

        for index, window in enumerate(windows):
            if not window.ocr_warning and index not in image_fallback_window_indexes:
                continue
            pages = sorted(
                {source.page_number for source in window.sources if source.page_number is not None}
            )
            results = [page_results[page] for page in pages if page in page_results]
            statuses = [status for status, _findings, _category in results]
            status = (
                "completed"
                if statuses and all(item == "completed" for item in statuses)
                else next(
                    (item for item in ("failed", "invalid", "uncertain") if item in statuses),
                    "failed",
                )
            )
            findings = [
                finding
                for _page_status, page_findings, _category in results
                for finding in page_findings
            ]
            error_category = next(
                (category for _status, _findings, category in results if category),
                None,
            )
            if error_category is None and status != "completed":
                error_category = window_results[index].coverage_error_category
            window_results[index] = replace(
                window_results[index],
                coverage_status=status,
                coverage_error_category=error_category,
                potential_omissions=findings,
            )

    return ExtractionOutcome(
        candidates=candidates,
        llm_calls=llm_calls,
        window_results=window_results,
    )


__all__ = [
    "CandidateRecord",
    "ExtractionOutcome",
    "WindowExtractionResult",
    "extract_from_windows",
]
