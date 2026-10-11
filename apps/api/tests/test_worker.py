"""Tests for the queue adapter and worker job-processing (CP18).

Covers:
- FakeQueueAdapter enqueue/dequeue/acknowledge/release/idempotency.
- make_job_id determinism.
- JobProcessor processing a version through the state machine.
- Worker.run_once picking up a queued job and transitioning to PARSED.
- Idempotency: re-delivered jobs for already-terminal versions are skipped.
- Full upload → queue → worker → PARSED flow.
"""

from __future__ import annotations

import asyncio
import io
import time
import uuid
from io import BytesIO

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    OemDocument,
    OemDocumentVersion,
    OemTextSegment,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    RunStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.export.vendor_response_docx import build_vendor_response_docx
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.prompts import ExtractionResponse
from tender_compliance_api.extraction.schema import (
    RequirementCandidate,
    RequirementType,
    UncertaintyLevel,
)
from tender_compliance_api.main import app
from tender_compliance_api.matrix.projection import project_matrix_rows
from tender_compliance_api.parser import FakeParserAdapter
from tender_compliance_api.parser.adapter import PageResult, ParseResult
from tender_compliance_api.queue import (
    DEFAULT_QUEUE,
    FakeQueueAdapter,
    QueuedJob,
    QueueMessage,
)
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.routes.uploads import (
    get_queue_adapter as get_queue_adapter_dep,
)
from tender_compliance_api.routes.uploads import (
    get_scanner as get_scanner_dep,
)
from tender_compliance_api.routes.uploads import (
    get_storage_adapter as get_storage_dep,
)
from tender_compliance_api.scan.fake import FakeScanner
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import WORKER_ACTOR_ID, JobProcessor
from tender_compliance_worker.worker import Worker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _worker_auth(org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=WORKER_ACTOR_ID,
        organization_id=org_id,
        roles=frozenset({"worker"}),
    )


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


def _make_pdf() -> bytes:
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buf)
    return buf.getvalue()


async def _create_org_project(
    session_cm, status: str = "documents_processing"
) -> dict[str, uuid.UUID]:
    """Create org + user + membership + project. Returns info dict."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    async with session_cm() as session:
        session.add(Organization(id=org_id, name="CP18 Test Org"))
        session.add(
            User(
                id=user_id,
                auth_provider="dev",
                auth_provider_user_id=str(user_id),
            )
        )
        session.add(
            Membership(organization_id=org_id, user_id=user_id, role="owner")
        )
        session.add(
            Project(
                id=project_id,
                organization_id=org_id,
                name="CP18 Test Project",
                status=status,
            )
        )
        await session.commit()
    return {
        "org_id": org_id,
        "user_id": user_id,
        "project_id": project_id,
    }


async def _create_version(
    session_cm,
    org_id: uuid.UUID,
    status: DocumentProcessingStatus,
    *,
    pdf_bytes: bytes | None = None,
) -> dict:
    """Create org + user + membership + project + document + version + stored object.

    Returns a dict with IDs and ``storage_key`` + ``stored_object_id`` so
    tests can populate a :class:`FakeStorageAdapter` with the bytes.
    """
    info = await _create_org_project(session_cm)
    org_id = info["org_id"]
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()

    if pdf_bytes is None:
        pdf_bytes = _make_pdf()

    storage_key = build_key(
        org_id=org_id,
        project_id=info["project_id"],
        document_id=doc_id,
        version=1,
    )

    import hashlib

    async with session_cm() as session:
        stored = StoredObject(
            id=stored_object_id,
            organization_id=org_id,
            project_id=info["project_id"],
            storage_key=storage_key,
            filename="tender.pdf",
            content_type="application/pdf",
            content_length=len(pdf_bytes),
            checksum_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        session.add(stored)

        doc = TenderDocument(
            id=doc_id,
            project_id=info["project_id"],
            display_name="tender.pdf",
        )
        session.add(doc)
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            processing_status=status,
        )
        session.add(version)
        await session.commit()
    info.update(
        doc_id=doc_id,
        version_id=version_id,
        version_number=1,
        stored_object_id=stored_object_id,
        storage_key=storage_key,
        pdf_bytes=pdf_bytes,
    )
    return info


# ---------------------------------------------------------------------------
# Queue adapter tests (FakeQueueAdapter)
# ---------------------------------------------------------------------------


class TestFakeQueueAdapter:
    """Unit tests for the in-memory fake queue."""

    def _msg(self) -> QueueMessage:
        return QueueMessage(
            document_version_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            version_number=1,
            stage="parse",
            run_id=str(uuid.uuid4()),
            attempt=1,
        )

    def test_enqueue_dequeue(self) -> None:
        queue = FakeQueueAdapter()

        async def _run():
            msg = self._msg()
            job_id = "test-job-1"
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)
            assert await queue.size(DEFAULT_QUEUE) == 1
            job = await queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            assert job.job_id == job_id
            assert job.payload["document_version_id"] == msg.document_version_id
            assert job.attempt == 1

        asyncio.run(_run())

    def test_dequeue_empty_returns_none(self) -> None:
        queue = FakeQueueAdapter()
        assert asyncio.run(queue.dequeue(DEFAULT_QUEUE)) is None

    def test_acknowledge_removes_job(self) -> None:
        queue = FakeQueueAdapter()

        async def _run():
            msg = self._msg()
            job_id = "test-job-2"
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)
            job = await queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            await queue.acknowledge(DEFAULT_QUEUE, job_id)
            assert await queue.dequeue(DEFAULT_QUEUE) is None
            assert await queue.size(DEFAULT_QUEUE) == 0

        asyncio.run(_run())

    def test_release_requeues(self) -> None:
        queue = FakeQueueAdapter()

        async def _run():
            msg = self._msg()
            job_id = "test-job-3"
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)
            job = await queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            await queue.release(DEFAULT_QUEUE, job_id)
            job2 = await queue.dequeue(DEFAULT_QUEUE)
            assert job2 is not None
            assert job2.job_id == job_id

        asyncio.run(_run())

    def test_release_with_delay_defers(self) -> None:
        queue = FakeQueueAdapter()

        async def _run():
            msg = self._msg()
            job_id = "test-job-4"
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)
            job = await queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            await queue.release(DEFAULT_QUEUE, job_id, delay=3600)
            # Job should not be available immediately.
            assert await queue.dequeue(DEFAULT_QUEUE) is None
            assert await queue.size(DEFAULT_QUEUE) == 1

        asyncio.run(_run())

    def test_duplicate_enqueue_idempotent(self) -> None:
        queue = FakeQueueAdapter()

        async def _run():
            msg = self._msg()
            job_id = "dup-job"
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)
            await queue.enqueue(DEFAULT_QUEUE, job_id, msg)  # no-op
            job = await queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            # Only one dequeue should succeed.
            assert await queue.dequeue(DEFAULT_QUEUE) is None

        asyncio.run(_run())


class TestMakeJobId:
    def test_deterministic(self) -> None:
        v = "12345678-1234-5678-1234-567812345678"
        assert make_job_id(v, "parse") == make_job_id(v, "parse")

    def test_different_version_different_id(self) -> None:
        assert make_job_id("v1", "parse") != make_job_id("v2", "parse")

    def test_different_stage_different_id(self) -> None:
        v = "12345678-1234-5678-1234-567812345678"
        assert make_job_id(v, "parse") != make_job_id(v, "ocr")


# ---------------------------------------------------------------------------
# JobProcessor tests
# ---------------------------------------------------------------------------


class TestJobProcessor:
    """Tests for the worker's JobProcessor (CP19 — PARSE stage integration)."""

    def test_processing_status_is_visible_while_parse_is_running(self, session_cm) -> None:
        async def _run():
            info = await _create_version(
                session_cm, uuid.uuid4(), DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            storage = FakeStorageAdapter()
            storage._store[info["storage_key"]] = info["pdf_bytes"]
            storage._meta[info["storage_key"]] = {
                "content_type": "application/pdf",
                "content_length": len(info["pdf_bytes"]),
                "etag": "test-etag",
                "stored_at": time.time(),
            }

            class BlockingParser(FakeParserAdapter):
                def __init__(self) -> None:
                    super().__init__(
                        pages=[
                            PageResult(
                                page_number=1,
                                text="test page text",
                                text_length=15,
                                ocr_needed=False,
                                warnings=[],
                                error=None,
                            )
                        ]
                    )
                    self.started = asyncio.Event()
                    self.release = asyncio.Event()

                async def parse(self, data: bytes, mime_type: str) -> ParseResult:
                    self.started.set()
                    await self.release.wait()
                    return await super().parse(data, mime_type)

            parser = BlockingParser()
            processor = JobProcessor(sf, parser=parser, storage=storage)
            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = QueuedJob(
                job_id=str(run_id),
                payload={
                    "document_version_id": str(info["version_id"]),
                    "document_id": str(info["doc_id"]),
                    "organization_id": str(info["org_id"]),
                    "version_number": info["version_number"],
                    "stage": "parse",
                    "run_id": str(run_id),
                    "attempt": 1,
                },
                attempt=1,
                queue=DEFAULT_QUEUE,
            )

            task = asyncio.create_task(processor.process(job))
            try:
                await asyncio.wait_for(parser.started.wait(), timeout=5)
                async with sf() as session:
                    version_result = await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                    run_result = await session.execute(
                        select(ProcessingRun).where(
                            ProcessingRun.document_version_id == info["version_id"],
                            ProcessingRun.run_id == run_id,
                            ProcessingRun.stage == ProcessingStage.PARSE,
                        )
                    )
                    assert (
                        version_result.scalar_one().processing_status
                        == DocumentProcessingStatus.PROCESSING
                    )
                    assert run_result.scalar_one().status == RunStatus.RUNNING
            finally:
                parser.release.set()
            await task

        asyncio.run(_run())

    def test_process_transitions_to_parsed(self, session_cm) -> None:
        """Processing a QUEUED version transitions it to PARSED."""

        async def _run():
            info = await _create_version(
                session_cm, uuid.uuid4(), DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            # Use FakeParserAdapter + FakeStorageAdapter with the PDF bytes.
            storage = FakeStorageAdapter()
            storage._store[info["storage_key"]] = info["pdf_bytes"]
            storage._meta[info["storage_key"]] = {
                "content_type": "application/pdf",
                "content_length": len(info["pdf_bytes"]),
                "etag": "test-etag",
                "stored_at": time.time(),
            }
            pages = [
                PageResult(
                    page_number=1,
                    text="test page text",
                    text_length=13,
                    ocr_needed=False,
                    warnings=[],
                    error=None,
                )
            ]
            parser = FakeParserAdapter(pages=pages)
            processor = JobProcessor(sf, parser=parser, storage=storage)

            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = QueuedJob(
                job_id=str(run_id),
                payload={
                    "document_version_id": str(info["version_id"]),
                    "document_id": str(info["doc_id"]),
                    "organization_id": str(info["org_id"]),
                    "version_number": info["version_number"],
                    "stage": "parse",
                    "run_id": str(run_id),
                    "attempt": 1,
                },
                attempt=1,
                queue=DEFAULT_QUEUE,
            )
            await processor.process(job)

            # Verify the version is now PARSED
            async with sf() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == info["version_id"]
                    )
                )
                updated = result.scalar_one()
                assert updated.processing_status == DocumentProcessingStatus.PARSED
                assert updated.parser_name == "fake"
                assert updated.parser_version == "test"

                # Verify ProcessingRun rows exist for all 4 stages
                run_result = await session.execute(
                    select(ProcessingRun).where(
                        ProcessingRun.document_version_id == info["version_id"]
                    )
                )
                runs = list(run_result.scalars().all())
                assert len(runs) == 4
                for r in runs:
                    assert r.status == RunStatus.COMPLETED

                # Verify DocumentPage rows were stored
                page_result = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == info["version_id"]
                    )
                )
                pages_stored = list(page_result.scalars().all())
                assert len(pages_stored) == 1
                assert pages_stored[0].page_number == 1
                assert pages_stored[0].extracted_text == "test page text"

        asyncio.run(_run())

    def test_idempotent_skip_terminal(self, session_cm) -> None:
        """Re-delivered job for an already-PARSED version is a no-op."""

        async def _run():
            info = await _create_version(
                session_cm, uuid.uuid4(), DocumentProcessingStatus.PARSED
            )
            sf = _get_session_factory()
            processor = JobProcessor(sf)

            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = QueuedJob(
                job_id=str(run_id),
                payload={
                    "document_version_id": str(info["version_id"]),
                    "document_id": str(info["doc_id"]),
                    "organization_id": str(info["org_id"]),
                    "version_number": info["version_number"],
                    "stage": "parse",
                    "run_id": str(run_id),
                    "attempt": 1,
                },
                attempt=1,
                queue=DEFAULT_QUEUE,
            )
            # Should not raise — version is already PARSED
            await processor.process(job)

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Worker run_once tests
# ---------------------------------------------------------------------------


class TestWorkerRunOnce:
    """Tests for Worker.run_once with FakeQueueAdapter."""

    def test_run_once_processes_queued_job(self, session_cm) -> None:
        """Worker picks up a queued job and transitions version to PARSED."""

        async def _run():
            info = await _create_version(
                session_cm, uuid.uuid4(), DocumentProcessingStatus.QUEUED
            )
            queue = FakeQueueAdapter()
            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )

            msg = QueueMessage(
                document_version_id=str(info["version_id"]),
                document_id=str(info["doc_id"]),
                organization_id=str(info["org_id"]),
                version_number=info["version_number"],
                stage="parse",
                run_id=str(run_id),
                attempt=1,
            )
            await queue.enqueue(DEFAULT_QUEUE, str(run_id), msg)

            sf = _get_session_factory()
            # Use FakeParserAdapter + FakeStorageAdapter with the PDF bytes.
            storage = FakeStorageAdapter()
            storage._store[info["storage_key"]] = info["pdf_bytes"]
            storage._meta[info["storage_key"]] = {
                "content_type": "application/pdf",
                "content_length": len(info["pdf_bytes"]),
                "etag": "test-etag",
                "stored_at": time.time(),
            }
            worker = Worker(
                queue=queue,
                session_factory=sf,  # type: ignore[arg-type]
                processor=JobProcessor(
                    sf,
                    parser=FakeParserAdapter(
                        pages=[
                            PageResult(
                                page_number=1,
                                text="test page text",
                                text_length=13,
                                ocr_needed=False,
                                warnings=[],
                                error=None,
                            )
                        ]
                    ),
                    storage=storage,
                ),
                max_concurrency=1,
            )
            processed = await worker.run_once()
            assert processed == 1

            # Verify the version is now PARSED
            async with sf() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == info["version_id"]
                    )
                )
                updated = result.scalar_one()
                assert updated.processing_status == DocumentProcessingStatus.PARSED
                assert updated.parser_name == "fake"

        asyncio.run(_run())

    def test_run_once_empty_queue(self) -> None:
        """Worker.run_once with an empty queue returns 0."""
        sf = _get_session_factory()

        async def _run():
            worker = Worker(
                queue=FakeQueueAdapter(),
                session_factory=sf,  # type: ignore[arg-type]
                max_concurrency=4,
            )
            processed = await worker.run_once()
            assert processed == 0

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Integration: full upload → queue → worker → PARSED flow
# ---------------------------------------------------------------------------


class TestFullProcessingFlow:
    """End-to-end: upload → enqueue → worker → PARSED."""

    def test_upload_then_worker_parses(self, session_cm) -> None:
        fake_queue = FakeQueueAdapter()
        shared_storage = FakeStorageAdapter()
        app.dependency_overrides[get_storage_dep] = lambda: shared_storage
        app.dependency_overrides[get_scanner_dep] = lambda: FakeScanner()
        app.dependency_overrides[get_queue_adapter_dep] = lambda: fake_queue

        try:
            async def _setup_and_upload():
                info = await _create_org_project(session_cm)
                headers = _headers(info["user_id"], info["org_id"])

                client = TestClient(app)
                r = client.post(
                    f"/projects/{info['project_id']}/upload",
                    files={"file": ("tender.pdf", _make_pdf(), "application/pdf")},
                    headers=headers,
                )
                assert r.status_code == 201, r.text
                return info

            info = asyncio.run(_setup_and_upload())

            # Verify the version is QUEUED via API
            async def _check_queued():
                sf = _get_session_factory()
                async with sf() as session:
                    result = await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id.in_(
                                select(TenderDocument.id).where(
                                    TenderDocument.project_id == info["project_id"]
                                )
                            )
                        )
                    )
                    versions = list(result.scalars().all())
                    assert len(versions) >= 1
                    latest = versions[-1]
                    assert latest.processing_status == DocumentProcessingStatus.QUEUED

            asyncio.run(_check_queued())

            # Run the worker to process the queued job
            async def _run_worker():
                sf = _get_session_factory()
                worker = Worker(
                    queue=fake_queue,
                    session_factory=sf,  # type: ignore[arg-type]
                    processor=JobProcessor(
                        sf,
                        parser=FakeParserAdapter(
                            pages=[
                                PageResult(
                                    page_number=1,
                                    text="page one text",
                                    text_length=15,
                                    ocr_needed=False,
                                    warnings=[],
                                    error=None,
                                )
                            ]
                        ),
                        storage=shared_storage,
                    ),
                    max_concurrency=1,
                )
                processed = await worker.run_once()
                assert processed >= 1

            asyncio.run(_run_worker())

            # Verify the version is now PARSED
            async def _check_parsed():
                sf = _get_session_factory()
                async with sf() as session:
                    result = await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id.in_(
                                select(TenderDocument.id).where(
                                    TenderDocument.project_id == info["project_id"]
                                )
                            )
                        )
                    )
                    versions = list(result.scalars().all())
                    assert len(versions) >= 1
                    latest = versions[-1]
                    assert latest.processing_status == DocumentProcessingStatus.PARSED
                    assert latest.parser_name == "fake"

            asyncio.run(_check_parsed())

        finally:
            app.dependency_overrides.clear()

    def test_upload_extracts_only_technical_section_and_exports_blank_sheet(
        self, session_cm
    ) -> None:
        """Exercise upload -> worker extraction -> source-bounded sheet export."""

        class CapturingFake(FakeLlmAdapter):
            def __init__(self) -> None:
                super().__init__(
                    [
                        ExtractionResponse(
                            candidates=[
                                RequirementCandidate(
                                    normalized_text="Hydraulic test capacity: 300 kN.",
                                    raw_source="Hydraulic test capacity: 300 kN.",
                                    requirement_type=RequirementType.OBLIGATION,
                                    uncertainty=UncertaintyLevel.CONFIRMED,
                                    clause_section=None,
                                    group_hint=None,
                                )
                            ]
                        )
                    ]
                )
                self.windows: list[str] = []

            async def extract(self, **kwargs):  # type: ignore[no-untyped-def]
                self.windows.append(kwargs["user_text"])
                return await super().extract(**kwargs)

        fake_queue = FakeQueueAdapter()
        shared_storage = FakeStorageAdapter()
        app.dependency_overrides[get_storage_dep] = lambda: shared_storage
        app.dependency_overrides[get_scanner_dep] = lambda: FakeScanner()
        app.dependency_overrides[get_queue_adapter_dep] = lambda: fake_queue
        try:
            async def _setup_and_upload():
                info = await _create_org_project(session_cm)
                response = TestClient(app).post(
                    f"/projects/{info['project_id']}/upload",
                    files={"file": ("tender.pdf", _make_pdf(), "application/pdf")},
                    headers=_headers(info["user_id"], info["org_id"]),
                )
                assert response.status_code == 201, response.text
                return info

            info = asyncio.run(_setup_and_upload())
            technical_text = (
                "SECTION V / Technical Specification\n"
                "S.No. | Technical Specification\n"
                "Hydraulic test capacity: 300 kN.\n"
                "SECTION VI / General Terms and Conditions\n"
                "The bidder shall submit audited financial statements."
            )
            llm = CapturingFake()

            async def _run_worker() -> None:
                sf = _get_session_factory()
                worker = Worker(
                    queue=fake_queue,
                    session_factory=sf,  # type: ignore[arg-type]
                    processor=JobProcessor(
                        sf,
                        parser=FakeParserAdapter(
                            pages=[
                                PageResult(
                                    page_number=1,
                                    text=technical_text,
                                    text_length=len(technical_text),
                                    ocr_needed=False,
                                    warnings=[],
                                    error=None,
                                )
                            ]
                        ),
                        storage=shared_storage,
                        llm=llm,
                    ),
                    max_concurrency=1,
                )
                assert await worker.run_once() >= 1

            asyncio.run(_run_worker())
            assert len(llm.windows) == 1
            assert "Hydraulic test capacity: 300 kN." in llm.windows[0]
            assert "audited financial statements" not in llm.windows[0]

            async def _export_and_assert() -> None:
                sf = _get_session_factory()
                async with sf() as session:
                    version = (
                        await session.execute(
                            select(DocumentVersion).where(
                                DocumentVersion.document_id.in_(
                                    select(TenderDocument.id).where(
                                        TenderDocument.project_id == info["project_id"]
                                    )
                                )
                            )
                        )
                    ).scalar_one()
                    rows = await project_matrix_rows(session, version.id)
                    assert len(rows) == 1
                    assert rows[0].tender_requirement == "Hydraulic test capacity: 300 kN."
                    document = build_vendor_response_docx(rows)
                    exported = DocxDocument(BytesIO(document))
                    assert len(exported.tables) == 1
                    table = exported.tables[0]
                    assert [cell.text for cell in table.rows[0].cells] == [
                        "S.No.",
                        "Technical Specification",
                        "Compliance (Yes / No)",
                        "Any Deviation",
                    ]
                    assert [cell.text for cell in table.rows[1].cells] == [
                        "1)",
                        "Hydraulic test capacity: 300 kN.",
                        "",
                        "",
                    ]
                    assert len(exported.paragraphs) == 1
                    assert exported.paragraphs[0].text == "Technical Specification Sheet"

            asyncio.run(_export_and_assert())
        finally:
            app.dependency_overrides.clear()

    def test_oem_upload_then_worker_creates_searchable_segments(self, session_cm) -> None:
        """Real OEM upload -> queue -> worker -> searchable source segments."""
        fake_queue = FakeQueueAdapter()
        shared_storage = FakeStorageAdapter()
        app.dependency_overrides[get_storage_dep] = lambda: shared_storage
        app.dependency_overrides[get_scanner_dep] = lambda: FakeScanner()
        app.dependency_overrides[get_queue_adapter_dep] = lambda: fake_queue

        try:
            info = asyncio.run(_create_org_project(session_cm, status="tender_uploaded"))
            headers = _headers(info["user_id"], info["org_id"])

            upload = TestClient(app).post(
                f"/projects/{info['project_id']}/oem-documents/upload",
                files={"file": ("datasheet.pdf", _make_pdf(), "application/pdf")},
                data={
                    "document_type": "datasheet",
                    "vendor_name": "Acme Instruments",
                    "product_name": "Model X",
                },
                headers=headers,
            )
            assert upload.status_code == 201, upload.text
            assert upload.json()["processing_status"] == "uploaded"

            async def _run_worker() -> None:
                sf = _get_session_factory()
                worker = Worker(
                    queue=fake_queue,
                    session_factory=sf,  # type: ignore[arg-type]
                    processor=JobProcessor(
                        sf,
                        parser=FakeParserAdapter(
                            pages=[
                                PageResult(
                                    page_number=1,
                                    text="Positioning resolution is 1 um.",
                                    text_length=31,
                                    ocr_needed=False,
                                    warnings=[],
                                    error=None,
                                )
                            ]
                        ),
                        storage=shared_storage,
                    ),
                    max_concurrency=1,
                )
                assert await worker.run_once() == 1

            asyncio.run(_run_worker())

            async def _verify() -> None:
                sf = _get_session_factory()
                async with sf() as session:
                    version_result = await session.execute(
                        select(OemDocumentVersion)
                        .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
                        .where(OemDocument.project_id == info["project_id"])
                    )
                    version = version_result.scalar_one()
                    assert version.processing_status == DocumentProcessingStatus.PARSED
                    assert version.parser_name == "fake"
                    assert version.parser_version == "test"

                    segment_result = await session.execute(
                        select(OemTextSegment).where(
                            OemTextSegment.oem_document_version_id == version.id
                        )
                    )
                    segments = list(segment_result.scalars().all())
                    assert len(segments) == 1
                    assert segments[0].page_number == 1
                    assert segments[0].text == "Positioning resolution is 1 um."

            asyncio.run(_verify())
        finally:
            app.dependency_overrides.clear()

