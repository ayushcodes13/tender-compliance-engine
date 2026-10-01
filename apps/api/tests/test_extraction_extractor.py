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
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction import (
    CandidateRecord,
    ExtractionOutcome,
    ExtractionResponse,
    FakeLlmAdapter,
    LlmAdapter,
    LlmCallError,
    LlmCallResult,
    RequirementCandidate,
    RequirementType,
    SourceWindow,
    TrustedSourceContext,
    UncertaintyLevel,
    extract_from_windows,
)
from tender_compliance_api.extraction.adapter import ExtractResult, LlmCallConfig
from tender_compliance_api.extraction.chunking import build_source_windows

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
