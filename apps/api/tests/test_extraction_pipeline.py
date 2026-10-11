"""Tests for CP26: LLM extraction adapter port, fake, prompt versioning, and
run-metadata persistence.

Covers:
- The :class:`LlmAdapter` port is provider-agnostic (a FakeLlmAdapter and the
  OpenAiLlmAdapter both construct without touching the model/document layer).
- :class:`FakeLlmAdapter` drives extraction deterministically with no network.
- Prompt/schema versions are recorded and constant.
- :meth:`DocumentService.log_llm_call` persists provider/model/prompt+schema
  version (and never fabricates cost/token counts).
- The real OpenAI call is opt-in (skipped by default to avoid surprise cost).
"""

from __future__ import annotations

import asyncio
import os
import struct
import uuid

import pytest
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    ExtractionCandidate,
    ExtractionDiagnostics,
    ExtractionReconciliation,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionWindowAudit,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    RunStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.document.service import (
    DocumentService,
)
from tender_compliance_api.export.visual_validation import (
    PageImageBatchResponse,
    PageImageQuoteDecision,
)
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallError,
    LlmCallResult,
)
from tender_compliance_api.extraction.chunking import (
    SourceWindow,
    build_literal_source_window,
    build_source_windows,
)
from tender_compliance_api.extraction.coverage_audit import (
    ImageCoverageQuote,
    ImageObligationCoverageResponse,
)
from tender_compliance_api.extraction.extractor import (
    CandidateRecord,
    ExtractionOutcome,
    WindowExtractionResult,
    _to_record,
    extract_from_windows,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter
from tender_compliance_api.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionResponse,
    system_prompt_for_source_window,
)
from tender_compliance_api.extraction.requirement import promotion_key
from tender_compliance_api.extraction.schema import (
    RequirementCandidate,
    RequirementType,
    TrustedSourceContext,
    UncertaintyLevel,
)
from tender_compliance_api.extraction.technical_scope import SourceTextRange
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import (
    JobProcessor,
    _boundary_continuation_ranges,
    _merge_blank_serial_table_rows,
    _sample_heading_ranges,
    _standalone_numbered_heading_ranges,
    _subtract_source_range,
    _table_cell_source_windows,
    _technical_preamble_ranges,
    _technical_schedule_leadin_ranges,
    _technical_section_title_ranges,
)


def test_boundary_continuation_keeps_one_lettered_row_across_pages() -> None:
    previous_text = (
        "j) Warranty: Vendor to provide comprehensive three-year warranty on the "
        "complete system and utilities. Expenses are borne by vendor for the\n"
    )
    next_text = (
        "replacement/repair of faulty items. It starts on acceptance.\n\n"
        "k) Vendor must provide a service network.\n"
    )
    version_id = uuid.uuid4()
    previous_page = DocumentPage(
        document_version_id=version_id,
        page_number=12,
        extracted_text=previous_text,
        cleaned_text=previous_text,
        ocr_needed=0,
    )
    next_page = DocumentPage(
        document_version_id=version_id,
        page_number=13,
        extracted_text=next_text,
        cleaned_text=next_text,
        ocr_needed=0,
    )

    spans = _boundary_continuation_ranges(
        previous_page,
        next_page,
        (SourceTextRange(0, len(previous_text)),),
        (SourceTextRange(0, len(next_text)),),
    )

    assert spans is not None
    previous_span, next_span = spans
    assert previous_text[previous_span.start : previous_span.end].startswith("j) Warranty:")
    assert next_text[next_span.start : next_span.end].startswith("replacement/repair")
    assert "k) Vendor" not in next_text[next_span.start : next_span.end]

    windows = build_source_windows(
        [previous_page, next_page],
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        max_chars=5000,
        overlap_chars=0,
        included_ranges_by_page={
            12: (previous_span,),
            13: (next_span,),
        },
    )
    assert len(windows) == 1
    assert len(windows[0].sources) == 2
    assert "for the\nreplacement/repair" in windows[0].text


def test_standalone_numbered_section_labels_are_literal_rows() -> None:
    text = (
        "1. Growth chamber\n"
        "2.1 Buffer Chamber pumping system:\n"
        "7. Computer package and relevant software shall provide full logging.\n"
        "10. Sources/Manufactures\n"
    )
    included = (SourceTextRange(0, len(text)),)
    rows = _standalone_numbered_heading_ranges(text, included)
    assert [text[row.start : row.end] for row in rows] == [
        "1. Growth chamber",
        "2.1 Buffer Chamber pumping system:",
        "10. Sources/Manufactures",
    ]


def test_technical_sample_lead_in_is_excluded_from_sheet_windows() -> None:
    text = (
        "Item details and technical specifications as mentioned below: Supply,\n"
        "Installation and Commissioning of Geosynthetic Universal Testing Machine.\n"
    )
    rows = _technical_preamble_ranges(text, (SourceTextRange(0, len(text)),))
    assert len(rows) == 1
    assert text[rows[0].start : rows[0].end].startswith("Item details")


def test_technical_section_title_is_not_a_requirement_window() -> None:
    text = "SECTION V / Technical Specification\n"
    rows = _technical_section_title_ranges(
        text, (SourceTextRange(0, len(text)),)
    )
    assert [text[item.start : item.end] for item in rows] == [
        "SECTION V / Technical Specification"
    ]


def test_response_table_leadin_excludes_only_instructions_and_equipment_title() -> None:
    text = (
        "अनुभाग-5 / SECTION- V\n"
        "तकनीकी विशिष्टता / Technical Specification\n"
        "(Bidder should submit compliance matrix along with Technical Bid)\n"
        "Item details and technical specifications as mentioned below: Supply,\n"
        "Installation and Commissioning of Geosynthetic Universal Testing Machine.\n"
        "S.no | Technical Specification | Qty | Compliance (Yes/No) | Any Deviation\n"
        "1 | Universal Testing Machine (300 kN) with 300 kN capacity. | 01 | |\n"
    )
    ranges = _technical_schedule_leadin_ranges(
        text, (SourceTextRange(0, len(text)),)
    )
    assert [text[item.start : item.end] for item in ranges] == [
        "(Bidder should submit compliance matrix along with Technical Bid)",
        "Item details and technical specifications as mentioned below: Supply,",
        "Installation and Commissioning of Geosynthetic Universal Testing Machine.",
    ]


def test_sample_heading_row_is_separated_from_nonrow_section_label() -> None:
    text = "Other important requirements:\nOptional Items\n"
    row_headings, section_labels = _sample_heading_ranges(
        text, (SourceTextRange(0, len(text)),)
    )
    assert [text[item.start : item.end] for item in row_headings] == [
        "Other important requirements:"
    ]
    assert [text[item.start : item.end] for item in section_labels] == [
        "Optional Items"
    ]


def test_table_rows_extract_only_the_technical_specification_cells() -> None:
    text = (
        "S.no | Technical Specification | Qty | Compliance (Yes/No) | Any Deviation\n"
        "1 | Universal Testing Machine (300 kN) with 300 kN capacity. | 01 | |\n"
    )
    page = DocumentPage(
        document_version_id=uuid.uuid4(),
        page_number=17,
        extracted_text=text,
        cleaned_text=text,
        ocr_needed=0,
        ocr_confidence=None,
    )
    windows, excluded, schema = _table_cell_source_windows(
        page,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        included_ranges=(SourceTextRange(0, len(text)),),
        schema=None,
    )
    assert schema == (1,)
    assert len(windows) == 1
    assert windows[0].text == "Universal Testing Machine (300 kN) with 300 kN capacity."
    source = windows[0].sources[0]
    assert text[source.char_start : source.char_end] == windows[0].text
    assert source.source_text == windows[0].text
    assert windows[0].literal_source_row is True
    assert excluded == (
        SourceTextRange(0, text.index("1 |")),
        SourceTextRange(text.index("1 |"), len(text)),
    )


def test_blank_serial_specification_rows_continue_prior_row_across_pages() -> None:
    version_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    document_id = uuid.uuid4()
    first_page_text = (
        "S.no | Technical Specification | Qty | Compliance (Yes/No) | Any Deviation\n"
        "1 | Main machine requirement. | 01 | |\n"
    )
    continuation_text = (
        " | Keyboard entry and power supply requirements. | | |\n"
        " | Accessories and attachments. | | |\n"
        "2 | Second machine requirement. | 01 | |\n"
    )
    first_page = DocumentPage(
        document_version_id=version_id,
        page_number=17,
        extracted_text=first_page_text,
        cleaned_text=first_page_text,
        ocr_needed=0,
    )
    continuation_page = DocumentPage(
        document_version_id=version_id,
        page_number=18,
        extracted_text=continuation_text,
        cleaned_text=continuation_text,
        ocr_needed=0,
    )
    first_windows, _, schema = _table_cell_source_windows(
        first_page,
        organization_id=organization_id,
        document_id=document_id,
        included_ranges=(SourceTextRange(0, len(first_page_text)),),
        schema=None,
    )
    continuation_windows, _, _ = _table_cell_source_windows(
        continuation_page,
        organization_id=organization_id,
        document_id=document_id,
        included_ranges=(SourceTextRange(0, len(continuation_text)),),
        schema=schema,
    )

    merged = _merge_blank_serial_table_rows(first_windows + continuation_windows)

    assert [window.text for window in merged] == [
        "Main machine requirement.\nKeyboard entry and power supply requirements.\n"
        "Accessories and attachments.",
        "Second machine requirement.",
    ]
    assert [source.page_number for source in merged[0].sources] == [17, 18, 18]
    for window in merged:
        for source in window.sources:
            assert (
                window.text[source.window_char_start : source.window_char_end]
                == source.page_source_text[
                    source.char_start - source.page_source_char_start :
                    source.char_end - source.page_source_char_start
                ]
            )


def test_unlabelled_continuation_between_serial_rows_stays_with_prior_row() -> None:
    organization_id, document_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first_page_text = "S.no | Technical Specification | Qty\n1 | Main machine requirement. | 01\n"
    continuation_text = (
        "Keyboard entry of stiffness correction factor.\n"
        "Accessories and Attachments: Wide Frame Option.\n"
        "S.no | Technical Specification | Qty\n2 | Grips and fixtures. | 01\n"
    )
    first_page = DocumentPage(
        document_version_id=version_id,
        page_number=17,
        extracted_text=first_page_text,
        cleaned_text=first_page_text,
        ocr_needed=0,
    )
    continuation_page = DocumentPage(
        document_version_id=version_id,
        page_number=18,
        extracted_text=continuation_text,
        cleaned_text=continuation_text,
        ocr_needed=0,
    )
    first_windows, _, schema = _table_cell_source_windows(
        first_page,
        organization_id=organization_id,
        document_id=document_id,
        included_ranges=(SourceTextRange(0, len(first_page_text)),),
        schema=None,
    )
    continuation_windows, _, _ = _table_cell_source_windows(
        continuation_page,
        organization_id=organization_id,
        document_id=document_id,
        included_ranges=(SourceTextRange(0, len(continuation_text)),),
        schema=schema,
    )
    plain_continuation = continuation_text.split("S.no")[0].rstrip()
    plain_window = build_literal_source_window(
        continuation_page,
        organization_id=organization_id,
        document_id=document_id,
        char_start=0,
        char_end=len(plain_continuation),
    )

    merged = _merge_blank_serial_table_rows(
        first_windows + [plain_window] + continuation_windows
    )

    assert [window.text for window in merged] == [
        "Main machine requirement.\nKeyboard entry of stiffness correction factor.\n"
        "Accessories and Attachments: Wide Frame Option.",
        "Grips and fixtures.",
    ]
    assert [source.page_number for source in merged[0].sources] == [17, 18]
    record = _to_record(
        merged[0],
        RequirementCandidate(
            normalized_text=merged[0].text,
            raw_source=merged[0].text,
            requirement_type=RequirementType.OBLIGATION,
            uncertainty=UncertaintyLevel.CONFIRMED,
        ),
    )
    assert record.is_valid is True
    assert record.persistable is True
    for window in merged:
        for source in window.sources:
            assert (
                window.text[source.window_char_start : source.window_char_end]
                == source.page_source_text[
                    source.char_start - source.page_source_char_start :
                    source.char_end - source.page_source_char_start
                ]
            )


def test_parameter_tables_keep_the_name_and_required_specification() -> None:
    text = (
        "Parameter | Required Specification | Compliance (Yes / No) | Any remarks\n"
        "Main Instrument | Precision manual diamond scriber. | |\n"
    )
    page = DocumentPage(
        document_version_id=uuid.uuid4(),
        page_number=1,
        extracted_text=text,
        cleaned_text=text,
        ocr_needed=0,
        ocr_confidence=None,
    )
    windows, _, schema = _table_cell_source_windows(
        page,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        included_ranges=(SourceTextRange(0, len(text)),),
        schema=None,
    )
    assert schema == (0, 1)
    assert len(windows) == 1
    assert windows[0].text == "Main Instrument | Precision manual diamond scriber."
    source = windows[0].sources[0]
    assert text[source.char_start : source.char_end] == windows[0].text


def test_boundary_continuation_does_not_join_two_labeled_rows() -> None:
    previous_text = "a) First requirement ends with the\n"
    next_text = "b) Second requirement starts here.\n"
    version_id = uuid.uuid4()
    previous_page = DocumentPage(
        document_version_id=version_id,
        page_number=1,
        extracted_text=previous_text,
        cleaned_text=previous_text,
        ocr_needed=0,
    )
    next_page = DocumentPage(
        document_version_id=version_id,
        page_number=2,
        extracted_text=next_text,
        cleaned_text=next_text,
        ocr_needed=0,
    )

    assert _boundary_continuation_ranges(
        previous_page,
        next_page,
        (SourceTextRange(0, len(previous_text)),),
        (SourceTextRange(0, len(next_text)),),
    ) is None


def test_boundary_continuation_joins_unlabeled_new_sentence() -> None:
    previous_text = (
        "m) In-situ characterization facility includes the RHEED system.\n"
    )
    next_text = (
        "The RHEED analysis software shall provide real-time image acquisition.\n"
        "1.1 Growth chamber pumping system\n"
        "a) Cryogenic pumping system.\n"
    )
    version_id = uuid.uuid4()
    previous_page = DocumentPage(
        document_version_id=version_id,
        page_number=8,
        extracted_text=previous_text,
        cleaned_text=previous_text,
        ocr_needed=0,
    )
    next_page = DocumentPage(
        document_version_id=version_id,
        page_number=9,
        extracted_text=next_text,
        cleaned_text=next_text,
        ocr_needed=0,
    )

    spans = _boundary_continuation_ranges(
        previous_page,
        next_page,
        (SourceTextRange(0, len(previous_text)),),
        (SourceTextRange(0, len(next_text)),),
    )
    assert spans is not None
    previous_span, next_span = spans

    windows = build_source_windows(
        [previous_page, next_page],
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        max_chars=5000,
        overlap_chars=0,
        included_ranges_by_page={
            8: (previous_span,),
            9: (next_span,),
        },
    )
    assert len(windows) == 1
    assert len(windows[0].sources) == 2
    assert "The RHEED analysis software" in windows[0].text
    assert "1.1 Growth chamber pumping system" not in windows[0].text
    assert "a) Cryogenic pumping system" not in windows[0].text


def test_excluded_continuation_fragments_preserve_unrelated_page_ranges() -> None:
    source_ranges = (SourceTextRange(0, 100),)
    remaining = _subtract_source_range(
        source_ranges,
        (SourceTextRange(20, 30), SourceTextRange(60, 80)),
    )

    assert remaining == (
        SourceTextRange(0, 20),
        SourceTextRange(30, 60),
        SourceTextRange(80, 100),
    )


def test_lettered_requirement_labels_split_chunk_segments() -> None:
    text = f"a) {'x' * 50}\nb) {'y' * 50}"
    version_id = uuid.uuid4()
    page = DocumentPage(
        document_version_id=version_id,
        page_number=1,
        extracted_text=text,
        cleaned_text=text,
        ocr_needed=0,
    )

    windows = build_source_windows(
        [page],
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        max_chars=60,
        overlap_chars=0,
    )

    assert len(windows) == 2
    assert windows[0].text.startswith("a)")
    assert windows[1].text.startswith("b)")

# ---------------------------------------------------------------------------
# DB helpers (self-contained; tests/ is not a package)
# ---------------------------------------------------------------------------


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


async def _create_version_with_run(session_cm) -> dict:
    """Create org/project/doc/version/stored-object + an in-flight EXTRACT run."""

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    run_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()
    storage_key = build_key(
        org_id=org_id, project_id=project_id, document_id=doc_id, version=1
    )
    async with session_cm() as session:
        session.add(Organization(id=org_id, name="CP26 Org"))
        session.add(User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id)))
        session.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
        session.add(Project(id=project_id, organization_id=org_id, name="CP26 Project"))
        session.add(
            StoredObject(
                id=stored_object_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=storage_key,
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=10,
                checksum_sha256="abc123",
            )
        )
        session.add(TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf"))
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256="abc123",
            mime_type="application/pdf",
            size_bytes=10,
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        session.add(version)
        await session.flush()
        run = ProcessingRun(
            document_version_id=version_id,
            run_id=run_id,
            attempt=1,
            stage=ProcessingStage.EXTRACT,
            status=RunStatus.RUNNING,
        )
        session.add(run)
        await session.commit()
    return {
        "org_id": org_id,
        "user_id": user_id,
        "project_id": project_id,
        "doc_id": doc_id,
        "version_id": version_id,
        "version_number": 1,
        "run_id": run_id,
        "processing_run_id": run.id,
    }



# ---------------------------------------------------------------------------
# Port + provider-agnostic surface
# ---------------------------------------------------------------------------


class TestLlmAdapterPort:
    def test_both_providers_implement_the_port(self) -> None:
        """Swapping providers must never require rewriting document services:
        both the fake and the OpenAI adapter satisfy the same port, and both
        construct without network (openai is imported lazily)."""
        assert isinstance(FakeLlmAdapter(), LlmAdapter)
        # OpenAiLlmAdapter is constructible without OPENAI_API_KEY / the
        # openai package — the client is built lazily on first call.
        assert isinstance(OpenAiLlmAdapter(), LlmAdapter)

    def test_openai_adapter_reads_settings(self) -> None:
        adapter = OpenAiLlmAdapter()
        settings = get_settings()
        assert adapter._model == settings.openai_model  # noqa: SLF001


# ---------------------------------------------------------------------------
# FakeLlmAdapter — deterministic, no network
# ---------------------------------------------------------------------------


def _candidate(text: str, raw: str) -> RequirementCandidate:
    return RequirementCandidate(
        normalized_text=text,
        raw_source=raw,
        requirement_type=RequirementType.OBLIGATION,
        uncertainty=UncertaintyLevel.CONFIRMED,
        clause_section=None,
        group_hint=None,
    )


class _ConcurrentTrackingAdapter(LlmAdapter):
    provider = "tracking"
    model = "tracking"

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def extract(
        self, *, system_prompt: str, user_text: str, response_model: type,
        config: LlmCallConfig,
    ) -> ExtractResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.002 * (int(user_text[-1]) % 4 + 1))
        self.active -= 1
        call = LlmCallResult(
            provider=self.provider, model=self.model,
            prompt_version=config.prompt_version, schema_version=config.schema_version,
            latency_ms=0, prompt_tokens=None, completion_tokens=None,
            total_tokens=None, cost_usd=None, finish_reason="stop",
            status="completed", call_site=config.call_site,
        )
        return ExtractResult(
            response=ExtractionResponse(candidates=[
                _candidate(f"Requirement {user_text[-1]}", user_text)
            ]),
            call=call,
        )


class TestBoundedWindowConcurrency:
    def test_runs_windows_concurrently_and_preserves_ordered_audit(self) -> None:
        async def _run() -> None:
            org_id, doc_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            windows = [
                SourceWindow(
                    chunk_id=f"chunk-{index}", text=f"source text {index}",
                    sources=(TrustedSourceContext(
                        organization_id=org_id, document_id=doc_id,
                        document_version_id=version_id, page_number=index + 1,
                        source_text=f"source text {index}",
                    ),),
                )
                for index in range(8)
            ]
            adapter = _ConcurrentTrackingAdapter()
            logged: list[LlmCallResult] = []
            in_log = False

            async def log_call(call: LlmCallResult) -> None:
                nonlocal in_log
                assert not in_log
                in_log = True
                await asyncio.sleep(0)
                logged.append(call)
                in_log = False

            outcome = await extract_from_windows(windows, adapter, log_call=log_call)
            assert 1 < adapter.max_active <= 4
            assert [item.chunk_id for item in outcome.candidates] == [
                f"chunk-{index}" for index in range(8)
            ]
            assert [item.window_index for item in outcome.window_results] == list(range(1, 9))
            assert logged == outcome.llm_calls
            assert len(logged) == 8

        asyncio.run(_run())


class TestFakeLlmAdapter:
    def test_drives_extraction_without_network(self) -> None:
        raw = "shall be painted RAL 9005"
        response = ExtractionResponse(
            candidates=[_candidate("must be painted RAL 9005", raw)]
        )
        fake = FakeLlmAdapter(responses=[response])
        config = LlmCallConfig(
            provider="fake",
            model="fake",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            call_site="extract_candidates",
        )

        async def _run() -> None:
            result = await fake.extract(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_text=raw,
                response_model=ExtractionResponse,
                config=config,
            )
            assert isinstance(result, ExtractResult)
            assert result.response.candidates[0].normalized_text == (
                "must be painted RAL 9005"
            )
            assert result.call.provider == "fake"
            assert result.call.model == "fake"
            assert result.call.prompt_version == PROMPT_VERSION
            assert result.call.schema_version == SCHEMA_VERSION
            assert result.call.status == "completed"
            assert result.call.call_site == "extract_candidates"
            assert result.call.latency_ms == 0
            # Tokens/cost are null (unknown), never fabricated.
            assert result.call.cost_usd is None
            assert result.call.prompt_tokens is None
            assert result.call.total_tokens is None
            # The call was audited.
            assert len(fake.calls) == 1

        asyncio.run(_run())

    def test_returns_empty_when_no_responses(self) -> None:
        fake = FakeLlmAdapter()
        config = LlmCallConfig(
            provider="fake",
            model="fake",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            call_site="extract_candidates",
        )

        async def _run() -> None:
            result = await fake.extract(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_text="anything",
                response_model=ExtractionResponse,
                config=config,
            )
            assert result.response.candidates == []
            assert result.call.status == "completed"

        asyncio.run(_run())

    def test_calls_advance_through_responses(self) -> None:
        fake = FakeLlmAdapter(
            responses=[
                ExtractionResponse(
                    candidates=[_candidate("first", "first raw")]
                ),
                ExtractionResponse(
                    candidates=[_candidate("second", "second raw")]
                ),
            ]
        )
        config = LlmCallConfig(
            provider="fake", model="fake",
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
        )

        async def _run() -> None:
            r1 = await fake.extract(
                system_prompt="", user_text="",
                response_model=ExtractionResponse, config=config,
            )
            r2 = await fake.extract(
                system_prompt="", user_text="",
                response_model=ExtractionResponse, config=config,
            )
            assert r1.response.candidates[0].normalized_text == "first"
            assert r2.response.candidates[0].normalized_text == "second"
            assert len(fake.calls) == 2

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Prompt / schema versioning
# ---------------------------------------------------------------------------


class TestPromptVersioning:
    def test_versions_are_stable_non_empty_strings(self) -> None:
        assert PROMPT_VERSION
        assert SCHEMA_VERSION
        assert isinstance(PROMPT_VERSION, str)
        assert isinstance(SCHEMA_VERSION, str)

    def test_system_prompt_never_advised_to_invent(self) -> None:
        # The guardrail is encoded in the prompt: no fabrication.
        assert "fabricate" in EXTRACTION_SYSTEM_PROMPT
        assert "verbatim" in EXTRACTION_SYSTEM_PROMPT

    def test_system_prompt_is_section_bounded_and_preserves_source_wording(self) -> None:
        prompt = " ".join(EXTRACTION_SYSTEM_PROMPT.lower().split())
        for phrase in (
            "application supplies source windows only from that selected section",
            "do not use, infer from, or add material from any other part of the tender",
            "reproduce specification text exactly",
            "do not paraphrase, summarize, explain, assess compliance",
            "normalized_text: the exact same text as raw_source",
            "preferred",
            "or another reputable supplier",
            "only when they are inside the selected technical section",
            "never fabricate",
            'standalone numbered heading such as "1. growth chamber" is its own row',
            "separately lettered specification rows",
            "never merge sibling lettered rows",
            "keep the full text belonging to one labeled row together",
            "preserve grouped bullets as one candidate",
            "blank specification cell",
            "retain the exact item label as a source-linked row",
            "do not invent a specification for it",
            "grips and fixtures",
            "grouped \"other requirements\"",
            "utilities/spares",
            "lc50kn, pr9+sj1",
            "ve-xs1/m5+rce-25",
            "keep wide frame option, dual station configuration, and load cells together",
            "diamond-scriber example",
        ):
            assert phrase in prompt
        assert "1.13.0" == PROMPT_VERSION

    def test_extraction_response_uses_candidate_schema(self) -> None:
        # The LLM response schema is bounded by the CP25 RequirementCandidate.
        field = ExtractionResponse.model_fields["candidates"]
        assert field is not None  # candidates: list[RequirementCandidate]

    def test_source_window_selects_lettered_or_grouped_bullet_row_rules(self) -> None:
        lettered = system_prompt_for_source_window(
            "1. Growth chamber\na) First item\nb) Second item\n"
        )
        grouped = system_prompt_for_source_window(
            "Grips and Fixtures\n• First accessory\n• Second accessory\n"
        )
        assert "exactly one candidate per lettered row" in lettered
        assert "do not merge sibling letters" in lettered.lower()
        assert "keep related unnumbered bullets together" in grouped.lower()
        assert "do not emit one candidate per bullet" in grouped.lower()


# ---------------------------------------------------------------------------
# Run-metadata persistence (DocumentService.log_llm_call)
# ---------------------------------------------------------------------------


class TestRunMetadataPersistence:
    def test_log_llm_call_persists_config(self, session_cm) -> None:
        sf = _get_session_factory()
        call = LlmCallResult(
            provider="openai",
            model="gpt-4o",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            latency_ms=256,
            prompt_tokens=128,
            completion_tokens=41,
            total_tokens=169,
            cost_usd=None,  # unknown pricing, never fabricated zero
            finish_reason="stop",
            status="completed",
            call_site="extract_candidates",
        )

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            async with sf() as session:
                svc = DocumentService(session)
                row = await svc.log_llm_call(info["processing_run_id"], call)
                assert row.provider == "openai"
                assert row.model == "gpt-4o"
                assert row.prompt_version == PROMPT_VERSION
                assert row.schema_version == SCHEMA_VERSION
                assert row.latency_ms == 256
                assert row.prompt_tokens == 128
                assert row.completion_tokens == 41
                assert row.cost_usd is None  # not fabricated as 0
                assert row.finish_reason == "stop"
                assert row.status is ExtractionRunStatus.COMPLETED
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(ExtractionRun).where(
                            ExtractionRun.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1
                db = rows[0]
                assert db.provider == "openai"
                assert db.prompt_version == PROMPT_VERSION
                assert db.schema_version == SCHEMA_VERSION
                assert db.cost_usd is None
                assert db.latency_ms == 256

        asyncio.run(_run())

    def test_log_llm_call_captures_failure(self, session_cm) -> None:
        sf = _get_session_factory()
        call = LlmCallResult(
            provider="openai",
            model="gpt-4o",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            latency_ms=8,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            finish_reason=None,
            status="failed",
            error_message="connection timed out",
            call_site="extract_candidates",
        )

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            async with sf() as session:
                svc = DocumentService(session)
                await svc.log_llm_call(info["processing_run_id"], call)
                await session.commit()
            async with sf() as session:
                row = (
                    await session.execute(
                        select(ExtractionRun).where(
                            ExtractionRun.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalar_one()
                assert row.status is ExtractionRunStatus.FAILED
                assert row.error_message != "connection timed out"
                assert "processing stage" in (row.error_message or "").lower()
                assert row.finish_reason is None

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# OpenAI real call — opt-in only (never runs in CI / without a key)
# ---------------------------------------------------------------------------


class TestOpenAiAdapter:
    def test_real_call_is_opt_in(self) -> None:
        """A live OpenAI call must never run without an explicit opt-in to
        avoid surprise cost/token usage; CI always skips this."""
        if not os.environ.get("CP26_OPENAI_REAL_CALL"):
            pytest.skip("set CP26_OPENAI_REAL_CALL=1 to exercise the live call")
        settings = get_settings()
        if not settings.openai_api_key:
            pytest.skip("OPENAI_API_KEY not configured")

        adapter = OpenAiLlmAdapter()
        config = LlmCallConfig(
            provider="openai",
            model=settings.openai_model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            call_site="extract_candidates",
            timeout_s=15.0,
            max_retries=1,
        )

        async def _run() -> None:
            result = await adapter.extract(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_text="The handrail shall be painted RAL 9005.",
                response_model=ExtractionResponse,
                config=config,
            )
            assert isinstance(result, ExtractResult)
            assert isinstance(result.response, ExtractionResponse)
            assert result.call.provider == "openai"
            assert result.call.model == settings.openai_model
            assert result.call.status == "completed"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# CP28 — extraction orchestrator -> service -> DB candidate persistence
# ---------------------------------------------------------------------------


class TestExtractStageCandidates:
    """CP28 end-to-end: orchestrator + audit log + candidate persistence."""

    def test_validated_candidates_are_persisted_with_audit(
        self, session_cm
    ) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()

            text1 = (
                "The system shall encrypt all data at rest using AES-256 bit "
                "strong encryption and must not be disabled under any "
                "operating condition or maintenance mode of the device."
            )
            text2 = (
                "The unit shall weigh less than 2 kg in its installed "
                "configuration and must remain within operational temperature "
                "limits when subjected to continuous full-load operation."
            )
            w1 = SourceWindow(
                chunk_id="c1",
                text=text1,
                sources=(
                    TrustedSourceContext.from_page(
                        DocumentPage(
                            document_version_id=info["version_id"],
                            page_number=1,
                            cleaned_text=text1,
                            ocr_needed=False,
                        ),
                        info["org_id"],
                        info["doc_id"],
                    ),
                ),
                ocr_warning=False,
            )
            w2 = SourceWindow(
                chunk_id="c2",
                text=text2,
                sources=(
                    TrustedSourceContext.from_page(
                        DocumentPage(
                            document_version_id=info["version_id"],
                            page_number=2,
                            cleaned_text=text2,
                            ocr_needed=False,
                        ),
                        info["org_id"],
                        info["doc_id"],
                    ),
                ),
                ocr_warning=True,  # second window is OCR-derived
            )
            fake = FakeLlmAdapter(
                responses=[
                    ExtractionResponse(
                        candidates=[
                            _candidate("Encrypt data at rest with AES-256.", text1)
                        ]
                    ),
                    ExtractionResponse(
                        candidates=[
                            _candidate("Weigh less than 2 kg.", text2)
                        ]
                    ),
                ]
            )
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            persisted: list = []
            async with sf() as session:
                svc = DocumentService(session)
                # log_call anchors every audited LLM result to the EXTRACT run.
                log_call = lambda call: svc.log_llm_call(  # noqa: E731
                    info["processing_run_id"], call
                )
                outcome = await extract_from_windows(
                    [w1, w2], fake, log_call=log_call
                )
                await svc.store_extraction_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    candidates=outcome.candidates,
                )
                await session.commit()
                persisted = list(outcome.candidates)

            # audit + persistence assertions read back from the DB
            async with sf() as session:
                cands = (
                    await session.execute(
                        select(ExtractionCandidate).where(
                            ExtractionCandidate.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(cands) == 2
                by_chunk = {c.chunk_id: c for c in cands}
                rec1, rec2 = by_chunk["c1"], by_chunk["c2"]
                # window 1: confirm source text -> valid + persistable
                assert rec1.is_valid is True
                assert rec1.persistable is True
                assert rec1.uncertainty == UncertaintyLevel.CONFIRMED.value
                assert rec1.ocr_warning is False
                # window 2: OCR-derived -> CONFIRMED elevated to UNCERTAIN
                assert rec2.is_valid is True
                assert rec2.persistable is False
                assert rec2.uncertainty == UncertaintyLevel.UNCERTAIN.value
                assert rec2.ocr_warning is True
                # raw_source is stored verbatim, never mutated
                assert rec1.raw_source == text1
                assert rec1.normalized_text == "Encrypt data at rest with AES-256."
                # sources_json carries the trusted anchors (uuids as strings)
                import json as _json

                src = _json.loads(_json.dumps(rec1.sources_json))
                assert src[0]["document_id"] == str(info["doc_id"])

                # one audit row per LLM call, both completed + provider echoed
                runs = (
                    await session.execute(
                        select(ExtractionRun).where(
                            ExtractionRun.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalars().all()
                assert len(runs) == 2
                assert all(r.status == ExtractionRunStatus.COMPLETED for r in runs)
                assert all(r.provider == "fake" for r in runs)
                assert all(r.call_site == "extract_candidates" for r in runs)
                assert all(
                    r.prompt_version == PROMPT_VERSION for r in runs
                )
                assert all(r.schema_version == SCHEMA_VERSION for r in runs)

            assert len(persisted) == 2
            assert len(fake.calls) == 2

        asyncio.run(_run())

    def test_invalid_candidate_recorded_not_persisted(self, session_cm) -> None:
        """A candidate whose raw_source is absent from the window is kept for
        audit (is_valid=False, persistable=False) but stored as non-persistable."""

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()

            window_text = "The system performs data processing in memory only."
            w = SourceWindow(
                chunk_id="c1",
                text=window_text,
                sources=(
                    TrustedSourceContext.from_page(
                        DocumentPage(
                            document_version_id=info["version_id"],
                            page_number=1,
                            cleaned_text=window_text,
                            ocr_needed=False,
                        ),
                        info["org_id"],
                        info["doc_id"],
                    ),
                ),
                ocr_warning=False,
            )
            # raw_source is NOT a substring of window_text -> fabrication guard
            bad = _candidate(
                "Must be painted RAL 9005.",
                "The surface shall be painted RAL 9005 matt.",
            )
            fake = FakeLlmAdapter(responses=[ExtractionResponse(candidates=[bad])])
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            async with sf() as session:
                svc = DocumentService(session)
                log_call = lambda call: svc.log_llm_call(  # noqa: E731
                    info["processing_run_id"], call
                )
                outcome = await extract_from_windows([w], fake, log_call=log_call)
                await svc.store_extraction_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    candidates=outcome.candidates,
                )
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(ExtractionCandidate).where(
                            ExtractionCandidate.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1
                row = rows[0]
                assert row.is_valid is False
                assert row.persistable is False
                assert row.rejection_reason is not None
                assert "not present in the trusted source text" in (
                    row.rejection_reason or ""
                )

        asyncio.run(_run())

    def test_page_image_fallback_result_and_call_audit_are_persisted(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            text = "The unit shall operate below 30 dB(A)\n."
            window = SourceWindow(
                chunk_id="c1",
                text=text,
                sources=(
                    TrustedSourceContext.from_page(
                        DocumentPage(
                            document_version_id=info["version_id"],
                            page_number=1,
                            cleaned_text=text,
                            ocr_needed=True,
                        ),
                        info["org_id"],
                        info["doc_id"],
                    ),
                ),
                ocr_warning=True,
            )
            candidate = RequirementCandidate(
                normalized_text="The unit shall operate below 30 dB(A).",
                raw_source="The unit shall operate below 30 dB(A).",
                requirement_type=RequirementType.OBLIGATION,
                uncertainty=UncertaintyLevel.CONFIRMED,
            )
            class VisionFake(FakeLlmAdapter):
                async def extract_with_image(self, **kwargs):
                    return await self.extract(
                        system_prompt=kwargs["system_prompt"],
                        user_text=kwargs["user_text"],
                        response_model=kwargs["response_model"],
                        config=kwargs["config"],
                    )

            llm = VisionFake(
                responses=[
                    ExtractionResponse(candidates=[candidate]),
                    PageImageBatchResponse(
                        decisions=[
                            PageImageQuoteDecision(
                                item_id="0",
                                verdict="exact",
                                confidence=0.99,
                                visible_quote=text,
                                reason="Exact wording is visible on the cited page.",
                            )
                        ]
                    ),
                ]
            )
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            async with sf() as session:
                svc = DocumentService(session)
                outcome = await extract_from_windows(
                    [window],
                    llm,
                    log_call=lambda call: svc.log_llm_call(
                        info["processing_run_id"], call
                    ),
                    enable_verbatim_fallback=True,
                    coverage_page_images={1: b"page-image"},
                )
                await svc.store_extraction_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    candidates=outcome.candidates,
                )
                await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                assert await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                ) == (1, 0)
                await session.commit()

            async with sf() as session:
                candidate_row = (
                    await session.execute(
                        select(ExtractionCandidate).where(
                            ExtractionCandidate.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert candidate_row.is_valid is True
                assert candidate_row.persistable is True
                assert candidate_row.uncertainty == "uncertain"
                assert candidate_row.raw_source == candidate.raw_source
                assert candidate_row.verbatim_validation["status"] == (
                    "exact_page_image_match_for_human_review"
                )
                run_rows = (
                    await session.execute(
                        select(ExtractionRun).where(
                            ExtractionRun.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalars().all()
                assert len(run_rows) == 2
                assert {run.call_site for run in run_rows} == {
                    "extract_candidates",
                    "validate_extraction_candidate_page_image",
                }
                requirement = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert requirement.review_state == RequirementReviewState.OCR_WARNING
                source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == requirement.id
                        )
                    )
                ).scalar_one()
                assert source.location_type == "approximate"
        asyncio.run(_run())

    def test_empty_windows_produce_no_candidates(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            fake = FakeLlmAdapter()
            calls: list[LlmCallResult] = []

            async def log_call(call: LlmCallResult) -> None:
                calls.append(call)

            async with sf() as session:
                outcome = await extract_from_windows(
                    [], fake, log_call=log_call
                )
                assert outcome.candidates == []
                assert outcome.llm_calls == []
                assert calls == []
                # no candidates persisted for this version
                cnt = await session.execute(
                    select(ExtractionCandidate).where(
                        ExtractionCandidate.document_version_id
                        == info["version_id"]
                    )
                )
                assert len(cnt.scalars().all()) == 0

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# CP29 — reconciliation persistence (dedup + audit read-back)
# ---------------------------------------------------------------------------


def _persist_candidate_row(
    session,
    version_id: uuid.UUID,
    chunk_id: str,
    normalized_text: str,
    page_numbers: tuple[int, ...],
) -> ExtractionCandidate:
    return ExtractionCandidate(
        document_version_id=version_id,
        processing_run_id=None,
        chunk_id=chunk_id,
        window_text=normalized_text,
        sources_json=[
            {
                "page_number": p,
                "document_id": str(uuid.uuid4()),
                "document_version_id": str(version_id),
                "clause_number": None,
                "char_start": 0,
                "char_end": 10,
                "bbox": None,
                "ocr_confidence": None,
                "location_type": "approximate",
                "source_text": normalized_text,
            }
            for p in page_numbers
        ],
        normalized_text=normalized_text,
        raw_source=normalized_text,
        requirement_type="obligation",
        uncertainty="confirmed",
        clause_number=None,
        group_hint=None,
        ocr_warning=False,
        is_valid=True,
        persistable=True,
        rejection_reason=None,
    )


class TestReconciliationPersistence:
    """CP29 service: reconcile_version_candidates writes group/decision columns
    + an audit row, and is non-destructive for flagged-review groups."""

    def test_dedup_and_audit_rows_persisted(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )

            async with sf() as session:
                svc = DocumentService(session)
                rows = [
                    _persist_candidate_row(
                        session,
                        info["version_id"],
                        "c1",
                        "Shall encrypt data at rest using AES-256.",
                        (1,),
                    ),
                    # overlap duplicate: same text on page 1 (chunk c2)
                    _persist_candidate_row(
                        session,
                        info["version_id"],
                        "c2",
                        "Shall encrypt data at rest using AES-256.",
                        (1,),
                    ),
                    # singleton obligation on page 2
                    _persist_candidate_row(
                        session,
                        info["version_id"],
                        "c3",
                        "Enclosure must be IP67 rated.",
                        (2,),
                    ),
                ]
                session.add_all(rows)
                await session.flush()
                candidate_ids = [r.id for r in rows]

                outcome = await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()

            assert outcome.input_count == 3
            assert outcome.removed_count == 1
            assert outcome.singleton_count == 1

            async with sf() as session:
                db_rows = (
                    await session.execute(
                        select(ExtractionCandidate).where(
                            ExtractionCandidate.document_version_id
                            == info["version_id"]
                        )
                        .order_by(ExtractionCandidate.chunk_id)
                    )
                ).scalars().all()
                by_chunk = {r.chunk_id: r for r in db_rows}
                a, b, c = by_chunk["c1"], by_chunk["c2"], by_chunk["c3"]
                # overlap duplicate: 'b' deduped, 'a' canonical, same group
                assert b.deduped is True
                assert b.reconciliation_decision == "dedup_exact"
                assert b.reconciliation_group_id == a.reconciliation_group_id
                assert a.deduped is False
                assert c.deduped is False
                assert c.reconciliation_decision == "singleton"
                assert a.reconciliation_group_id != c.reconciliation_group_id
                # audit row
                audit = (
                    await session.execute(
                        select(ExtractionReconciliation).where(
                            ExtractionReconciliation.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(audit) == 1
                summary = audit[0].summary
                assert summary["input"] == 3
                assert summary["deduped"] == 1
                assert summary["singleton"] == 1

            assert candidate_ids[0] == a.id

        asyncio.run(_run())

    def test_identical_text_distinct_pages_flagged_not_deleted(
        self, session_cm
    ) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            hdr = "CONFIDENTIAL - Tender Document"

            async with sf() as session:
                svc = DocumentService(session)
                session.add_all(
                    [
                        _persist_candidate_row(
                            session, info["version_id"], "h1", hdr, (1,)
                        ),
                        _persist_candidate_row(
                            session, info["version_id"], "h2", hdr, (2,)
                        ),
                    ]
                )
                await session.flush()
                await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(ExtractionCandidate).where(
                            ExtractionCandidate.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                # flagged_review keeps BOTH (no silent deletion)
                assert len(rows) == 2
                assert all(r.deduped is False for r in rows)
                assert all(
                    r.reconciliation_decision == "flagged_review" for r in rows
                )
                assert rows[0].reconciliation_group_id == rows[1].reconciliation_group_id

        asyncio.run(_run())

    def test_reconcile_is_idempotent(self, session_cm) -> None:
        """Running reconciliation twice yields stable ids/decisions."""

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )

            async with sf() as session:
                svc = DocumentService(session)
                session.add_all(
                    [
                        _persist_candidate_row(
                            session, info["version_id"], "c1", "Same req text.", (1,)
                        ),
                        _persist_candidate_row(
                            session, info["version_id"], "c2", "Same req text.", (1,)
                        ),
                        _persist_candidate_row(
                            session, info["version_id"], "c3", "Other req.", (1,)
                        ),
                    ]
                )
                await session.flush()
                await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                first = {
                    r.chunk_id: (
                        r.reconciliation_group_id,
                        r.deduped,
                        r.reconciliation_decision,
                    )
                    for r in (
                        await session.execute(
                            select(ExtractionCandidate).where(
                                ExtractionCandidate.document_version_id
                                == info["version_id"]
                            )
                        )
                    ).scalars().all()
                }
                await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()

            async with sf() as session:
                second = {
                    r.chunk_id: (
                        r.reconciliation_group_id,
                        r.deduped,
                        r.reconciliation_decision,
                    )
                    for r in (
                        await session.execute(
                            select(ExtractionCandidate).where(
                                ExtractionCandidate.document_version_id
                                == info["version_id"]
                            )
                        )
                    ).scalars().all()
                }
                assert first == second

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# CP30 — candidate -> Requirement promotion persistence
# ---------------------------------------------------------------------------


def _make_candidate_row(
    session,
    version_id: uuid.UUID,
    chunk_id: str,
    normalized_text: str,
    raw_source: str,
    page_number: int,
    *,
    deduped: bool = False,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        document_version_id=version_id,
        processing_run_id=None,
        chunk_id=chunk_id,
        window_text=normalized_text,
        sources_json=[
            {
                "page_number": page_number,
                "document_id": str(uuid.uuid4()),
                "document_version_id": str(version_id),
                "clause_number": "1.1",
                "char_start": 0,
                "char_end": len(normalized_text),
                "bbox": None,
                "ocr_confidence": None,
                "location_type": "approximate",
                "source_text": normalized_text,
            }
        ],
        normalized_text=normalized_text,
        raw_source=raw_source,
        requirement_type="obligation",
        uncertainty="confirmed",
        clause_number="1.1",
        group_hint=None,
        ocr_warning=False,
        is_valid=True,
        persistable=True,
        deduped=deduped,
        reconciliation_decision=None,
        reconciliation_group_id=None,
        rejection_reason=None,
    )


class TestPromotionPersistence:
    """CP30 service: persist_requirements promotes deduped candidates into
    Requirements with EXACT/APPROXIMATE anchors, idempotently."""

    def test_exactly_anchored_requirement_persisted(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            text = "The system shall encrypt all data at rest using AES-256."
            raw = "shall encrypt all data at rest"

            async with sf() as session:
                svc = DocumentService(session)
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c1", text, raw, 1
                    )
                )
                await session.flush()
                inserted, skipped = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()
                assert inserted == 1
                assert skipped == 0

            async with sf() as session:
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert req.review_state == RequirementReviewState.UNREVIEWED
                assert req.normalized_text == text
                assert req.raw_source == raw
                assert req.requirement_type == "obligation"
                assert req.ocr_warning is False

                srcs = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == req.id
                        )
                    )
                ).scalars().all()
                assert len(srcs) == 1
                s = srcs[0]
                # raw is a literal substring of the page source_text -> EXACT
                assert s.location_type == "exact"
                assert s.char_start == text.find(raw)
                assert s.char_end == text.find(raw) + len(raw)
                assert s.page_number == 1
                assert s.clause_number == "1.1"
                assert s.source_text == text

        asyncio.run(_run())

    def test_uncertain_requirement_persists_only_for_human_review(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            text = "Hydraulic test capacity: 300 kN."

            async with sf() as session:
                svc = DocumentService(session)
                candidate = _make_candidate_row(
                    session, info["version_id"], "c-uncertain", text, text, 1
                )
                candidate.uncertainty = "uncertain"
                session.add(candidate)
                await session.flush()
                inserted, skipped = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()
                assert (inserted, skipped) == (1, 0)

            async with sf() as session:
                requirement = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert requirement.raw_source == text
                assert requirement.uncertainty == "uncertain"
                assert requirement.review_state == RequirementReviewState.NEEDS_CLARIFICATION

        asyncio.run(_run())


    def test_reprocess_is_idempotent_and_preserves_review_state(
        self, session_cm
    ) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            text = "The unit shall weigh less than 2 kg."
            raw = "weigh less than 2 kg"

            async with sf() as session:
                svc = DocumentService(session)
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c1", text, raw, 1
                    )
                )
                await session.flush()
                first = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                assert first == (1, 0)
                # simulate a human reviewer setting the state
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                req.review_state = RequirementReviewState.REVIEWED
                await session.flush()
                # reprocess an unchanged version -> 0 inserted, 1 skipped,
                # and the human-reviewed state is preserved (not overwritten).
                second = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                assert second == (0, 1)
                await session.commit()

            async with sf() as session:
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert req.review_state == RequirementReviewState.REVIEWED
                # still exactly one requirement row (no duplication)
                count = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(count) == 1

        asyncio.run(_run())


    def test_deduped_candidates_are_not_promoted(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            text = "Shall operate below 30 dB(A)."
            async with sf() as session:
                svc = DocumentService(session)
                # one promotable + one deduped (suppressed) duplicate
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c1", text, text, 1
                    )
                )
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c2", text, text, 1,
                        deduped=True,
                    )
                )
                await session.flush()
                inserted, skipped = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()
            assert inserted == 1  # only the non-deduped candidate

            async with sf() as session:
                count = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(count) == 1

        asyncio.run(_run())


    def test_non_literal_raw_source_round_trips_as_approximate(
        self, session_cm
    ) -> None:
        """When ``raw_source`` is NOT a literal substring of the page text
        (e.g. the model collapsed whitespace that differs in the page), the
        resolver must fall back to APPROXIMATE and reuse the fragment's stored
        char span rather than fabricating an offset."""

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            page_text = "The  system  shall  encrypt data at rest."  # extra spaces
            raw = "shall encrypt data at rest"  # NOT a literal substring
            assert page_text.find(raw) == -1  # not literal -> APPROXIMATE

            async with sf() as session:
                svc = DocumentService(session)
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c1", page_text, raw, 1
                    )
                )
                await session.flush()
                await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()

            async with sf() as session:
                s = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id
                            == (
                                await session.execute(
                                    select(Requirement.id).where(
                                        Requirement.document_version_id
                                        == info["version_id"]
                                    )
                                )
                            ).scalar_one()
                        )
                    )
                ).scalar_one()
                assert s.location_type == "approximate"
                # fragment's stored span reused (0..len), not fabricated
                assert s.char_start == 0
                assert s.char_end == len(page_text)

        asyncio.run(_run())


    def test_promotion_key_stored_and_stable(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            text = "The relay shall switch 10 A at 250 V AC."
            raw = text
            async with sf() as session:
                svc = DocumentService(session)
                session.add(
                    _make_candidate_row(
                        session, info["version_id"], "c1", text, raw, 1
                    )
                )
                await session.flush()
                await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                await session.commit()

            expected = promotion_key(text, "obligation", "1.1", (1,))
            async with sf() as session:
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert req.promotion_key == expected

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# CP31 — extraction diagnostics persistence
# ---------------------------------------------------------------------------


def _candidate_record(
    *,
    chunk_id: str = "c1",
    normalized_text: str = "req",
    raw_source: str = "req",
    source_text: str = "req",
    page_number: int = 1,
    valid: bool = True,
    persistable: bool = True,
    uncertainty: str = "confirmed",
    requirement_type: str = "obligation",
    ocr_warning: bool = False,
    rejection_reason: str | None = None,
) -> CandidateRecord:
    """Build a CP30-style CandidateRecord with a single trusted source fragment."""

    return CandidateRecord(
        chunk_id=chunk_id,
        sources_json=[
            {
                "page_number": page_number,
                "document_id": str(uuid.uuid4()),
                "document_version_id": str(uuid.uuid4()),
                "clause_number": "1.1",
                "char_start": 0,
                "char_end": len(source_text),
                "bbox": None,
                "ocr_confidence": None,
                "location_type": "approximate",
                "source_text": source_text,
            }
        ],
        window_text=source_text,
        normalized_text=normalized_text,
        raw_source=raw_source,
        requirement_type=requirement_type,
        uncertainty=uncertainty,
        clause_number="1.1",
        group_hint=None,
        ocr_warning=ocr_warning,
        is_valid=valid,
        persistable=persistable,
        rejection_reason=rejection_reason,
    )


class TestExtractionDiagnostics:
    """CP31 end-to-end: EXTRACT pass -> diagnostics row captures counts."""

    def test_diagnostics_row_written_with_correct_counts(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )

            text_a = "The system shall encrypt data at rest using AES-256."
            text_b = "The unit shall weigh less than 2 kg."
            # A + B are two windows; A emits the SAME obligation twice (overlap
            # duplicate on page 1 -> one deduped), B emits a distinct obligation
            # on page 2; one window emits a fabrication (rejected, not persisted
            # as promotable).
            outcome = ExtractionOutcome(
                candidates=[
                    _candidate_record(
                        chunk_id="c1",
                        normalized_text="Encrypt data at rest.",
                        raw_source="Encrypt data at rest.",
                        source_text=text_a,
                        page_number=1,
                    ),  # A1: valid+persistable, page 1
                    _candidate_record(
                        chunk_id="c1",
                        normalized_text="Encrypt data at rest.",
                        raw_source="Encrypt data at rest.",
                        source_text=text_a,
                        page_number=1,
                    ),  # A2: valid+persistable, page 1 (deduped w/ A1)
                    _candidate_record(
                        chunk_id="c1",
                        normalized_text="Bogus fabricated obligation.",
                        raw_source="something not in window",
                        source_text=text_a,
                        page_number=1,
                        valid=False,
                        persistable=False,
                        rejection_reason="fabrication:raw_source not in window text",
                    ),  # C: rejected (fabrication guard)
                    _candidate_record(
                        chunk_id="c2",
                        normalized_text="Weigh less than 2 kg.",
                        raw_source="Weigh less than 2 kg.",
                        source_text=text_b,
                        page_number=2,
                    ),  # D: valid+persistable, page 2 (singleton)
                ],
                llm_calls=[
                    LlmCallResult(
                        provider="fake", model="fake",
                        prompt_version=PROMPT_VERSION,
                        schema_version=SCHEMA_VERSION, latency_ms=5,
                        prompt_tokens=10, completion_tokens=3, total_tokens=13,
                        cost_usd=None, finish_reason="stop",
                        status="completed", call_site="extract_candidates",
                    ),
                    LlmCallResult(
                        provider="fake", model="fake",
                        prompt_version=PROMPT_VERSION,
                        schema_version=SCHEMA_VERSION, latency_ms=5,
                        prompt_tokens=None, completion_tokens=None,
                        total_tokens=None, cost_usd=None, finish_reason="stop",
                        status="completed", call_site="extract_candidates",
                    ),
                ],
                window_results=[
                    WindowExtractionResult(
                        chunk_id="c1",
                        window_index=1,
                        call_status="completed",
                        candidate_count=3,
                        ocr_warning=False,
                        source_spans=[
                            {
                                "page_number": 1,
                                "clause_number": None,
                                "char_start": 0,
                                "char_end": len(text_a),
                            }
                        ],
                    ),
                    WindowExtractionResult(
                        chunk_id="c2",
                        window_index=2,
                        call_status="completed",
                        candidate_count=1,
                        ocr_warning=False,
                        source_spans=[
                            {
                                "page_number": 2,
                                "clause_number": None,
                                "char_start": 0,
                                "char_end": len(text_b),
                            }
                        ],
                    ),
                ],
            )

            async with sf() as session:
                svc = DocumentService(session)
                await svc.store_extraction_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    candidates=outcome.candidates,
                )
                recon = await svc.reconcile_version_candidates(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                inserted, _skipped = await svc.persist_requirements(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                )
                assert inserted == 2  # A1 + D promoted (A2 deduped, C rejected)
                diag = await svc.capture_extraction_diagnostics(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    outcome=outcome,
                    reconciliation_outcome=recon,
                    promoted_count=inserted,
                )
                await session.commit()
                diag_id = diag.id

            async with sf() as session:
                row = (
                    await session.execute(
                        select(ExtractionDiagnostics).where(
                            ExtractionDiagnostics.id == diag_id
                        )
                    )
                ).scalar_one()
                assert row.total_windows == 2
                assert row.total_llm_calls == 2
                assert row.total_candidates == 4
                # A1, A2, D are valid+persistable
                assert row.accepted_candidates == 3
                # C is the only invalid candidate
                assert row.rejected_candidates == 1
                assert row.rejection_breakdown == {
                    "fabrication:raw_source not in window text": 1
                }
                # A2 deduped by reconcile (overlap duplicate on page 1)
                assert row.deduped_candidates == recon.removed_count == 1
                # A1 + D promoted to requirements
                assert row.promoted_requirements == 2
                assert row.ocr_warning_candidates == 0
                # Versions captured from the audited LLM calls
                assert row.provider == "fake"
                assert row.model == "fake"
                assert row.prompt_version == PROMPT_VERSION
                assert row.schema_version == SCHEMA_VERSION
                # Reconciliation summary carried through verbatim
                assert row.reconciliation_summary == recon.summary()
                windows = (
                    await session.execute(
                        select(ExtractionWindowAudit)
                        .where(
                            ExtractionWindowAudit.processing_run_id
                            == info["processing_run_id"]
                        )
                        .order_by(ExtractionWindowAudit.window_index)
                    )
                ).scalars().all()
                assert [(window.chunk_id, window.call_status) for window in windows] == [
                    ("c1", "completed"),
                    ("c2", "completed"),
                ]
                assert [window.candidate_count for window in windows] == [3, 1]
                assert [window.source_spans[0]["page_number"] for window in windows] == [
                    1,
                    2,
                ]

        asyncio.run(_run())

    def test_diagnostics_unique_per_run(self, session_cm) -> None:
        """A second EXTRACT run (new run_id) writes a second diagnostics row
        (history grows), each anchored to its own processing_run_id."""

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            outcome = ExtractionOutcome(
                candidates=[_candidate_record()],
                llm_calls=[
                    LlmCallResult(
                        provider="fake", model="fake",
                        prompt_version=PROMPT_VERSION,
                        schema_version=SCHEMA_VERSION, latency_ms=1,
                        prompt_tokens=1, completion_tokens=1, total_tokens=2,
                        cost_usd=None, finish_reason="stop", status="completed",
                        call_site="extract_candidates",
                    ),
                ],
            )
            run2_id = uuid.uuid4()
            async with sf() as session:
                svc = DocumentService(session)
                await svc.capture_extraction_diagnostics(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=info["run_id"],
                    outcome=outcome,
                )
                second_run = ProcessingRun(
                    document_version_id=info["version_id"],
                    run_id=run2_id,
                    attempt=1,
                    stage=ProcessingStage.EXTRACT,
                    status=RunStatus.RUNNING,
                )
                session.add(second_run)
                await session.flush()
                second_processing_run_id = second_run.id
                await svc.capture_extraction_diagnostics(
                    auth,
                    document_id=info["doc_id"],
                    version_number=info["version_number"],
                    run_id=run2_id,
                    outcome=outcome,
                )
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(ExtractionDiagnostics).where(
                            ExtractionDiagnostics.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(rows) == 2
                assert {r.processing_run_id for r in rows} == {
                    info["processing_run_id"],
                    second_processing_run_id,
                }

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# CP31 regression — EXTRACT-stage call-site anchor (CP28 orchestrator)
# ---------------------------------------------------------------------------


class TestExtractStageDiagnosticsCaptureCP31:
    """The EXTRACT orchestrator (``JobProcessor._do_extract``) must anchor the
    CP31 diagnostics row to the run's ``run_id`` *column* (the value
    :meth:`DocumentService.get_run` resolves — matched against
    ``ProcessingRun.run_id``), never the row PK (``ProcessingRun.id``).

    Previously the call site passed ``run.id`` (PK). ``get_run`` then matched
    nothing, raised ``DocumentNotFoundError`` ("processing run … not found"),
    and the (best-effort) handler in ``_do_extract`` swallowed it — silently
    dropping the diagnostics row. ``run.run_id`` is the column value
    ``get_run`` looks up, so the row is captured.

    This end-to-end test exercises the real call site: it FAILS with the bug
    (no diagnostics row) and PASSES with the fix (row present)."""

    def test_do_extract_persists_diagnostics_row(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            text = (
                "TECHNICAL SPECIFICATION:\n"
                "The enclosure shall be sealed to IP65 minimum ingress protection."
            )
            fake = FakeLlmAdapter(
                responses=[
                    ExtractionResponse(
                        candidates=[_candidate("Sealed to IP65 minimum.", text)]
                    )
                ]
            )
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            proc = JobProcessor(sf, llm=fake)

            async with sf() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                ).scalar_one()
                # _load_pages queries DocumentPage by version_id; the extractor
                # chunks these windows and the fake LLM answers per window.
                session.add(
                    DocumentPage(
                        document_version_id=info["version_id"],
                        page_number=1,
                        cleaned_text=text,
                        ocr_needed=False,
                    )
                )
                await session.flush()
                svc = DocumentService(session)
                await proc._do_extract(  # noqa: SLF001 — exercising private stage
                    session, svc, auth, version, run_id=info["run_id"]
                )
                await session.commit()

            # The diagnostics row must exist — proof the orchestrator passed the
            # run_id *column* (run.run_id) to capture_extraction_diagnostics.
            async with sf() as session:
                rows = (
                    await session.execute(
                        select(ExtractionDiagnostics).where(
                            ExtractionDiagnostics.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1

        asyncio.run(_run())

    def test_do_extract_fails_closed_without_technical_section(self, session_cm) -> None:
        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            fake = FakeLlmAdapter()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            processor = JobProcessor(sf, llm=fake)

            async with sf() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=info["version_id"],
                        page_number=1,
                        cleaned_text=(
                            "Eligibility criteria\n"
                            "The bidder shall provide audited financial statements."
                        ),
                        ocr_needed=False,
                    )
                )
                await session.flush()
                service = DocumentService(session)
                await processor._do_extract(  # noqa: SLF001
                    session, service, auth, version, run_id=info["run_id"]
                )
                await session.commit()

            assert fake.calls == []
            async with sf() as session:
                run = (
                    await session.execute(
                        select(ProcessingRun).where(
                            ProcessingRun.id == info["processing_run_id"]
                        )
                    )
                ).scalar_one()
                assert run.status == RunStatus.FAILED
                assert run.error_type == "technical_specification_section_not_found"

        asyncio.run(_run())

    def test_do_extract_loads_saved_page_image_for_ocr_coverage_audit(
        self, session_cm
    ) -> None:
        class VisionFake(FakeLlmAdapter):
            def __init__(self) -> None:
                super().__init__(
                    [
                        ExtractionResponse(candidates=[]),
                        ImageObligationCoverageResponse(
                            quotes=[
                                ImageCoverageQuote(
                                    source_quote=(
                                        "The enclosure shall be sealed to IP65."
                                    ),
                                    confidence=0.999,
                                    bbox={
                                        "x": 0.1,
                                        "y": 0.1,
                                        "width": 0.5,
                                        "height": 0.04,
                                    },
                                )
                            ],
                            confidence=0.999,
                            uncertain=False,
                        ),
                    ]
                )
                self.image_bytes: list[bytes] = []

            async def extract_with_image(self, **kwargs):
                self.image_bytes.append(kwargs["image_bytes"])
                return await self.extract(
                    system_prompt=kwargs["system_prompt"],
                    user_text=kwargs["user_text"],
                    response_model=kwargs["response_model"],
                    config=kwargs["config"],
                )

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            image_key = "rendered/ocr-coverage-page.png"
            png = (
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR"
                + struct.pack(">II", 1000, 2000)
            )
            storage = FakeStorageAdapter()
            await storage.put(image_key, png, "image/png")
            llm = VisionFake()
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            processor = JobProcessor(
                sf,
                llm=llm,
                storage=storage,
                obligation_coverage_audit_enabled=True,
            )

            async with sf() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=info["version_id"],
                        page_number=1,
                        cleaned_text=(
                            "TECHNICAL SPECIFICATION:\n"
                            "The enclosure shall be sealed to IP6S."
                        ),
                        ocr_needed=True,
                        rendered_image_object_key=image_key,
                    )
                )
                await session.flush()
                service = DocumentService(session)
                await processor._do_extract(  # noqa: SLF001
                    session, service, auth, version, run_id=info["run_id"]
                )
                await session.commit()

            async with sf() as session:
                audit = (
                    await session.execute(
                        select(ExtractionWindowAudit).where(
                            ExtractionWindowAudit.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalar_one()
                assert audit.coverage_status == "completed"
                assert audit.coverage_error_category is None
                assert audit.potential_omissions == [
                    {
                        "page_number": 1,
                        "source_quote": "The enclosure shall be sealed to IP65.",
                        "bbox": {
                            "x": 100.0,
                            "y": 200.0,
                            "width": 500.0,
                            "height": 80.0,
                        },
                    }
                ]
            assert llm.image_bytes == [png]

        asyncio.run(_run())

    def test_do_extract_persists_page_image_error_category(self, session_cm) -> None:
        class FailingVisionFake(FakeLlmAdapter):
            def __init__(self) -> None:
                super().__init__([ExtractionResponse(candidates=[])])

            async def extract_with_image(self, **_kwargs):
                raise LlmCallError(
                    "provider details intentionally omitted",
                    error_category="image_parse_error",
                )

        async def _run() -> None:
            info = await _create_version_with_run(session_cm)
            sf = _get_session_factory()
            image_key = "rendered/ocr-coverage-error-page.png"
            png = (
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR"
                + struct.pack(">II", 1000, 2000)
            )
            storage = FakeStorageAdapter()
            await storage.put(image_key, png, "image/png")
            auth = AuthContext(
                actor_id=info["user_id"],
                organization_id=info["org_id"],
                roles=frozenset({"owner"}),
            )
            processor = JobProcessor(
                sf,
                llm=FailingVisionFake(),
                storage=storage,
                obligation_coverage_audit_enabled=True,
            )

            async with sf() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=info["version_id"],
                        page_number=1,
                        cleaned_text=(
                            "TECHNICAL SPECIFICATION:\n"
                            "Unclear scanned technical text."
                        ),
                        ocr_needed=True,
                        rendered_image_object_key=image_key,
                    )
                )
                await session.flush()
                service = DocumentService(session)
                await processor._do_extract(  # noqa: SLF001
                    session, service, auth, version, run_id=info["run_id"]
                )
                await session.commit()

            async with sf() as session:
                audit = (
                    await session.execute(
                        select(ExtractionWindowAudit).where(
                            ExtractionWindowAudit.processing_run_id
                            == info["processing_run_id"]
                        )
                    )
                ).scalar_one()
                assert audit.coverage_status == "failed"
                assert audit.coverage_error_category == "image_parse_error"
                assert audit.potential_omissions == []

        asyncio.run(_run())
