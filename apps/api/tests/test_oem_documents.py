"""Tests for CP49 — OEM document ingestion and provenance.

Covers:
- OEM document upload via API (validation, storage, versioning, vendor metadata)
- OEM documents are stored separately from tender documents (separate tables)
- Tenant isolation (cross-org access denied)
- Upload rejection (empty file, malware, invalid format)
- Duplicate content reuses StoredObject (deduplication)
- Version sequencing (second upload creates v2)
- OEM document listing (latest version per document)
- Immutability of stored versions (sha256 unchanged)
- Audit trail records upload events with OEM-specific metadata
- Tender/OEM separation: tender upload does not create OEM docs, vice versa
"""

import asyncio
import io
import uuid

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.db.models import (
    AuditLog,
    DocumentProcessingStatus,
    Membership,
    OemDocument,
    OemDocumentType,
    OemDocumentVersion,
    Organization,
    Project,
    ProjectStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.main import app
from tender_compliance_api.queue.fake import FakeQueueAdapter
from tender_compliance_api.routes.uploads import (
    get_queue_adapter,
    get_scanner,
    get_storage_adapter,
)
from tender_compliance_api.scan.adapter import MalwareScannerUnavailableError
from tender_compliance_api.scan.fake import (
    TEST_INFECTED_SIGNATURE,
    FakeScanner,
)
from tender_compliance_api.storage.fake import FakeStorageAdapter

# Override storage, scanner, and queue dependencies for all tests.
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


def _build_auth_headers(session_cm) -> tuple[dict[str, str], uuid.UUID]:
    """Set up org + user + membership + project; return (headers, proj_id)."""

    async def _setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP49 Test Org"))
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
                    name="CP49 Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    user_id, org_id, project_id = asyncio.run(_setup())
    return _headers(user_id, org_id), project_id


class TestOemUpload:
    """OEM document upload via API."""

    def test_valid_oem_upload(self, session_cm) -> None:
        """A valid PDF is accepted as an OEM document.  OemDocument +
        OemDocumentVersion are created and the project is NOT transitioned
        to TENDER_UPLOADED (separate pipeline)."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            data={
                "document_type": "datasheet",
                "vendor_name": "Acme Corp",
                "product_name": "Thermostat X1",
                "product_sku": "TH-X1-2024",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["filename"] == "datasheet.pdf"
        assert body["content_type"] == "application/pdf"
        assert body["content_length"] == len(pdf_data)
        assert body["processing_status"] == "uploaded"
        assert "checksum_sha256" in body
        assert "document_id" in body
        assert body["version_number"] == 1

        # Verify persistence.
        async def _verify() -> None:
            async with session_cm() as session:
                docs = (
                    await session.execute(
                        select(OemDocument).where(
                            OemDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(docs) == 1
                doc = docs[0]
                assert doc.display_name == "datasheet.pdf"
                assert doc.document_type == OemDocumentType.DATASHEET
                assert doc.vendor_name == "Acme Corp"
                assert doc.product_name == "Thermostat X1"
                assert doc.product_sku == "TH-X1-2024"

                versions = (
                    await session.execute(
                        select(OemDocumentVersion).where(
                            OemDocumentVersion.document_id == doc.id
                        )
                    )
                ).scalars().all()
                assert len(versions) == 1
                assert versions[0].version_number == 1
                assert versions[0].sha256 == body["checksum_sha256"]
                # Status transitioned to QUEUED by enqueue (same as tender upload).
                assert (
                    versions[0].processing_status
                    == DocumentProcessingStatus.QUEUED
                )

                # TenderDocument should NOT exist (separate tables).
                tender_docs = (
                    await session.execute(
                        select(TenderDocument).where(
                            TenderDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(tender_docs) == 0

        asyncio.run(_verify())

    def test_vendor_compliance_sheet_is_first_class_source(self, session_cm) -> None:
        """Existing vendor compliance sheets remain evidence, but are classified explicitly."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("vendor-compliance.pdf", pdf_data, "application/pdf")},
            data={
                "document_type": "compliance_sheet",
                "vendor_name": "Acme Corp",
                "product_name": "Model X",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        async def _verify() -> None:
            async with session_cm() as session:
                doc = (
                    await session.execute(
                        select(OemDocument).where(
                            OemDocument.project_id == project_id,
                            OemDocument.display_name == "vendor-compliance.pdf",
                        )
                    )
                ).scalar_one()
                assert doc.document_type == OemDocumentType.COMPLIANCE_SHEET

        asyncio.run(_verify())

    def test_version_sequencing(self, session_cm) -> None:
        """Uploading the same filename twice creates v1 and v2."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        # v1
        r1 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            data={"document_type": "datasheet", "vendor_name": "Acme"},
            headers=headers,
        )
        assert r1.status_code == 201
        assert r1.json()["version_number"] == 1

        # v2 — same filename, new content (modify the PDF slightly)
        from pypdf import PdfWriter as _W
        writer = _W()
        writer.add_blank_page(width=100, height=100)
        buf = io.BytesIO()
        writer.write(buf)
        pdf_data_v2 = buf.getvalue()

        r2 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data_v2, "application/pdf")},
            headers=headers,
        )
        assert r2.status_code == 201
        assert r2.json()["version_number"] == 2

        async def _verify() -> None:
            async with session_cm() as session:
                docs = (
                    await session.execute(
                        select(OemDocument).where(
                            OemDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                # Same OemDocument, two versions.
                assert len(docs) == 1
                versions = (
                    await session.execute(
                        select(OemDocumentVersion).where(
                            OemDocumentVersion.document_id == docs[0].id
                        )
                    )
                ).scalars().all()
                assert len(versions) == 2
                assert versions[0].version_number == 1
                assert versions[1].version_number == 2

        asyncio.run(_verify())

    def test_duplicate_content_reuses_stored_object(self, session_cm) -> None:
        """Same bytes uploaded for different filenames reuses StoredObject."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        r1 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert r1.status_code == 201

        r2 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("brochure.pdf", pdf_data, "application/pdf")},
            data={"document_type": "brochure"},
            headers=headers,
        )
        assert r2.status_code == 201

        async def _verify() -> None:
            async with session_cm() as session:
                objs = (
                    await session.execute(
                        select(StoredObject).where(
                            StoredObject.project_id == project_id
                        )
                    )
                ).scalars().all()
                # Only 1 StoredObject despite 2 uploads (same checksum).
                assert len(objs) == 1

        asyncio.run(_verify())

    def test_empty_file_rejected(self, session_cm) -> None:
        """Empty uploads are rejected with 422."""
        headers, project_id = _build_auth_headers(session_cm)

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_malware_rejected(self, session_cm) -> None:
        """Infected files are rejected with 422."""
        headers, project_id = _build_auth_headers(session_cm)
        infected_data = TEST_INFECTED_SIGNATURE

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("virus.pdf", infected_data, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_invalid_document_type_rejected(self, session_cm) -> None:
        """Unknown document_type values are rejected with 422."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("doc.pdf", pdf_data, "application/pdf")},
            data={"document_type": "not_a_real_type"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_wrong_extension_rejected(self, session_cm) -> None:
        """Non-PDF extensions are rejected (same validation as tender uploads)."""
        headers, project_id = _build_auth_headers(session_cm)

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("malware.exe", b"not a pdf", "application/octet-stream")},
            headers=headers,
        )
        assert resp.status_code == 422


class TestOemListing:
    """OEM document listing."""

    def test_list_oem_documents(self, session_cm) -> None:
        """GET /oem-documents returns uploaded OEM document versions."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        # Upload two different OEM documents.
        r1 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            data={
                "document_type": "datasheet",
                "vendor_name": "Acme Corp",
            },
            headers=headers,
        )
        assert r1.status_code == 201

        # Second upload with different content
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        pdf_data_2 = buf.getvalue()

        r2 = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("test_report.pdf", pdf_data_2, "application/pdf")},
            data={
                "document_type": "test_report",
                "vendor_name": "Acme Corp",
            },
            headers=headers,
        )
        assert r2.status_code == 201

        # List
        resp = client.get(
            f"/projects/{project_id}/oem-documents",
            headers=headers,
        )
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) == 2
        for doc in docs:
            assert doc["vendor_name"] == "Acme Corp"
            # Upload → enqueued → QUEUED (worker processes asynchronously).
            assert doc["processing_status"] == "queued"

    def test_list_oem_documents_cross_tenant_denied(self, session_cm) -> None:
        """Cross-tenant access to OEM documents is denied."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()
        client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            data={"document_type": "datasheet", "vendor_name": "Acme"},
            headers=headers,
        )

        # Second org
        other_org_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        async def _setup_other():
            async with session_cm() as session:
                session.add(Organization(id=other_org_id, name="Other Org"))
                session.add(
                    User(
                        id=other_user_id,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user_id),
                    )
                )
                session.add(Membership(
                    organization_id=other_org_id,
                    user_id=other_user_id,
                    role="owner",
                ))
                await session.commit()
        asyncio.run(_setup_other())

        resp = client.get(
            f"/projects/{project_id}/oem-documents",
            headers=_headers(other_user_id, other_org_id),
        )
        assert resp.status_code == 404


class TestOemTenantIsolation:
    """Cross-tenant isolation for OEM documents."""

    def test_oem_upload_cross_tenant_denied(self, session_cm) -> None:
        """Other org cannot upload to a project they don't own."""
        headers, project_id = _build_auth_headers(session_cm)

        # Create other org with no access.
        other_org_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        async def _setup_other():
            async with session_cm() as session:
                session.add(Organization(id=other_org_id, name="Other Org"))
                session.add(User(
                    id=other_user_id, auth_provider="dev",
                    auth_provider_user_id=str(other_user_id),
                ))
                session.add(Membership(
                    organization_id=other_org_id,
                    user_id=other_user_id, role="owner",
                ))
                await session.commit()
        asyncio.run(_setup_other())

        pdf_data = _make_valid_pdf()
        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("doc.pdf", pdf_data, "application/pdf")},
            data={"document_type": "datasheet"},
            headers=_headers(other_user_id, other_org_id),
        )
        assert resp.status_code == 404

    def test_tender_upload_does_not_create_oem_docs(self, session_cm) -> None:
        """Uploading via the tender upload route creates TenderDocument
        but NOT OemDocument — the two remain separate."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        resp = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        assert resp.status_code == 201

        async def _verify() -> None:
            async with session_cm() as session:
                # Tender doc exists.
                tender = (
                    await session.execute(
                        select(TenderDocument).where(
                            TenderDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(tender) == 1

                # No OEM docs.
                oem = (
                    await session.execute(
                        select(OemDocument).where(
                            OemDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(oem) == 0

        asyncio.run(_verify())


class TestOemAuditTrail:
    """Audit trail records for OEM document uploads."""

    def test_upload_audit_events_recorded(self, session_cm) -> None:
        """Uploading an OEM document creates audit events."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            data={
                "document_type": "datasheet",
                "vendor_name": "Acme Corp",
                "product_name": "Thermostat X1",
                "product_sku": "TH-X1",
            },
            headers=headers,
        )

        async def _verify() -> None:
            async with session_cm() as session:
                events = (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.project_id == project_id,
                            AuditLog.action == "oem_document.upload",
                        )
                    )
                ).scalars().all()
                assert len(events) >= 1
                # Verify OEM-specific metadata is present.
                meta = events[0].metadata_json
                assert meta["oem_document_type"] == "datasheet"
                assert meta["vendor_name"] == "Acme Corp"
                assert meta["product_name"] == "Thermostat X1"
                assert "checksum_sha256" in meta
                assert "storage_key" in meta

        asyncio.run(_verify())


class TestOemImmutability:
    """OEM document versions are immutable."""

    def test_version_sha256_matches_stored_object(self, session_cm) -> None:
        """The OemDocumentVersion.sha256 must match the StoredObject checksum."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()
        import hashlib
        expected_sha = hashlib.sha256(pdf_data).hexdigest()

        resp = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )
        body = resp.json()
        assert body["checksum_sha256"] == expected_sha

        async def _verify() -> None:
            async with session_cm() as session:
                versions = (
                    await session.execute(
                        select(OemDocumentVersion).join(OemDocument).where(
                            OemDocument.project_id == project_id
                        )
                    )
                ).scalars().all()
                for v in versions:
                    assert v.sha256 == expected_sha
                    # Stored object exists and is not mutated by subsequent
                    # version uploads.
                    stored = (
                        await session.execute(
                            select(StoredObject).where(
                                StoredObject.id == v.stored_object_id
                            )
                        )
                    ).scalar_one()
                    assert stored.checksum_sha256 == v.sha256

        asyncio.run(_verify())


class _UnavailableOemScanner(FakeScanner):
    async def scan(self, filename: str, data: bytes):
        raise MalwareScannerUnavailableError("scanner offline")


def test_scanner_outage_rejects_oem_upload(session_cm) -> None:
    """A scanner outage never accepts an unscanned OEM source."""
    headers, project_id = _build_auth_headers(session_cm)
    original = app.dependency_overrides[get_scanner]
    app.dependency_overrides[get_scanner] = lambda: _UnavailableOemScanner()
    try:
        response = client.post(
            f"/projects/{project_id}/oem-documents/upload",
            files={"file": ("datasheet.pdf", _make_valid_pdf(), "application/pdf")},
            data={"document_type": "datasheet"},
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
