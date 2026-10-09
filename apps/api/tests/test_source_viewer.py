"""Tests for CP36 — Source viewer API.

Covers:
- GET .../pages/{page_number} — page metadata (text, OCR, structural metadata)
- GET .../pages/{page_number}/image — rendered PNG bytes from storage
- GET .../pages/{page_number}/sources — requirement source anchors for overlay
- Tenant isolation: cross-org access is denied
- 404 for non-existent pages or pages with no rendered image
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
import uuid
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    ExtractionDiagnostics,
    ExtractionWindowAudit,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    ProjectStatus,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    RunStatus,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.main import app
from tender_compliance_api.routes.source_viewer import (
    _ocr_quote_bbox,
    _pdf_quote_bbox,
    get_storage_adapter,
)
from tender_compliance_api.storage.fake import FakeStorageAdapter

client = TestClient(app)

_session_cm = contextlib.asynccontextmanager(get_session)

# Shared fake storage for tests that override the dependency.
_test_storage: FakeStorageAdapter | None = None


def _make_test_storage() -> FakeStorageAdapter:
    """Return a fresh FakeStorageAdapter and install it as the route dependency."""
    global _test_storage
    _test_storage = FakeStorageAdapter()
    app.dependency_overrides[get_storage_adapter] = lambda: _test_storage
    return _test_storage


def _clear_test_storage():
    """Remove the storage dependency override."""
    app.dependency_overrides.pop(get_storage_adapter, None)


def _put_image_sync(key: str, data: bytes, content_type: str = "image/png"):
    """Synchronously store an image in the test storage."""
    assert _test_storage is not None, "Test storage not initialized; call _make_test_storage first"
    asyncio.run(_test_storage.put(key, data, content_type))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _build_org_project():
    """Set up org + user + membership + project; return (user_id, org_id, project_id)."""

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP36 Test Org"))
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
                    name="CP36 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _create_doc_version_with_pages(project_id: uuid.UUID, num_pages: int = 3):
    """Create a document version with pages, one requirement with a source anchor.

    Returns (document_id, version_number).
    """

    async def _create():
        async with _session_cm() as session:
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
                processing_status=DocumentProcessingStatus.PARSED,
            )
            session.add(version)
            await session.flush()

            # Create pages.  Page 1 and 2 have rendered images; page 3 does not.
            for i in range(1, num_pages + 1):
                page = DocumentPage(
                    document_version_id=version.id,
                    page_number=i,
                    extracted_text=f"Page {i} native text content.",
                    cleaned_text=f"Page {i} cleaned text.",
                    ocr_needed=0,
                    ocr_confidence=0.95,
                    rendered_image_object_key=f"rendered/page_{i}.png" if i <= 2 else None,
                )
                session.add(page)
            await session.flush()

            # Create a requirement on page 1 with a source anchor that has a bbox
            req = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                requirement_type="obligation",
                normalized_text="weight \u2264 2 kg",
                raw_source="weight \u2264 2 kg",
                uncertainty="confirmed",
                ocr_warning=False,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req)
            await session.flush()

            source = RequirementSource(
                requirement_id=req.id,
                document_version_id=version.id,
                page_number=1,
                clause_number="4.2.1",
                location_type="exact",
                source_text="weight \u2264 2 kg",
                bbox={"x": 100, "y": 200, "width": 300, "height": 20},
                ocr_confidence=0.95,
            )
            session.add(source)
            await session.commit()
            return doc.id, version.version_number

    return asyncio.run(_create())


def _setup_other_org():
    """Create a second org/user not in the project's org; return (user_id, org_id)."""

    async def _setup():
        other_org = uuid.uuid4()
        other_user = uuid.uuid4()
        async with _session_cm() as session:
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
        return other_user, other_org

    return asyncio.run(_setup())


# ---------------------------------------------------------------------------
# Page metadata endpoint
# ---------------------------------------------------------------------------


class TestPageMetadata:
    def test_historical_exception_text_is_redacted(self):
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=1)

        async def _inject_historical_metadata():
            async with _session_cm() as session:
                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id
                            == select(DocumentVersion.id)
                            .where(DocumentVersion.document_id == doc_id)
                            .scalar_subquery(),
                            DocumentPage.page_number == 1,
                        )
                    )
                ).scalars().first()
                assert page is not None
                page.structural_metadata = {
                    "error": "provider token SECRET leaked from parser",
                    "warnings": [
                        "page render failed: /private/path SECRET",
                        "page has no text layer",
                    ],
                }
                await session.commit()

        asyncio.run(_inject_historical_metadata())
        response = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1",
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 200
        body = response.json()
        assert "SECRET" not in response.text
        assert "provider token" not in response.text
        assert "Page preview rendering failed" in body["structural_metadata"]["warnings"][0]
        assert "page has no text layer" in body["structural_metadata"]["warnings"][1]

    def test_get_page_returns_metadata(self):
        """GET page returns text, OCR, structural metadata."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_number"] == 1
        assert body["has_image"] is True  # page 1 has rendered_image_object_key
        assert body["ocr_needed"] is False
        assert body["ocr_confidence"] == 0.95
        assert body["cleaned_text"] == "Page 1 cleaned text."
        assert body["extracted_text"] == "Page 1 native text content."
        assert "created_at" in body

    def test_get_page_no_image_metadata(self):
        """GET page for a page with no rendered image still returns metadata."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/3",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_number"] == 3
        assert body["has_image"] is False

    def test_get_page_404_for_nonexistent_page(self):
        """GET page for a non-existent page number returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/99",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404

    def test_get_page_tenant_isolation(self):
        """Cross-org access to page metadata returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        other_user, other_org = _setup_other_org()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Page image endpoint
# ---------------------------------------------------------------------------


class TestPageImage:
    def test_get_page_image_returns_bytes(self):
        """GET page image returns the stored PNG bytes."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        _make_test_storage()
        _put_image_sync("rendered/page_1.png", b"\x89PNG\r\n\x1a\n fake png data")
        try:
            resp = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/image",
                headers=_headers(user_id, org_id),
            )
        finally:
            _clear_test_storage()

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == b"\x89PNG\r\n\x1a\n fake png data"

    def test_get_page_image_404_when_no_image(self):
        """GET page image for a page with no rendered image returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)
        # Page 3 has no rendered_image_object_key

        _make_test_storage()
        try:
            resp = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/3/image",
                headers=_headers(user_id, org_id),
            )
        finally:
            _clear_test_storage()

        assert resp.status_code == 404

    def test_get_page_image_tenant_isolation(self):
        """Cross-org access to page image returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        other_user, other_org = _setup_other_org()

        _make_test_storage()
        try:
            resp = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/image",
                headers=_headers(other_user, other_org),
            )
        finally:
            _clear_test_storage()

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Source anchors endpoint
# ---------------------------------------------------------------------------


class TestSourceAnchors:
    def test_pdf_quote_bbox_maps_unique_literal_quote_and_fails_closed(self):
        pdf = pymupdf.open()
        page = pdf.new_page(width=300, height=200)
        fontfile = (
            Path(__file__).parent.parent
            / "src/tender_compliance_api/export/fonts/DejaVuSans.ttf"
        )
        page.insert_text(
            (30, 60),
            "Wafer diameter shall be 4” minimum.",
            fontname="dejavu",
            fontfile=str(fontfile),
        )
        rendered_png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")

        bbox = _pdf_quote_bbox(pdf, 1, "Wafer diameter shall be 4” minimum.", rendered_png)

        assert bbox is not None
        assert bbox["x"] > 0
        assert bbox["y"] > 0
        assert bbox["width"] > 0
        assert bbox["height"] > 0
        assert _pdf_quote_bbox(
            pdf, 1, 'Wafer diameter shall be 4" minimum.', rendered_png
        ) is None

        page.insert_text(
            (30, 100),
            "Wafer diameter shall be 4” minimum.",
            fontname="dejavu",
            fontfile=str(fontfile),
        )
        duplicated_png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
        assert _pdf_quote_bbox(
            pdf, 1, "Wafer diameter shall be 4” minimum.", duplicated_png
        ) is None
        pdf.close()

    def test_pdf_quote_bbox_matches_unique_full_tokens_across_whitespace_changes(self):
        pdf = pymupdf.open()
        page = pdf.new_page(width=500, height=200)
        fontfile = (
            Path(__file__).parent.parent
            / "src/tender_compliance_api/export/fonts/DejaVuSans.ttf"
        )
        page.insert_text(
            (30, 60),
            "16. PREDISPATCH- The firm  should arrange the inspection.",
            fontname="dejavu",
            fontfile=str(fontfile),
        )
        rendered_png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")

        bbox = _pdf_quote_bbox(
            pdf,
            1,
            "16. PREDISPATCH - The firm should arrange the inspection.",
            rendered_png,
        )

        assert bbox is not None
        assert bbox["x"] > 0
        assert bbox["y"] > 0
        assert bbox["width"] > 0
        assert bbox["height"] > 0
        assert _pdf_quote_bbox(
            pdf,
            1,
            "16. PREDISPATCH - The firm shall arrange the inspection.",
            rendered_png,
        ) is None
        assert _pdf_quote_bbox(
            pdf,
            1,
            "16. PREDISPATCH – The firm should arrange the inspection.",
            rendered_png,
        ) is None
        pdf.close()

    def test_pdf_quote_bbox_does_not_guess_rotated_page_geometry(self):
        pdf = pymupdf.open()
        page = pdf.new_page(width=300, height=200)
        fontfile = (
            Path(__file__).parent.parent
            / "src/tender_compliance_api/export/fonts/DejaVuSans.ttf"
        )
        page.insert_text(
            (30, 60),
            "Minimum accuracy shall be ±2 mm.",
            fontname="dejavu",
            fontfile=str(fontfile),
        )
        page.set_rotation(90)
        rendered_png = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")

        assert _pdf_quote_bbox(
            pdf, 1, "Minimum accuracy shall be ±2 mm.", rendered_png
        ) is None
        pdf.close()

    def test_ocr_quote_bbox_rejects_ambiguous_or_changed_words(self):
        png = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">IIBBBBB", 300, 100, 8, 6, 0, 0, 0)
            + b"\x00\x00\x00\x00"
        )
        words = [
            {"text": "weight", "bbox": {"x": 10, "y": 20, "width": 35, "height": 12}},
            {"text": "≤", "bbox": {"x": 48, "y": 20, "width": 10, "height": 12}},
            {"text": "2", "bbox": {"x": 62, "y": 20, "width": 7, "height": 12}},
            {"text": "kg", "bbox": {"x": 73, "y": 20, "width": 15, "height": 12}},
        ]
        assert _ocr_quote_bbox(words + words, "weight ≤ 2 kg", png) is None
        assert _ocr_quote_bbox(words, "weight < 2 kg", png) is None

    def test_get_page_sources_returns_anchors(self):
        """GET page sources returns source anchors with bbox for overlay."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        anchor = body[0]
        assert anchor["page_number"] == 1
        assert anchor["location_type"] == "exact"
        assert anchor["source_text"] == "weight \u2264 2 kg"
        assert anchor["bbox"] == {"x": 100, "y": 200, "width": 300, "height": 20}
        assert anchor["ocr_confidence"] == 0.95
        assert "clause_number" in anchor
        assert "requirement_id" in anchor

    def test_ocr_word_geometry_highlights_unique_exact_quote(self):
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">IIBBBBB", 300, 100, 8, 6, 0, 0, 0)
            + b"\x00\x00\x00\x00"
        )

        async def _persist_ocr_geometry():
            async with _session_cm() as session:
                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.page_number == 1,
                            DocumentPage.document_version_id
                            == select(DocumentVersion.id)
                            .where(DocumentVersion.document_id == doc_id)
                            .scalar_subquery(),
                        )
                    )
                ).scalar_one()
                page.ocr_words = [
                    {"text": "weight", "bbox": {"x": 10, "y": 20, "width": 35, "height": 12}},
                    {"text": "≤", "bbox": {"x": 48, "y": 20, "width": 10, "height": 12}},
                    {"text": "2", "bbox": {"x": 62, "y": 20, "width": 7, "height": 12}},
                    {"text": "kg", "bbox": {"x": 73, "y": 20, "width": 15, "height": 12}},
                ]
                source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.document_version_id
                            == page.document_version_id
                        )
                    )
                ).scalar_one()
                source.bbox = None
                await session.commit()

        asyncio.run(_persist_ocr_geometry())
        _make_test_storage()
        _put_image_sync("rendered/page_1.png", png)
        try:
            response = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
                headers=_headers(user_id, org_id),
            )
        finally:
            _clear_test_storage()

        assert response.status_code == 200
        assert response.json()[0]["bbox"] == {
            "x": 10.0, "y": 20.0, "width": 78.0, "height": 12.0
        }

    def test_coverage_quote_deep_link_returns_only_source_verified_anchor(self):
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)
        quote = "The motor shall be IP55 rated."
        png = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">IIBBBBB", 300, 100, 8, 6, 0, 0, 0)
            + b"\x00\x00\x00\x00"
        )

        async def _persist_quote_geometry():
            async with _session_cm() as session:
                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id
                            == select(DocumentVersion.id)
                            .where(DocumentVersion.document_id == doc_id)
                            .scalar_subquery(),
                            DocumentPage.page_number == 1,
                        )
                    )
                ).scalar_one()
                page.cleaned_text = quote
                page.ocr_words = [
                    {
                        "text": token,
                        "bbox": {
                            "x": 10 + index * 20,
                            "y": 20,
                            "width": 18,
                            "height": 12,
                        },
                    }
                    for index, token in enumerate(quote.split())
                ]
                await session.commit()

        asyncio.run(_persist_quote_geometry())
        _make_test_storage()
        _put_image_sync("rendered/page_1.png", png)
        try:
            response = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
                params={"quote": quote},
                headers=_headers(user_id, org_id),
            )
            fabricated = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
                params={"quote": "The motor shall be IP66 rated."},
                headers=_headers(user_id, org_id),
            )
        finally:
            _clear_test_storage()

        assert response.status_code == 200
        anchor = next(item for item in response.json() if item["quote_text"] == quote)
        assert anchor.get("requirement_id") is None
        assert anchor["location_type"] == "exact"
        assert anchor["bbox"] == {
            "x": 10.0, "y": 20.0, "width": 118.0, "height": 12.0
        }
        assert fabricated.status_code == 200
        assert all(
            item["quote_text"] != "The motor shall be IP66 rated."
            for item in fabricated.json()
        )

    @pytest.mark.parametrize("cleaned_text_matches_quote", [False, True])
    def test_image_audit_quote_opens_with_bounded_approximate_highlight(
        self, cleaned_text_matches_quote: bool
    ):
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)
        quote = "Maximum operating temperature shall be 90 °C."
        bbox = {"x": 30.0, "y": 40.0, "width": 120.0, "height": 20.0}
        png = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">IIBBBBB", 300, 100, 8, 6, 0, 0, 0)
            + b"\x00\x00\x00\x00"
        )

        async def _persist_visual_finding():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc_id,
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == version.id,
                            DocumentPage.page_number == 1,
                        )
                    )
                ).scalar_one()
                page.cleaned_text = (
                    quote if cleaned_text_matches_quote else "Unclear OCR output"
                )
                run = ProcessingRun(
                    document_version_id=version.id,
                    run_id=uuid.uuid4(),
                    attempt=1,
                    stage=ProcessingStage.EXTRACT,
                    status=RunStatus.COMPLETED,
                )
                session.add(run)
                await session.flush()
                session.add(
                    ExtractionDiagnostics(
                        document_version_id=version.id,
                        processing_run_id=run.id,
                        total_windows=1,
                        rejection_breakdown={},
                    )
                )
                session.add(
                    ExtractionWindowAudit(
                        document_version_id=version.id,
                        processing_run_id=run.id,
                        chunk_id="visual-window",
                        window_index=1,
                        call_status="completed",
                        candidate_count=0,
                        ocr_warning=True,
                        source_spans=[{"page_number": 1, "char_start": 0, "char_end": 18}],
                        coverage_status="completed",
                        potential_omissions=[
                            {
                                "page_number": 1,
                                "source_quote": quote,
                                "bbox": bbox,
                            }
                        ],
                    )
                )
                await session.commit()

        asyncio.run(_persist_visual_finding())
        _make_test_storage()
        _put_image_sync("rendered/page_1.png", png)
        try:
            response = client.get(
                f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
                params={"quote": quote},
                headers=_headers(user_id, org_id),
            )
        finally:
            _clear_test_storage()

        assert response.status_code == 200
        anchor = next(item for item in response.json() if item["quote_text"] == quote)
        assert anchor.get("requirement_id") is None
        assert anchor["location_type"] == "approximate"
        assert anchor["bbox"] == bbox

    def test_get_page_sources_empty_for_page_without_anchors(self):
        """GET page sources for a page with no anchors returns empty list."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/2/sources",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_page_sources_tenant_isolation(self):
        """Cross-org access to source anchors returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_pages(project_id, num_pages=3)

        other_user, other_org = _setup_other_org()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/pages/1/sources",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404
