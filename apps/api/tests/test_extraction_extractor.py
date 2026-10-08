"""Tests for the CP28 extraction orchestrator (extract_from_windows).

Pure-logic tests: a :class:`FakeLlmAdapter` (or a tiny failing subclass)
drives the orchestrator, so no LLM API key or network is required.  The
DB-layer path (candidate persistence, retry) is covered in
``test_extraction_pipeline.py`` (CP26 style).

Async tests use the project's ``asyncio.run(_run())`` pattern (no
pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, TypeAdapter

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallError,
    LlmCallResult,
)
from tender_compliance_api.extraction.chunking import SourceWindow, build_source_windows
from tender_compliance_api.extraction.extractor import (
    CandidateRecord,
    ExtractionOutcome,
    extract_from_windows,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.prompts import ExtractionResponse
from tender_compliance_api.extraction.schema import (
    RequirementCandidate,
    RequirementType,
    TrustedSourceContext,
    UncertaintyLevel,
)
from tender_compliance_api.extraction.verbatim_validation import (
    VerbatimValidationResponse,
)

ORG_ID = uuid.uuid4()
DOC_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()


def _page(
    cleaned: str,
    page_number: int = 1,
    ocr_needed: bool = False,
    error: str | None = None,
) -> DocumentPage:
    """Build a persisted-shaped DocumentPage without hitting the DB."""

    meta: dict[str, Any] | None = {"error": error} if error else None
    return DocumentPage(
        id=uuid.uuid4(),
        document_version_id=VERSION_ID,
        page_number=page_number,
        extracted_text=None,
        cleaned_text=cleaned,
        ocr_needed=ocr_needed,
        ocr_confidence=None,
        rendered_image_object_key=None,
        structural_metadata=meta,
        created_at=datetime.now(UTC),
    )


def _window(
    page: DocumentPage,
    text: str,
    chunk_id: str = "c1",
    ocr_warning: bool = False,
) -> SourceWindow:
    src = TrustedSourceContext.from_page(page, ORG_ID, DOC_ID)
    return SourceWindow(
        chunk_id=chunk_id,
        text=text,
        sources=(src,),
        overlap=None,
        hierarchy=(),
        table_context=(),
        ocr_warning=ocr_warning,
    )


def _cand(
    normalized: str,
    raw_source: str,
    ut: RequirementType = RequirementType.OBLIGATION,
    unc: UncertaintyLevel = UncertaintyLevel.CONFIRMED,
    clause: str | None = None,
    group: str | None = None,
) -> RequirementCandidate:
    return RequirementCandidate(
        normalized_text=normalized,
        raw_source=raw_source,
        requirement_type=ut,
        uncertainty=unc,
        clause_section=clause,
        group_hint=group,
    )


def _response(candidates: list[RequirementCandidate]) -> ExtractionResponse:
    return ExtractionResponse(candidates=candidates)


def _make_log() -> tuple[list[LlmCallResult], Any]:
    """Return ``(calls, log_call)`` where ``log_call`` records every LLM result."""

    calls: list[LlmCallResult] = []

    async def log_call(call: LlmCallResult) -> None:
        calls.append(call)

    return calls, log_call


# ---------------------------------------------------------------------------
# 1. The happy path: a confirmed candidate that matches the window text.
# ---------------------------------------------------------------------------

def test_confirmed_candidate_validated_and_persistable() -> None:
    async def _run() -> None:
        text = (
            "The system shall encrypt all data at rest using AES-256."
        )
        page = _page(text)
        window = _window(page, text)
        cand = _cand(
            "The system shall encrypt data at rest using AES-256.",
            raw_source="The system shall encrypt all data at rest using AES-256.",
        )
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        assert len(outcome.candidates) == 1
        rec = outcome.candidates[0]
        assert rec.is_valid is True
        assert rec.persistable is True
        assert rec.uncertainty == UncertaintyLevel.CONFIRMED.value
        assert rec.ocr_warning is False
        assert rec.requirement_type == RequirementType.OBLIGATION.value
        assert rec.chunk_id == window.chunk_id
        assert len(calls) == 1
        assert calls[0].status == "completed"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. A candidate that cites text absent from the window is rejected.
# ---------------------------------------------------------------------------

def test_candidate_with_no_citation_is_invalid_not_persistable() -> None:
    async def _run() -> None:
        window_text = "Some unrelated page content."
        page = _page(window_text)
        window = _window(page, window_text)
        # raw_source deliberately NOT a substring of window_text
        cand = _cand(
            normalized="The system shall encrypt data at rest using AES-256.",
            raw_source="The system shall encrypt data at rest using AES-256.",
        )
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows(
            [window], llm, log_call=log_call
        )

        rec = outcome.candidates[0]
        assert rec.is_valid is False
        assert rec.persistable is False
        assert rec.rejection_reason is not None
        assert "not present in the trusted source text" in rec.rejection_reason
        # still recorded for audit → invented-requirement rate is measurable
        assert len(calls) == 1

    asyncio.run(_run())


def test_verbatim_fallback_recovers_only_exact_guarded_quote() -> None:
    async def _run() -> None:
        source = "The pump must deliver at least 5 L/\nmin at 2 bar."
        candidate = _cand(
            "The pump must deliver at least 5 L/min at 2 bar.",
            "The pump must deliver at least 5 L/min at 2 bar.",
        )
        fallback = VerbatimValidationResponse(
            verdict="supported",
            confidence=0.99,
            matched_source=source,
            reason="Line wrapping only.",
        )
        llm = FakeLlmAdapter(responses=[_response([candidate]), fallback])
        calls, log_call = _make_log()
        outcome = await extract_from_windows(
            [_window(_page(source), source)],
            llm,
            log_call=log_call,
            enable_verbatim_fallback=True,
        )
        record = outcome.candidates[0]
        assert record.is_valid is True
        assert record.persistable is True
        assert record.raw_source == source
        assert record.normalized_text == candidate.normalized_text
        assert record.uncertainty == UncertaintyLevel.UNCERTAIN.value
        assert record.verbatim_validation["status"] == "recovered_for_human_review"
        assert len(calls) == 2
        assert calls[1].call_site == "validate_verbatim_source"

        changed_unit = "The pump must deliver at least 5 L/s at 2 bar."
        wrong_unit = VerbatimValidationResponse(
            verdict="supported",
            confidence=0.99,
            matched_source=changed_unit,
            reason="Close wording.",
        )
        llm2 = FakeLlmAdapter(responses=[_response([candidate]), wrong_unit])
        _, log_call2 = _make_log()
        result2 = await extract_from_windows(
            [_window(_page(changed_unit), changed_unit)],
            llm2,
            log_call=log_call2,
            enable_verbatim_fallback=True,
        )
        assert result2.candidates[0].is_valid is False

        changed_concept = "The sensor accuracy shall be within 0.5 percent."
        concept_candidate = _cand(
            "The sensor resolution shall be within 0.5 percent.",
            "The sensor resolution shall be within 0.5 percent.",
        )
        model_support = VerbatimValidationResponse(
            verdict="supported",
            confidence=0.99,
            matched_source=changed_concept,
            reason="Close wording.",
        )
        llm3 = FakeLlmAdapter(responses=[_response([concept_candidate]), model_support])
        _, log_call3 = _make_log()
        result3 = await extract_from_windows(
            [_window(_page(changed_concept), changed_concept)],
            llm3,
            log_call=log_call3,
            enable_verbatim_fallback=True,
        )
        assert result3.candidates[0].is_valid is False

        entity_source = "The Contoso pump must deliver 5 L/min at 2 bar."
        entity_candidate = _cand(
            "The Acme pump must deliver 5 L/min at 2 bar.",
            "The Acme pump must deliver 5 L/min at 2 bar.",
        )
        entity_support = VerbatimValidationResponse(
            verdict="supported",
            confidence=0.99,
            matched_source=entity_source,
            reason="Close wording.",
        )
        llm4 = FakeLlmAdapter(responses=[_response([entity_candidate]), entity_support])
        _, log_call4 = _make_log()
        result4 = await extract_from_windows(
            [_window(_page(entity_source), entity_source)],
            llm4,
            log_call=log_call4,
            enable_verbatim_fallback=True,
        )
        assert result4.candidates[0].is_valid is False

        many = [_cand(candidate.normalized_text, candidate.raw_source) for _ in range(4)]
        limited_llm = FakeLlmAdapter(
            responses=[_response(many), fallback, fallback, fallback]
        )
        _, limited_log = _make_log()
        limited = await extract_from_windows(
            [_window(_page(source), source)],
            limited_llm,
            log_call=limited_log,
            enable_verbatim_fallback=True,
        )
        assert len(limited_llm.calls) == 4  # one extraction + three bounded fallbacks
        assert all(candidate.persistable for candidate in limited.candidates[:3])
        assert limited.candidates[3].is_valid is False
        assert limited.candidates[3].verbatim_validation["status"] == (
            "fallback_budget_exhausted"
        )

    asyncio.run(_run())


def test_verbatim_fallback_rejects_malformed_and_does_not_run_after_match() -> None:
    for payload in (
        {
            "verdict": "supported",
            "confidence": "0.99",
            "matched_source": "quote",
            "reason": "ok",
        },
        {
            "verdict": "supported",
            "confidence": 0.99,
            "matched_source": "quote",
            "reason": "ok",
            "page_number": 2,
        },
    ):
        try:
            VerbatimValidationResponse.model_validate(payload)
        except Exception:
            continue
        raise AssertionError("strict fallback schema accepted malformed output")

    async def _run() -> None:
        text = "The pump must deliver at least 5 L/min at 2 bar."
        candidate = _cand("The pump must deliver 5 L/min.", text)
        llm = FakeLlmAdapter(responses=[_response([candidate])])
        _, log_call = _make_log()
        outcome = await extract_from_windows(
            [_window(_page(text), text)],
            llm,
            log_call=log_call,
            enable_verbatim_fallback=True,
        )
        assert outcome.candidates[0].is_valid is True
        assert len(llm.calls) == 1

    asyncio.run(_run())


def test_verbatim_fallback_skips_multisource_windows() -> None:
    async def _run() -> None:
        text = "The unit shall operate below 30 dB(A)."
        window = SourceWindow(
            chunk_id="multi",
            text=text,
            sources=(
                TrustedSourceContext.from_page(_page(text, 1), ORG_ID, DOC_ID),
                TrustedSourceContext.from_page(_page(text, 2), ORG_ID, DOC_ID),
            ),
            ocr_warning=False,
        )
        candidate = _cand("The unit shall operate below 30 dB(A).", "missing")
        llm = FakeLlmAdapter(
            responses=[
                _response([candidate]),
                VerbatimValidationResponse(
                    verdict="supported",
                    confidence=0.99,
                    matched_source=text,
                    reason="Selected.",
                ),
            ]
        )
        _, log_call = _make_log()
        outcome = await extract_from_windows(
            [window], llm, log_call=log_call, enable_verbatim_fallback=True
        )
        assert outcome.candidates[0].is_valid is False
        assert len(llm.calls) == 1

    asyncio.run(_run())


def test_verbatim_fallback_provider_failure_preserves_original_rejection() -> None:
    class FailedFallbackLlm(FakeLlmAdapter):
        async def extract(
            self,
            *,
            system_prompt: str,
            user_text: str,
            response_model: type[BaseModel],
            config: LlmCallConfig,
        ) -> ExtractResult:
            result = await super().extract(
                system_prompt=system_prompt,
                user_text=user_text,
                response_model=response_model,
                config=config,
            )
            if response_model is VerbatimValidationResponse:
                return ExtractResult(
                    response=result.response,
                    call=replace(result.call, status="failed"),
                )
            return result

    class RaisingFallbackLlm(FakeLlmAdapter):
        async def extract(
            self,
            *,
            system_prompt: str,
            user_text: str,
            response_model: type[BaseModel],
            config: LlmCallConfig,
        ) -> ExtractResult:
            if response_model is VerbatimValidationResponse:
                raise LlmCallError("synthetic provider timeout")
            return await super().extract(
                system_prompt=system_prompt,
                user_text=user_text,
                response_model=response_model,
                config=config,
            )

    async def _run() -> None:
        source = "The enclosure shall be IP67 rated."
        candidate = _cand("The enclosure shall be IP67 rated.", "fabricated quote")
        llm = FailedFallbackLlm(
            responses=[
                _response([candidate]),
                VerbatimValidationResponse(
                    verdict="supported",
                    confidence=0.99,
                    matched_source=source,
                    reason="Model result must be ignored after provider failure.",
                ),
            ]
        )
        calls, log_call = _make_log()
        outcome = await extract_from_windows(
            [_window(_page(source), source)],
            llm,
            log_call=log_call,
            enable_verbatim_fallback=True,
        )
        record = outcome.candidates[0]
        assert record.is_valid is False
        assert record.persistable is False
        assert record.verbatim_validation["status"] == "provider_failure"
        assert [call.status for call in calls] == ["completed", "failed"]

        timeout_llm = RaisingFallbackLlm(responses=[_response([candidate])])
        timeout_calls, timeout_log = _make_log()
        timeout_outcome = await extract_from_windows(
            [_window(_page(source), source)],
            timeout_llm,
            log_call=timeout_log,
            enable_verbatim_fallback=True,
        )
        assert timeout_outcome.candidates[0].is_valid is False
        assert timeout_outcome.candidates[0].verbatim_validation["status"] == (
            "provider_failure"
        )
        assert [call.status for call in timeout_calls] == ["completed", "failed"]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. OCR/structure uncertainty elevates CONFIRMED -> UNCERTAIN.
# ---------------------------------------------------------------------------

def test_ocr_warning_elevates_confirmed_to_uncertain() -> None:
    async def _run() -> None:
        text = (
            "The system shall operate below 30 dB(A) between 06:00 and 22:00."
        )
        page = _page(text, ocr_needed=True)
        window = _window(page, text, ocr_warning=True)
        cand = _cand(
            "The system shall operate below 30 dB(A).",
            raw_source=text,  # matches window text -> citation valid
        )
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        rec = outcome.candidates[0]
        assert rec.ocr_warning is True
        assert rec.uncertainty == UncertaintyLevel.UNCERTAIN.value
        # cannot be persisted as a confirmed requirement while uncertain
        assert rec.persistable is False
        assert rec.is_valid is True  # citation still valid

    asyncio.run(_run())


def test_structural_error_page_also_elevates_uncertainty() -> None:
    text = "The casing must be IP67 rated for dust ingress protection."
    page = _page(text, error="malformed table")
    # build_source_windows computes ocr_warning from ocr_needed OR structural
    # error — verify end-to-end through the real chunker:
    windows = build_source_windows(
        [page], organization_id=ORG_ID, document_id=DOC_ID
    )
    assert windows[0].ocr_warning is True

    async def _run() -> None:
        cand = _cand("IP67 casing.", raw_source=text)
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows(windows, llm, log_call=log_call)

        assert outcome.candidates[0].uncertainty == UncertaintyLevel.UNCERTAIN.value
        assert outcome.candidates[0].persistable is False

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. ABSTAIN is kept (audit) but never persists.
# ---------------------------------------------------------------------------

def test_abstain_candidate_is_kept_not_persistable() -> None:
    async def _run() -> None:
        text = "The unit shall weigh less than 2 kg."
        page = _page(text)
        window = _window(page, text)
        cand = _cand(
            "Weight requirement.",
            raw_source="The unit shall weigh less than 2 kg.",
            unc=UncertaintyLevel.ABSTAIN,
        )
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        rec = outcome.candidates[0]
        assert rec.uncertainty == UncertaintyLevel.ABSTAIN.value
        assert rec.persistable is False
        # is_valid reflects the citation substring check (raw_source IS in window)
        assert rec.is_valid is True

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Multiple windows -> one audited LLM call per window, all collected.
# ---------------------------------------------------------------------------

def test_multiple_windows_each_get_one_llm_call() -> None:
    async def _run() -> None:
        t1 = "Requirement 1: operating temperature -20 to +60 °C."
        t2 = "Requirement 2: storage humidity 5 % to 95 % RH."
        # Two explicit, independent windows (distinct chunk_ids) so each is
        # processed by its own LLM call regardless of merged-page sizing.
        w1 = _window(_page(t1, page_number=1), t1, chunk_id="c1")
        w2 = _window(_page(t2, page_number=2), t2, chunk_id="c2")

        c1 = _cand("Temp range.", raw_source=t1)
        c2 = _cand("Humidity range.", raw_source=t2)
        llm = FakeLlmAdapter(responses=[_response([c1]), _response([c2])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([w1, w2], llm, log_call=log_call)

        assert len(outcome.candidates) == 2
        assert len(calls) == 2
        assert all(c.status == "completed" for c in calls)
        texts = {c.normalized_text for c in outcome.candidates}
        assert {"Temp range.", "Humidity range."} == texts

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. Empty windows -> no LLM calls, no candidates, no exceptions.
# ---------------------------------------------------------------------------

def test_empty_windows_is_noop() -> None:
    async def _run() -> None:
        llm = FakeLlmAdapter()
        calls, log_call = _make_log()

        outcome = await extract_from_windows([], llm, log_call=log_call)

        assert outcome.candidates == []
        assert outcome.llm_calls == []
        assert calls == []

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. A per-window LLM failure is audited and skipped; other windows survive.
# ---------------------------------------------------------------------------

class _FailingOnceLlm(LlmAdapter):
    """First call raises LlmCallError; subsequent calls return an empty response."""

    def __init__(self) -> None:
        self._calls = 0

    @property
    def provider(self) -> str:
        return "fake-fail"

    @property
    def model(self) -> str:
        return "fake-fail"

    async def extract(  # type: ignore[override]
        self,
        *,
        system_prompt: str,
        user_text: str,
        response_model: type[Any],
        config: LlmCallConfig,
    ) -> ExtractResult:
        self._calls += 1
        if self._calls == 1:
            raise LlmCallError("inject: provider boom")
        ta = TypeAdapter(response_model)
        data = ta.validate_python({"candidates": []})
        return ExtractResult(
            response=data,
            call=LlmCallResult(
                provider=config.provider,
                model=config.model,
                prompt_version=config.prompt_version,
                schema_version=config.schema_version,
                latency_ms=1,
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                cost_usd=None,
                finish_reason="stop",
                status="completed",
                error_message=None,
                call_site=config.call_site,
            ),
        )


def test_llm_failure_is_audited_and_skipped() -> None:
    async def _run() -> None:
        t1 = "First requirement that will fail extraction."
        t2 = "Second requirement that will succeed."
        # Two explicit independent windows so each gets its own (ordered) call.
        w1 = _window(_page(t1, page_number=1), t1, chunk_id="c1")
        w2 = _window(_page(t2, page_number=2), t2, chunk_id="c2")
        llm = _FailingOnceLlm()
        calls, log_call = _make_log()

        outcome = await extract_from_windows([w1, w2], llm, log_call=log_call)

        # both the failed call and the successful call are audited
        statuses = sorted(c.status for c in calls)
        assert statuses == ["completed", "failed"]
        # the failed window produced no candidates; the success window had none
        assert outcome.candidates == []

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. Overlap is included in the user payload so context crosses boundaries.
# ---------------------------------------------------------------------------

def test_user_payload_includes_overlap() -> None:
    async def _run() -> None:
        text = "The voltage shall not exceed 230 V."
        page = _page(text)
        src = TrustedSourceContext.from_page(page, ORG_ID, DOC_ID)
        window = SourceWindow(
            chunk_id="c1",
            text=text,
            sources=(src,),
            overlap="previous window tail context",
            hierarchy=(),
            table_context=(),
            ocr_warning=False,
        )
        cand = _cand("Volt limit.", raw_source=text)
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        assert outcome.candidates[0].raw_source == text

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. CandidateRecord is JSON-serializable (sources_json must be JSON-safe).
# ---------------------------------------------------------------------------

def test_record_is_json_serializable() -> None:
    async def _run() -> None:
        text = "The cable shall be rated 10 A."
        page = _page(text)
        window = _window(page, text)
        cand = _cand("Cable amp rating.", raw_source=text)
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        rec = outcome.candidates[0]
        serializable = {
            "chunk_id": rec.chunk_id,
            "sources_json": rec.sources_json,
            "window_text": rec.window_text,
            "normalized_text": rec.normalized_text,
            "raw_source": rec.raw_source,
            "requirement_type": rec.requirement_type,
            "uncertainty": rec.uncertainty,
            "clause_number": rec.clause_number,
            "group_hint": rec.group_hint,
            "ocr_warning": rec.ocr_warning,
            "is_valid": rec.is_valid,
            "persistable": rec.persistable,
            "rejection_reason": rec.rejection_reason,
        }
        json.dumps(serializable)  # must not raise
        # the trusted source inside sources_json carries its uuids as strings
        assert isinstance(rec.sources_json, list)
        src = rec.sources_json[0]
        assert isinstance(src["document_id"], str)
        assert isinstance(src["document_version_id"], str)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 10. Provider/model are echoed from the adapter onto every audit row.
# ---------------------------------------------------------------------------

def test_provider_model_echoed_on_audit_rows() -> None:
    async def _run() -> None:
        text = "The enclosure shall withstand an impact of 1 J."
        page = _page(text)
        window = _window(page, text)
        cand = _cand("Impact rating.", raw_source=text)
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        await extract_from_windows([window], llm, log_call=log_call)

        assert calls[0].provider == "fake"
        assert calls[0].model == "fake"
        assert calls[0].call_site == "extract_candidates"

    asyncio.run(_run())


def test_outcome_type_and_fields() -> None:
    async def _run() -> None:
        text = "The relay shall switch 10 A at 250 V AC."
        page = _page(text)
        window = _window(page, text)
        cand = _cand(
            "Relay switching.", raw_source=text, clause="1.2", group="power"
        )
        llm = FakeLlmAdapter(responses=[_response([cand])])
        calls, log_call = _make_log()

        outcome = await extract_from_windows([window], llm, log_call=log_call)

        assert isinstance(outcome, ExtractionOutcome)
        assert isinstance(outcome.candidates, list)
        assert isinstance(outcome.candidates[0], CandidateRecord)
        assert outcome.candidates[0].clause_number == "1.2"
        assert outcome.candidates[0].group_hint == "power"

    asyncio.run(_run())
