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
import uuid

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    RunStatus,
    TenderDocument,
    User,
)
from tender_compliance_api.main import app
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
) -> dict:
    """Create org + user + membership + project + document + version."""
    info = await _create_org_project(session_cm)
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    async with session_cm() as session:
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
            stored_object_id=uuid.uuid4(),
            sha256="abc123",
            mime_type="application/pdf",
            size_bytes=100,
            processing_status=status,
        )
        session.add(version)
        await session.commit()
    info.update(
        doc_id=doc_id,
        version_id=version_id,
        version_number=1,
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
    """Tests for the worker's JobProcessor (CP18 placeholder pass)."""

    def test_process_transitions_to_parsed(self, session_cm) -> None:
        """Processing a QUEUED version transitions it to PARSED."""

        async def _run():
            info = await _create_version(
                session_cm, uuid.uuid4(), DocumentProcessingStatus.QUEUED
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
                assert updated.parser_name == "tender-compliance-engine"

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
            worker = Worker(
                queue=queue,
                session_factory=sf,  # type: ignore[arg-type]
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
        app.dependency_overrides[get_storage_dep] = lambda: FakeStorageAdapter()
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
                    assert latest.parser_name == "tender-compliance-engine"

            asyncio.run(_check_parsed())

        finally:
            app.dependency_overrides.clear()
