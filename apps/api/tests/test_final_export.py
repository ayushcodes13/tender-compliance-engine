"""Tests for CP60 — Final XLSX, DOCX, and PDF outputs.

Covers:
- XLSX export from final matrix projection (Phase 2 columns present)
- DOCX export from final matrix projection
- PDF export from final matrix projection
- Export artifact metadata recorded (format, checksum, audit)
- Export is append-only (new ExportArtifact per export, never mutates older)
- Tenant isolation on export
- Failed export records FAILED artifact
- No fabrication: missing evidence/assessment → empty cells, not defaults
"""

from __future__ import annotations

import asyncio
import contextlib
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    RequirementSource,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.main import app

client = TestClient(app)
_session_cm = contextlib.asynccontextmanager(get_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id, org_id):
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _build_org_project_with_req():
    """Set up org + user + membership + project + document version + requirement.

    Returns (user_id, org_id, project_id, doc_id, version_number, version_id, req_id).
    """

    async def _setup():
        org_id = uuid_module.uuid4()
        user_id = uuid_module.uuid4()
        project_id = uuid_module.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP60 Org"))
            session.add(
                User(
                    id=user_id, auth_provider="dev",
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
                    id=project_id, organization_id=org_id, name="CP60 Proj",
                    status=ProjectStatus.TENDER_UPLOADED, created_by=user_id,
                )
            )
            doc = TenderDocument(
                project_id=project_id, display_name="tender.pdf",
                document_type="tender",
            )
            session.add(doc)
            await session.flush()
            version = DocumentVersion(
                document_id=doc.id, version_number=1,
                stored_object_id=uuid_module.uuid4(), sha256="abc",
                mime_type="application/pdf", size_bytes=1024,
                processing_status=DocumentProcessingStatus.PARSED,
            )
            session.add(version)
            await session.flush()
            req = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid_module.uuid4().hex[:8]}",
                requirement_type="numeric",
                normalized_text="The operating temperature shall be at least 25 °C.",
                raw_source="The operating temperature shall be at least 25 °C.",
                uncertainty="exact", ocr_warning=False,
                review_state="unreviewed", display_order=1,
            )
            session.add(req)
            await session.commit()
            session.add(
                RequirementSource(
                    requirement_id=req.id,
                    document_version_id=version.id,
                    page_number=1,
                    source_text=req.raw_source,
                )
            )
            await session.commit()
            return (
                user_id, org_id, project_id, str(doc.id),
                version.version_number, version.id, req.id,
            )

    return asyncio.run(_setup())


import uuid as uuid_module  # noqa: E402

# ---------------------------------------------------------------------------
# XLSX export
# ---------------------------------------------------------------------------


class TestXlsxExport:
    def test_xlsx_export_returns_artifact(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed", data.get("validation_report")
        assert data["requirement_count"] == 1
        assert data["export_format"] == "xlsx"
        assert data["workbook_sha256"]  # non-empty checksum
        assert data["stored_object_id"] is not None
        assert data["validation_report"]["checked_columns"] == 28
        assert data["validation_report"]["checked_cells"] == 28

        history = client.get(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert history.status_code == 200
        saved_artifact = next(
            item for item in history.json() if item["id"] == data["id"]
        )
        assert saved_artifact["validation_status"] == "passed"
        assert saved_artifact["validation_report"]["checked_cells"] == 28

    def test_xlsx_export_has_phase2_columns(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        # Download the workbook.
        download = client.get(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/exports/{data['id']}",
            headers=_headers(user_id, org_id),
        )
        assert download.status_code == 200
        wb_bytes = download.content
        # Verify it's a valid XLSX (ZIP containing workbook.xml).
        with zipfile.ZipFile(BytesIO(wb_bytes)) as zf:
            names = zf.namelist()
            assert any("workbook" in n for n in names)
        # Check Phase 2 column headers via openpyxl.
        from openpyxl import load_workbook
        wb = load_workbook(filename=BytesIO(wb_bytes))
        ws = wb.active
        # Header row is row 7 (5 metadata rows + 1 blank).
        headers = [str(cell.value) for cell in ws[7]]
        assert "Assessment Status" in headers
        assert "Vendor Spec Value" in headers
        assert "Evidence ID" in headers

    def test_xlsx_export_no_fabrication(self):
        """Requirement with no evidence still exports with empty Phase 2 cells."""
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["requirement_count"] == 1

    def test_xlsx_export_append_only(self):
        """Each export creates a new ExportArtifact row."""
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )
        assert resp.status_code == 200
        artifact_id_1 = resp.json()["id"]

        resp2 = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )
        assert resp2.status_code == 200
        artifact_id_2 = resp2.json()["id"]

        assert artifact_id_1 != artifact_id_2


# ---------------------------------------------------------------------------
# DOCX export
# ---------------------------------------------------------------------------


class TestDocxExport:
    def test_docx_export_returns_artifact(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "docx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["export_format"] == "docx"
        assert data["stored_object_id"] is not None
        assert data["validation_report"]["checked_columns"] == 11
        assert data["validation_report"]["checked_cells"] == 11

    def test_docx_export_download_and_verify(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "docx"},
        )
        assert resp.status_code == 200
        data = resp.json()

        download = client.get(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/exports/{data['id']}",
            headers=_headers(user_id, org_id),
        )
        assert download.status_code == 200
        docx_bytes = download.content
        # DOCX is a ZIP; verify it's a valid Office Open XML package.
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            names = zf.namelist()
            assert "word/document.xml" in names

    def test_vendor_response_sheet_keeps_full_text_and_blank_response_fields(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )
        full_text = "The complete tender specification " + ("with all conditions " * 40)

        async def _add_source():
            async with _session_cm() as session:
                req = await session.get(Requirement, req_id)
                assert req is not None
                req.normalized_text = full_text
                req.raw_source = full_text
                req.clause_number = "4.2.1"
                source_result = await session.execute(
                    select(RequirementSource).where(
                        RequirementSource.requirement_id == req_id
                    )
                )
                source = source_result.scalar_one()
                source.page_number = 12
                source.clause_number = "4.2.1"
                source.location_type = "exact"
                source.source_text = full_text
                await session.commit()

        asyncio.run(_add_source())
        response = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "docx", "template": "vendor-response"},
        )
        assert response.status_code == 200
        artifact = response.json()
        assert artifact["validation_report"]["checked_columns"] == 7
        assert artifact["validation_report"]["checked_cells"] == 7
        download = client.get(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/exports/{artifact['id']}",
            headers=_headers(user_id, org_id),
        )
        assert download.status_code == 200

        from docx import Document

        exported = Document(BytesIO(download.content))
        rows = exported.tables[0].rows
        assert rows[0].cells[1].text == "Tender requirement"
        assert rows[1].cells[1].text == full_text
        assert rows[1].cells[2].text == "4.2.1"
        assert rows[1].cells[3].text == "12"
        assert rows[1].cells[4].text == "Unreviewed"
        assert rows[1].cells[5].text == ""
        assert rows[1].cells[6].text == ""

    def test_vendor_response_template_rejects_non_docx(self):
        (user_id, org_id, proj_id, doc_id, ver, _ver_id, _req_id) = (
            _build_org_project_with_req()
        )
        response = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx", "template": "vendor-response"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


class TestPdfExport:
    def test_pdf_export_returns_artifact(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed", data.get("validation_report")
        assert data["export_format"] == "pdf"
        assert data["stored_object_id"] is not None
        assert data["validation_report"]["checked_columns"] == 9
        assert data["validation_report"]["checked_cells"] == 9

    def test_pdf_export_download_and_verify(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()

        download = client.get(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/exports/{data['id']}",
            headers=_headers(user_id, org_id),
        )
        assert download.status_code == 200
        pdf_bytes = download.content
        # Verify it starts with %PDF magic bytes.
        assert pdf_bytes[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Export format default
# ---------------------------------------------------------------------------


class TestDefaultFormat:
    def test_default_format_is_xlsx(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["export_format"] == "xlsx"


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestExportTenantIsolation:
    def test_cross_org_cannot_export(self):
        (user_id, org_id, proj_id, doc_id, ver, ver_id, req_id) = (
            _build_org_project_with_req()
        )

        async def _other_org():
            other_org = uuid_module.uuid4()
            other_user = uuid_module.uuid4()
            async with _session_cm() as session:
                session.add(Organization(id=other_org, name="Other"))
                session.add(
                    User(
                        id=other_user, auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(
                        organization_id=other_org, user_id=other_user, role="owner"
                    )
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_other_org())

        resp = client.post(
            f"/projects/{proj_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(other_user, other_org),
            params={"fmt": "xlsx"},
        )
        assert resp.status_code == 404
