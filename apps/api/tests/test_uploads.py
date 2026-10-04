"""API-level tests for the document upload route (CP13, versioning in CP15).

Exercises the full HTTP request/response cycle: validation, malware
scanning, storage, DB persistence, document/version creation, project-
status transition, and audit logging.  Uses :class:`FakeStorageAdapter`
and :class:`FakeScanner` via FastAPI dependency overrides.
"""

import asyncio
import io
import uuid

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.main import app
from tender_compliance_api.queue.fake import FakeQueueAdapter
from tender_compliance_api.routes.uploads import get_queue_adapter, get_scanner, get_storage_adapter
from tender_compliance_api.scan.adapter import MalwareScannerUnavailableError
from tender_compliance_api.scan.fake import (
    TEST_INFECTED_SIGNATURE,
    FakeScanner,
)
from tender_compliance_api.storage.fake import FakeStorageAdapter

# Override storage, scanner, and queue dependencies for all tests in this module.
app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()
app.dependency_overrides[get_scanner] = lambda: FakeScanner()
app.dependency_overrides[get_queue_adapter] = lambda: FakeQueueAdapter()

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _make_valid_pdf() -> bytes:
    """Create a minimal valid single-page PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_valid_pdf_different() -> bytes:
    """Create a different valid PDF (two pages)."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_protected_pdf(password: str = "secret") -> bytes:
    """Create a password-protected PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_auth_headers(session_cm) -> tuple[dict[str, str], uuid.UUID]:
    """Set up org + user + membership + project; return (headers, proj_id)."""

    async def _setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="Upload Test Org"))
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
                    name="Upload Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    user_id, org_id, project_id = asyncio.run(_setup())
    return _headers(user_id, org_id), project_id


# ---------------------------------------------------------------------------
# Valid uploads
# ---------------------------------------------------------------------------


class TestUploadValid:
    def test_valid_pdf_upload(self, session_cm) -> None:
        """A valid PDF is accepted, stored, and project transitions to
        TENDER_UPLOADED.  A TenderDocument + DocumentVersion are created."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["filename"] == "tender.pdf"
        assert body["content_type"] == "application/pdf"
        assert body["content_length"] == len(pdf_data)
        assert "checksum_sha256" in body
        assert body["project_status"] == "tender_uploaded"

        # Document/version fields (CP14/CP15)
        assert "document_id" in body
        assert body["version_number"] == 1
        doc_id = uuid.UUID(body["document_id"])

        # Verify StoredObject + TenderDocument + DocumentVersion persisted.
        async def _verify() -> None:
            async with session_cm() as session:
                objs = (
                    await session.execute(
                        select(StoredObject).where(
                            StoredObject.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(objs) == 1
                assert objs[0].checksum_sha256 == body["checksum_sha256"]

                docs = (
                    await session.execute(
                        select(TenderDocument).where(
                            TenderDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(docs) == 1

                versions = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalars().all()
                assert len(versions) == 1
                assert versions[0].version_number == 1
                assert versions[0].stored_object_id == objs[0].id
                assert versions[0].sha256 == body["checksum_sha256"]

        asyncio.run(_verify())

    def test_list_documents_after_upload(self, session_cm) -> None:
        """GET /projects/{id}/documents returns uploaded document versions."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        # Upload one document
        r1 = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r1.status_code == 201, r1.text

        # Upload same content again (v2)
        r2 = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r2.status_code == 201, r2.text

        # Fetch the document list
        r_list = client.get(
            f"/projects/{project_id}/documents",
            headers=headers,
        )
        assert r_list.status_code == 200, r_list.text
        items = r_list.json()
        assert len(items) == 2
        assert items[0]["version_number"] == 1
        assert items[1]["version_number"] == 2
        assert items[0]["display_name"] == "tender.pdf"
        assert items[0]["size_bytes"] == len(pdf_data)
        assert items[0]["processing_status"] == "queued"

    def test_list_documents_cross_tenant_denied(self, session_cm) -> None:
        """Cross-tenant users cannot list another org's documents."""
        headers_a, project_id = _build_auth_headers(session_cm)

        # Upload to org A's project
        r1 = client.post(
            f"/projects/{project_id}/upload",
            files={
                "file": ("tender.pdf", _make_valid_pdf(), "application/pdf")
            },
            headers=headers_a,
        )
        assert r1.status_code == 201, r1.text

        # Org B tries to list
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
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        r_list = client.get(
            f"/projects/{project_id}/documents",
            headers=_headers(other_user, other_org),
        )
        assert r_list.status_code == 404


# ---------------------------------------------------------------------------
# Version semantics
# ---------------------------------------------------------------------------


class TestUploadVersioning:
    def test_duplicate_content_reuses_stored_object(self, session_cm) -> None:
        """Uploading identical bytes a second time reuses the StoredObject
        but creates a new DocumentVersion (v2) on the same TenderDocument."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        # First upload — creates document + v1
        r1 = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r1.status_code == 201, r1.text
        b1 = r1.json()
        doc_id = uuid.UUID(b1["document_id"])
        so_id_1 = uuid.UUID(b1["stored_object_id"])
        assert b1["version_number"] == 1

        # Second upload — same bytes, new version
        r2 = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r2.status_code == 201, r2.text
        b2 = r2.json()
        assert b2["document_id"] == str(doc_id)  # same document
        assert b2["stored_object_id"] == str(so_id_1)  # bytes reused
        assert b2["version_number"] == 2  # new version

        # Verify exactly one StoredObject and two DocumentVersions
        async def _verify() -> None:
            async with session_cm() as session:
                so_query = (
                    await session.execute(
                        select(StoredObject).where(
                            StoredObject.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(so_query) == 1, "bytes should be reused, not stored twice"

                v_query = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id
                        )
                    )
                ).scalars().all()
                assert len(v_query) == 2
                assert v_query[0].version_number == 1
                assert v_query[1].version_number == 2
                assert v_query[0].stored_object_id == v_query[1].stored_object_id

        asyncio.run(_verify())

    def test_different_content_creates_new_version(self, session_cm) -> None:
        """Uploading different bytes to the same project creates a new
        version (v2) with a new StoredObject."""
        headers, project_id = _build_auth_headers(session_cm)

        r1 = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", _make_valid_pdf(), "application/pdf")},
            headers=headers,
        )
        assert r1.status_code == 201, r1.text
        b1 = r1.json()
        doc_id = uuid.UUID(b1["document_id"])
        so_id_1 = uuid.UUID(b1["stored_object_id"])
        assert b1["version_number"] == 1

        # Second upload — genuinely different valid PDF
        r2 = client.post(
            f"/projects/{project_id}/upload",
            files={
                "file": ("tender_v2.pdf", _make_valid_pdf_different(), "application/pdf"),
            },
            headers=headers,
        )
        assert r2.status_code == 201, r2.text
        b2 = r2.json()
        assert b2["document_id"] == str(doc_id)  # same document
        assert b2["stored_object_id"] != str(so_id_1)  # new bytes
        assert b2["version_number"] == 2  # new version

    def test_upload_durable_after_restart(self, session_cm) -> None:
        """Uploaded documents/versions persist across session boundaries
        (file-based SQLite durability)."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        r = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        doc_id = uuid.UUID(body["document_id"])
        so_id = uuid.UUID(body["stored_object_id"])

        # Second session — data should still be there (same file-based DB)
        async def _verify() -> None:
            async with session_cm() as session:
                so = (
                    await session.execute(
                        select(StoredObject).where(StoredObject.id == so_id)
                    )
                ).scalar_one()
                assert so is not None
                assert so.checksum_sha256 == body["checksum_sha256"]

                doc = (
                    await session.execute(
                        select(TenderDocument).where(TenderDocument.id == doc_id)
                    )
                ).scalar_one()
                assert doc is not None
                assert doc.display_name == "tender.pdf"

                ver = (
                    await session.execute(
                        select(DocumentVersion)
                        .where(DocumentVersion.document_id == doc_id)
                        .order_by(DocumentVersion.version_number)
                    )
                ).scalars().all()
                assert len(ver) == 1
                assert ver[0].version_number == 1
                assert ver[0].stored_object_id == so_id

        asyncio.run(_verify())


# ---------------------------------------------------------------------------
# Rejected uploads
# ---------------------------------------------------------------------------


class TestUploadRejected:
    def test_mime_mismatch_rejected(self, session_cm) -> None:
        """File named .pdf but content lacks the PDF magic bytes."""
        headers, project_id = _build_auth_headers(session_cm)

        response = client.post(
            f"/projects/{project_id}/upload",
            files={
                "file": ("tender.pdf", b"NOT A PDF FILE CONTENTS", "application/pdf")
            },
            headers=headers,
        )

        assert response.status_code == 422
        assert "rejected" in response.json()["detail"].lower()

    def test_wrong_extension_rejected(self, session_cm) -> None:
        """PDF file with a disallowed extension is rejected."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.txt", pdf_data, "text/plain")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "extension" in response.json()["detail"].lower()

    def test_empty_file_rejected(self, session_cm) -> None:
        """Empty uploads are rejected before any processing."""
        headers, project_id = _build_auth_headers(session_cm)

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_protected_pdf_rejected(self, session_cm) -> None:
        """Password-protected PDFs are rejected."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_protected_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("protected.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        detail = response.json()["detail"].lower()
        assert "password" in detail or "protected" in detail

    def test_malware_detected(self, session_cm) -> None:
        """Files containing a malware signature are rejected."""
        headers, project_id = _build_auth_headers(session_cm)

        # Valid PDF with malware test signature appended.
        pdf_data = _make_valid_pdf() + TEST_INFECTED_SIGNATURE

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "malware" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestUploadAuthorization:
    def test_cross_tenant_denied(self, session_cm) -> None:
        """A user from org B cannot upload to a project in org A."""
        headers_a, project_id = _build_auth_headers(session_cm)

        # User from a different org.
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
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        pdf_data = _make_valid_pdf()
        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=_headers(other_user, other_org),
        )

        assert response.status_code == 404


class _UnavailableScanner(FakeScanner):
    async def scan(self, filename: str, data: bytes):
        raise MalwareScannerUnavailableError("scanner offline")


def test_scanner_outage_rejects_tender_upload(session_cm) -> None:
    """A scanner outage is retryable and never accepts an unscanned tender."""
    headers, project_id = _build_auth_headers(session_cm)
    original = app.dependency_overrides[get_scanner]
    app.dependency_overrides[get_scanner] = lambda: _UnavailableScanner()
    try:
        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", _make_valid_pdf(), "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 503
        assert "Upload was not accepted" in response.json()["detail"]

        async def _verify() -> None:
            async with session_cm() as session:
                stored = (
                    await session.execute(
                        select(StoredObject).where(StoredObject.project_id == project_id)
                    )
                ).scalars().all()
                assert stored == []

        asyncio.run(_verify())
    finally:
        app.dependency_overrides[get_scanner] = original
