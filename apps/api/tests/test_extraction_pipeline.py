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
from tender_compliance_api.document.service import DocumentService
from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallResult,
)
from tender_compliance_api.extraction.chunking import SourceWindow
from tender_compliance_api.extraction.extractor import (
    CandidateRecord,
    ExtractionOutcome,
    extract_from_windows,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter
from tender_compliance_api.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionResponse,
)
from tender_compliance_api.extraction.requirement import promotion_key
from tender_compliance_api.extraction.schema import (
    RequirementCandidate,
    RequirementType,
    TrustedSourceContext,
    UncertaintyLevel,
)
from tender_compliance_api.storage.keys import build_key

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

    def test_extraction_response_uses_candidate_schema(self) -> None:
        # The LLM response schema is bounded by the CP25 RequirementCandidate.
        field = ExtractionResponse.model_fields["candidates"]
        assert field is not None  # candidates: list[RequirementCandidate]


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
                assert row.error_message == "connection timed out"
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
