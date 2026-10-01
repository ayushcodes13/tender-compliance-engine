"""Tests for the document-processing state machine (CP17).

Covers:
- DocumentVersion state transitions (UPLOADED → QUEUED → PROCESSING →
  PARSED / PARTIAL / FAILED) and guard against invalid transitions.
- ProcessingRun lifecycle (begin, complete, fail).
- Reconciliation: version status derived from run outcomes.
- GET /projects/{id}/documents/{doc_id}/versions/{v} endpoint.
- GET /projects/{id}/documents/{doc_id}/versions/{v}/runs endpoint.
- Cross-tenant denial on document endpoints.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    ProjectStatus,
    RunStatus,
    TenderDocument,
    User,
)
from tender_compliance_api.document import DocumentNotFoundError, DocumentService
from tender_compliance_api.document.service import TransitionError, _is_valid_transition
from tender_compliance_api.main import app
from tender_compliance_api.queue import DEFAULT_QUEUE, FakeQueueAdapter
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.routes.uploads import (
    get_queue_adapter as get_queue_adapter_dep,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _mk_auth(org_id: uuid.UUID, user_id: uuid.UUID):
    """Build a minimal AuthContext-like object for service tests."""
    from types import SimpleNamespace

    return SimpleNamespace(organization_id=org_id, actor_id=user_id)


def _build_org_project(session_cm):
    """Set up org + user + membership + project; return (user_id, org_id, project_id)."""

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP17 Test Org"))
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
                    name="CP17 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _create_doc_version(session_cm, project_id: uuid.UUID) -> tuple[uuid.UUID, int]:
    """Create a TenderDocument + DocumentVersion (status=UPLOADED).

    Returns (document_id, version_number).
    """

    async def _create():
        async with session_cm() as session:
            doc = TenderDocument(
                project_id=project_id,
                display_name="tender.pdf",
                document_type="tender",
            )
            session.add(doc)
            await session.flush()
            version = DocumentVersion(
                document_id=doc.id,
                version_number=1,
                stored_object_id=uuid.uuid4(),
                sha256="abc123",
                mime_type="application/pdf",
                size_bytes=1024,
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
            session.add(version)
            await session.commit()
            return doc.id, version.version_number

    return asyncio.run(_create())


# ---------------------------------------------------------------------------
# State-machine transition guards
# ---------------------------------------------------------------------------


class TestStateMachineGuards:
    """Test the _is_valid_transition function directly."""

    def test_uploaded_to_queued(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.UPLOADED,
            DocumentProcessingStatus.QUEUED,
        )

    def test_queued_to_processing(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.QUEUED,
            DocumentProcessingStatus.PROCESSING,
        )

    def test_processing_to_parsed(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.PROCESSING,
            DocumentProcessingStatus.PARSED,
        )

    def test_processing_to_partial(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.PROCESSING,
            DocumentProcessingStatus.PARTIAL,
        )

    def test_processing_to_failed(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.PROCESSING,
            DocumentProcessingStatus.FAILED,
        )

    def test_partial_to_queued(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.PARTIAL,
            DocumentProcessingStatus.QUEUED,
        )

    def test_failed_to_queued(self):
        assert _is_valid_transition(
            DocumentProcessingStatus.FAILED,
            DocumentProcessingStatus.QUEUED,
        )

    def test_uploaded_to_processing_invalid(self):
        """Must go through QUEUED first."""
        assert not _is_valid_transition(
            DocumentProcessingStatus.UPLOADED,
            DocumentProcessingStatus.PROCESSING,
        )

    def test_parsed_to_processing_invalid(self):
        """PARSED is terminal — cannot go back to PROCESSING."""
        assert not _is_valid_transition(
            DocumentProcessingStatus.PARSED,
            DocumentProcessingStatus.PROCESSING,
        )

    def test_uploaded_to_parsed_invalid(self):
        """Cannot skip directly to PARSED."""
        assert not _is_valid_transition(
            DocumentProcessingStatus.UPLOADED,
            DocumentProcessingStatus.PARSED,
        )


# ---------------------------------------------------------------------------
# DocumentVersion status field accepts new enum values
# ---------------------------------------------------------------------------


class TestDocumentVersionStatuses:
    def test_new_enum_values_persist(self, session_cm) -> None:
        """QUEUED and PARTIAL are accepted and round-trip through SQLite."""

        async def _check() -> None:
            async with session_cm() as session:
                org_id = uuid.uuid4()
                user_id = uuid.uuid4()
                project_id = uuid.uuid4()
                doc_id = uuid.uuid4()
                ver_id = uuid.uuid4()
                session.add(
                    Organization(id=org_id, name="Enum Org")
                )
                session.add(
                    User(
                        id=user_id,
                        auth_provider="dev",
                        auth_provider_user_id=str(user_id),
                    )
                )
                session.add(
                    Membership(
                        organization_id=org_id, user_id=user_id, role="owner"
                    )
                )
                session.add(
                    Project(
                        id=project_id,
                        organization_id=org_id,
                        name="Enum Project",
                        status=ProjectStatus.DRAFT,
                        created_by=user_id,
                    )
                )
                session.add(
                    TenderDocument(
                        id=doc_id,
                        project_id=project_id,
                        display_name="test.pdf",
                        document_type="tender",
                    )
                )
                session.add(
                    DocumentVersion(
                        id=ver_id,
                        document_id=doc_id,
                        version_number=1,
                        stored_object_id=uuid.uuid4(),
                        sha256="deadbeef",
                        mime_type="application/pdf",
                        size_bytes=100,
                        processing_status=DocumentProcessingStatus.QUEUED,
                    )
                )
                await session.commit()

                result = await session.execute(
                    select(DocumentVersion).where(DocumentVersion.id == ver_id)
                )
                ver = result.scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.QUEUED

                ver.processing_status = DocumentProcessingStatus.PARTIAL
                await session.commit()

                result = await session.execute(
                    select(DocumentVersion).where(DocumentVersion.id == ver_id)
                )
                ver = result.scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.PARTIAL

        asyncio.run(_check())


# ---------------------------------------------------------------------------
# DocumentService transition tests
# ---------------------------------------------------------------------------


class TestDocumentServiceTransitions:
    def test_transition_uploaded_to_queued(self, session_cm) -> None:
        """DocumentService.transition_to UPLOADED → QUEUED succeeds."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                version = await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.QUEUED,
                )
                assert version.processing_status == DocumentProcessingStatus.QUEUED

        asyncio.run(_run())

    def test_transition_invalid_blocked(self, session_cm) -> None:
        """Direct UPLOADED → PROCESSING is blocked by the state machine."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                with pytest.raises(TransitionError):
                    await svc.transition_to(
                        auth, doc_id, ver_num,
                        DocumentProcessingStatus.PROCESSING,
                    )

        asyncio.run(_run())

    def test_transition_terminal_parsed_blocked(self, session_cm) -> None:
        """Cannot transition from PARSED back to PROCESSING."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                # Set to PARSED manually
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                ver = result.scalar_one()
                ver.processing_status = DocumentProcessingStatus.PARSED
                await session.flush()

                with pytest.raises(TransitionError):
                    await svc.transition_to(
                        auth, doc_id, ver_num,
                        DocumentProcessingStatus.PROCESSING,
                    )

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# ProcessingRun lifecycle + reconciliation
# ---------------------------------------------------------------------------


class TestProcessingRunLifecycle:
    def test_begin_and_complete_run_all_stages(self, session_cm) -> None:
        """All four stages COMPLETED → version transitions to PARSED."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.QUEUED,
                )
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.PROCESSING,
                )

                run_id = uuid.uuid4()
                for stage in [
                    ProcessingStage.PARSE,
                    ProcessingStage.OCR,
                    ProcessingStage.CLEANUP,
                    ProcessingStage.EXTRACT,
                ]:
                    await svc.begin_run(auth, doc_id, ver_num, stage, run_id)
                    await svc.complete_run(
                        auth, doc_id, ver_num, stage, run_id,
                    )

                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                ver = result.scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.PARSED

                runs = await svc.get_runs(auth, doc_id, ver_num)
                assert len(runs) == 4

        asyncio.run(_run())

    def test_partial_when_some_stages_fail(self, session_cm) -> None:
        """One stage fails permanently (5 attempts) but others complete → PARTIAL."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.QUEUED,
                )
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.PROCESSING,
                )

                # PARSE succeeds
                run_id = uuid.uuid4()
                await svc.begin_run(auth, doc_id, ver_num, ProcessingStage.PARSE, run_id)
                await svc.complete_run(auth, doc_id, ver_num, ProcessingStage.PARSE, run_id)

                # OCR fails 5 times (max retries)
                for _attempt in range(5):
                    fail_id = uuid.uuid4()
                    await svc.begin_run(
                        auth, doc_id, ver_num, ProcessingStage.OCR, fail_id
                    )
                    await svc.complete_run(
                        auth, doc_id, ver_num, ProcessingStage.OCR, fail_id,
                        error_type="ocr_error",
                        error_message="OCR failed",
                    )

                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                ver = result.scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.PARTIAL

        asyncio.run(_run())

    def test_failed_when_all_stages_exhausted(self, session_cm) -> None:
        """All stages fail permanently → FAILED."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.QUEUED,
                )
                await svc.transition_to(
                    auth, doc_id, ver_num,
                    DocumentProcessingStatus.PROCESSING,
                )

                for stage in [
                    ProcessingStage.PARSE,
                    ProcessingStage.OCR,
                    ProcessingStage.CLEANUP,
                    ProcessingStage.EXTRACT,
                ]:
                    for _attempt in range(5):
                        fail_id = uuid.uuid4()
                        await svc.begin_run(
                            auth, doc_id, ver_num, stage, fail_id
                        )
                        await svc.complete_run(
                            auth, doc_id, ver_num, stage, fail_id,
                            error_type="stage_error",
                            error_message="stage failed",
                        )

                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                ver = result.scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.FAILED

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDocumentVersionApi:
    def test_get_document_version(self, session_cm) -> None:
        """GET /projects/{id}/documents/{doc_id}/versions/{v} returns version info."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver_num}",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["document_id"] == str(doc_id)
        assert body["version_number"] == ver_num
        assert body["display_name"] == "tender.pdf"
        assert body["processing_status"] == "uploaded"
        assert body["size_bytes"] == 1024

    def test_get_version_not_found(self, session_cm) -> None:
        """GET a non-existent version returns 404."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id = uuid.uuid4()
        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/1",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 404

    def test_get_version_cross_tenant_denied(self, session_cm) -> None:
        """Cross-tenant access to a document version returns 404."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        # Other org
        other_user = uuid.uuid4()
        other_org = uuid.uuid4()

        async def _setup_other() -> None:
            async with session_cm() as session:
                session.add(
                    Organization(id=other_org, name="Other Org")
                )
                session.add(
                    User(
                        id=other_user,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver_num}",
            headers=_headers(other_user, other_org),
        )
        assert response.status_code == 404

    def test_get_version_wrong_project(self, session_cm) -> None:
        """Document exists but belongs to a different project → 404."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        wrong_project = uuid.uuid4()
        response = client.get(
            f"/projects/{wrong_project}/documents/{doc_id}/versions/{ver_num}",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 404


class TestProcessingRunsApi:
    def test_list_runs_for_version(self, session_cm) -> None:
        """GET .../runs returns processing runs for a version."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        async def _create_run() -> None:
            async with session_cm() as session:
                ver_result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                ver = ver_result.scalar_one()
                run = ProcessingRun(
                    document_version_id=ver.id,
                    run_id=uuid.uuid4(),
                    attempt=1,
                    stage=ProcessingStage.PARSE,
                    status=RunStatus.COMPLETED,
                )
                session.add(run)
                await session.commit()

        asyncio.run(_create_run())

        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/"
            f"{ver_num}/runs",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 200, response.text
        runs = response.json()
        assert len(runs) == 1
        assert runs[0]["stage"] == "parse"
        assert runs[0]["status"] == "completed"
        assert runs[0]["attempt"] == 1
        assert runs[0]["error_type"] is None

    def test_list_runs_cross_tenant_denied(self, session_cm) -> None:
        """Cross-tenant access to runs returns 404."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)

        other_user = uuid.uuid4()
        other_org = uuid.uuid4()

        async def _setup_other() -> None:
            async with session_cm() as session:
                session.add(
                    Organization(id=other_org, name="Other Org")
                )
                session.add(
                    User(
                        id=other_user,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/"
            f"{ver_num}/runs",
            headers=_headers(other_user, other_org),
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Retry action (CP24): DocumentService.requeue_version
# ---------------------------------------------------------------------------


def _set_version_status(
    session_cm, doc_id: uuid.UUID, status: DocumentProcessingStatus
) -> uuid.UUID:
    """Force a version's processing_status (bypassing the state machine).

    Returns the version's uuid.  Used to set up terminal/partial starting
    states that the happy-path upload flow never produces.
    """

    async def _go() -> uuid.UUID:
        async with session_cm() as session:
            ver = (
                await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
            ).scalar_one()
            ver.processing_status = status
            await session.commit()
            return ver.id

    return asyncio.run(_go())


class TestRetryVersion:
    """``DocumentService.requeue_version``: FAILED/PARTIAL -> QUEUED."""

    def test_requeue_failed_to_queued(self, session_cm) -> None:
        """A FAILED version is transitioned back to QUEUED and a run_id is
        returned deterministically keyed on the version + PARSE stage."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        ver_id = _set_version_status(
            session_cm, doc_id, DocumentProcessingStatus.FAILED
        )

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                run_id = await svc.requeue_version(auth, doc_id, ver_num)
                assert run_id == make_job_id(
                    str(ver_id), ProcessingStage.PARSE.value
                )
                ver = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.QUEUED

        asyncio.run(_run())

    def test_requeue_partial_to_queued(self, session_cm) -> None:
        """A PARTIAL version (some pages OCR-failed but not dead) is retryable."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        _set_version_status(session_cm, doc_id, DocumentProcessingStatus.PARTIAL)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                run_id = await svc.requeue_version(auth, doc_id, ver_num)
                ver = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.QUEUED
                assert run_id == make_job_id(
                    str(ver.id), ProcessingStage.PARSE.value
                )

        asyncio.run(_run())

    def test_requeue_parsed_rejected(self, session_cm) -> None:
        """PARSED is terminal — retrying it is a 409, never a silent re-run."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        _set_version_status(session_cm, doc_id, DocumentProcessingStatus.PARSED)

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                with pytest.raises(TransitionError):
                    await svc.requeue_version(auth, doc_id, ver_num)
                ver = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.PARSED

        asyncio.run(_run())

    def test_requeue_is_idempotent(self, session_cm) -> None:
        """Re-calling requeue on an already-QUEUED version returns the same
        run_id and does not enqueue a second distinct job / transition."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        ver_id = _set_version_status(
            session_cm, doc_id, DocumentProcessingStatus.FAILED
        )

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                first = await svc.requeue_version(auth, doc_id, ver_num)
                second = await svc.requeue_version(auth, doc_id, ver_num)
                assert first == second
                assert first == make_job_id(
                    str(ver_id), ProcessingStage.PARSE.value
                )
                ver = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.QUEUED

        asyncio.run(_run())

    def test_requeue_cross_tenant_denied(self, session_cm) -> None:
        """A user from another org cannot requeue a version they can't see."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        _set_version_status(session_cm, doc_id, DocumentProcessingStatus.FAILED)

        other_user = uuid.uuid4()
        other_org = uuid.uuid4()

        async def _setup_other() -> None:
            async with session_cm() as session:
                session.add(Organization(id=other_org, name="Other Org"))
                session.add(
                    User(
                        id=other_user,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(
                        organization_id=other_org, user_id=other_user, role="owner"
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        async def _run() -> None:
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(other_org, other_user)
                with pytest.raises(DocumentNotFoundError):
                    await svc.requeue_version(auth, doc_id, ver_num)

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Retry API endpoint (CP24)
# ---------------------------------------------------------------------------


class TestRetryProcessingApi:
    """``POST .../versions/{v}/retry`` endpoint."""

    def test_retry_failed_version(
        self, session_cm
    ) -> None:
        """Retrying a FAILED version returns 200, queues a deterministic job,
        and transitions the version to QUEUED."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        ver_id = _set_version_status(
            session_cm, doc_id, DocumentProcessingStatus.FAILED
        )

        fake_queue = FakeQueueAdapter()
        app.dependency_overrides[get_queue_adapter_dep] = lambda: fake_queue
        try:
            response = client.post(
                f"/projects/{project_id}/documents/{doc_id}/versions/"
                f"{ver_num}/retry",
                headers=_headers(user_id, org_id),
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200, response.text
        body = response.json()
        expected_run_id = str(
            make_job_id(str(ver_id), ProcessingStage.PARSE.value)
        )
        assert body["run_id"] == expected_run_id
        assert body["status"] == DocumentProcessingStatus.QUEUED.value

        # Version was transitioned to QUEUED.
        async def _check_db() -> None:
            async with session_cm() as session:
                ver = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalar_one()
                assert ver.processing_status == DocumentProcessingStatus.QUEUED

        asyncio.run(_check_db())

        # One deterministic job enqueued with a fresh worker attempt.
        async def _check_queue() -> None:
            assert await fake_queue.size(DEFAULT_QUEUE) == 1
            job = await fake_queue.dequeue(DEFAULT_QUEUE)
            assert job is not None
            assert job.job_id == expected_run_id
            assert job.payload["stage"] == ProcessingStage.PARSE.value
            assert job.payload["attempt"] == 1
            assert job.payload["document_version_id"] == str(ver_id)
            assert job.payload["document_id"] == str(doc_id)

        asyncio.run(_check_queue())

    def test_retry_parsed_returns_409(self, session_cm) -> None:
        """A PARSED (terminal) version cannot be retried — 409."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        _set_version_status(session_cm, doc_id, DocumentProcessingStatus.PARSED)

        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/"
            f"{ver_num}/retry",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 409

    def test_retry_not_found_returns_404(self, session_cm) -> None:
        """Retrying a non-existent version is 404 (no version enumeration)."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        response = client.post(
            f"/projects/{project_id}/documents/{uuid.uuid4()}/versions/1/retry",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 404

    def test_retry_wrong_project_returns_404(self, session_cm) -> None:
        """Document exists but belongs to a different project -> 404."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        _set_version_status(session_cm, doc_id, DocumentProcessingStatus.FAILED)

        response = client.post(
            f"/projects/{uuid.uuid4()}/documents/{doc_id}/versions/"
            f"{ver_num}/retry",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 404

    def test_retry_is_idempotent_at_api(self, session_cm) -> None:
        """Two consecutive retries return the same run_id and enqueue one job."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        doc_id, ver_num = _create_doc_version(session_cm, project_id)
        ver_id = _set_version_status(
            session_cm, doc_id, DocumentProcessingStatus.FAILED
        )

        fake_queue = FakeQueueAdapter()
        app.dependency_overrides[get_queue_adapter_dep] = lambda: fake_queue
        try:
            first = client.post(
                f"/projects/{project_id}/documents/{doc_id}/versions/"
                f"{ver_num}/retry",
                headers=_headers(user_id, org_id),
            )
            second = client.post(
                f"/projects/{project_id}/documents/{doc_id}/versions/"
                f"{ver_num}/retry",
                headers=_headers(user_id, org_id),
            )
        finally:
            app.dependency_overrides.clear()

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["run_id"] == second.json()["run_id"]
        expected_run_id = str(
            make_job_id(str(ver_id), ProcessingStage.PARSE.value)
        )
        assert first.json()["run_id"] == expected_run_id

        async def _check_queue() -> None:
            # Idempotent enqueue: still exactly one job.
            assert await fake_queue.size(DEFAULT_QUEUE) == 1

        asyncio.run(_check_queue())
