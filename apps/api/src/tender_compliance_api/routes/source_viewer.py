"""Source viewer API routes (CP36).

Tenant-scoped endpoints that expose the rendered page image and page
metadata for a specific document version.  The rendered PNG (CP20) is
served as raw bytes through the object-storage adapter, and the page's
text / OCR confidence / structural metadata is returned as JSON so the
frontend can overlay source anchors (bounding boxes) on the image.

Routes:

- ``GET .../pages/{page_number}``
  → page metadata (text, ocr_needed, ocr_confidence, structural metadata).

- ``GET .../pages/{page_number}/image``
  → rendered page PNG bytes (falls back to 404 if no image exists).

- ``GET .../pages/{page_number}/sources``
  → requirement source anchors (bboxes) for overlay on the rendered image.
"""

from __future__ import annotations

import re
import struct
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import Requirement, RequirementSource
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import DocumentNotFoundError, DocumentService
from tender_compliance_api.errors import (
    PAGE_IMAGE_STORAGE_FAILURE,
    PAGE_OCR_FAILURE,
    PAGE_RENDER_FAILURE,
    PAGE_TEXT_FAILURE,
)
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.factory import create_storage_adapter

router = APIRouter(prefix="/projects", tags=["source-viewer"])


def _safe_structural_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redact exception text from historical per-page metadata."""
    if not metadata:
        return None
    safe = dict(metadata)
    if safe.get("error"):
        safe["error"] = PAGE_TEXT_FAILURE
    safe_warnings = []
    for warning in safe.get("warnings", []):
        normalized = str(warning).lower()
        if "render failed" in normalized or "renderer raised" in normalized:
            safe_warnings.append(PAGE_RENDER_FAILURE)
        elif "image store failed" in normalized or "storage failed" in normalized:
            safe_warnings.append(PAGE_IMAGE_STORAGE_FAILURE)
        elif "ocr failed" in normalized:
            safe_warnings.append(PAGE_OCR_FAILURE)
        elif "text extraction failed" in normalized:
            safe_warnings.append(PAGE_TEXT_FAILURE)
        else:
            safe_warnings.append(warning)
    if "warnings" in safe:
        safe["warnings"] = safe_warnings
    return safe


def get_storage_adapter() -> ObjectStorageAdapter:
    """Return the configured storage adapter (FakeStorageAdapter by default).

    Uses the configured durable filesystem/S3 provider, with the in-memory
    fake reserved for unconfigured development/tests.
    """
    return create_storage_adapter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PageResponse(BaseModel):
    """Metadata for a single document page (text, OCR, structural info)."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    has_image: bool
    ocr_needed: bool
    ocr_confidence: float | None
    cleaned_text: str | None
    extracted_text: str | None
    structural_metadata: dict[str, Any] | None
    created_at: datetime


class SourceAnchor(BaseModel):
    """A source anchor for a requirement, returned for the overlay layer."""

    model_config = ConfigDict(from_attributes=True)

    requirement_id: UUID
    clause_number: str | None
    page_number: int
    location_type: str
    source_text: str | None
    quote_text: str | None
    bbox: dict[str, Any] | None
    ocr_confidence: float | None


def _pdf_quote_bbox(
    pdf_document: Any,
    page_number: int,
    quote: str,
    rendered_png: bytes,
) -> dict[str, float] | None:
    """Map one unique literal PDF text quote to rendered-page pixel coordinates."""
    if (
        len(rendered_png) < 24
        or rendered_png[:8] != b"\x89PNG\r\n\x1a\n"
        or not quote.strip()
    ):
        return None
    try:
        page = pdf_document.load_page(page_number - 1)
        if page.rotation != 0:
            return None
        normalized_quote = re.sub(r"\s+", " ", quote).strip()
        page_text = re.sub(r"\s+", " ", page.get_text(sort=True)).strip()
        if not normalized_quote or page_text.count(normalized_quote) != 1:
            return None
        rectangles = page.search_for(normalized_quote)
        if not rectangles:
            return None
        image_width, image_height = struct.unpack(">II", rendered_png[16:24])
        page_rect = page.rect
        if image_width <= 0 or image_height <= 0 or page_rect.width <= 0 or page_rect.height <= 0:
            return None
        scale_x = image_width / page_rect.width
        scale_y = image_height / page_rect.height
        x0 = min(rect.x0 for rect in rectangles)
        y0 = min(rect.y0 for rect in rectangles)
        x1 = max(rect.x1 for rect in rectangles)
        y1 = max(rect.y1 for rect in rectangles)
        return {
            "x": x0 * scale_x,
            "y": y0 * scale_y,
            "width": (x1 - x0) * scale_x,
            "height": (y1 - y0) * scale_y,
        }
    except Exception:  # noqa: BLE001 — missing/unmappable geometry stays unknown
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/pages/{page_number}",
    response_model=PageResponse,
    response_model_exclude_none=True,
)
async def get_page(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    page_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> PageResponse:
    """Retrieve a single page's metadata for the source viewer.

    Returns page text (native + cleaned), OCR confidence, and structural
    metadata.  Does **not** return the rendered image bytes — use the
    ``/image`` sub-resource for that.

    Authorized by organization and project scope.
    """
    svc = DocumentService(session)
    try:
        page = await svc.get_page(auth, document_id, version_number, page_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PageResponse(
        page_number=page.page_number,
        has_image=page.rendered_image_object_key is not None,
        ocr_needed=bool(page.ocr_needed),
        ocr_confidence=float(page.ocr_confidence) if page.ocr_confidence else None,
        cleaned_text=page.cleaned_text,
        extracted_text=page.extracted_text,
        structural_metadata=_safe_structural_metadata(page.structural_metadata),
        created_at=page.created_at,
    )


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/pages/{page_number}/image",
    response_class=Response,
)
async def get_page_image(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    page_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),  # noqa: B008
) -> Response:
    """Serve the rendered PNG for a single page.

    The image is streamed from object storage (MinIO/S3) or the in-memory
    fake in development/test.  If the page has no rendered image (rendering
    was skipped or failed), returns ``404`` — the frontend should fall back
    to the text viewer.

    Authorized by organization and project scope.
    """
    svc = DocumentService(session)
    try:
        image_bytes, content_type = await svc.get_page_image_bytes(
            auth, document_id, version_number, page_number, storage
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=image_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/pages/{page_number}/sources",
    response_model=list[SourceAnchor],
    response_model_exclude_none=True,
)
async def get_page_source_anchors(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    page_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),  # noqa: B008
) -> list[SourceAnchor]:
    """Return all requirement source anchors for a page.

    Used by the frontend to draw highlight overlays on the rendered PNG.
    Only anchors on this exact page are returned.
    """
    svc = DocumentService(session)
    try:
        version = await svc.get_version_or_raise(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = await session.execute(
        select(RequirementSource, Requirement.raw_source)
        .join(Requirement, Requirement.id == RequirementSource.requirement_id)
        .where(
            RequirementSource.document_version_id == version.id,
            RequirementSource.page_number == page_number,
        )
    )
    sources = list(result.all())
    page_png: bytes | None = None
    pdf_document: Any | None = None
    if any(source.bbox is None for source, _quote in sources):
        try:
            page_png, _ = await svc.get_page_image_bytes(
                auth, document_id, version_number, page_number, storage
            )
            original_key = await svc.get_stored_object_key(
                auth, document_id, version_number
            )
            import pymupdf

            pdf_document = pymupdf.open(  # type: ignore[no-untyped-call]
                stream=await storage.get(original_key), filetype="pdf"
            )
        except Exception:  # noqa: BLE001 — text/page navigation still works
            pdf_document = None
    anchors = [
        SourceAnchor(
            requirement_id=s.requirement_id,
            clause_number=s.clause_number,
            page_number=s.page_number,
            location_type=s.location_type,
            source_text=s.source_text,
            quote_text=quote_text,
            bbox=(
                dict(s.bbox)
                if s.bbox
                else (
                    _pdf_quote_bbox(
                        pdf_document, page_number, quote_text, page_png
                    )
                    if pdf_document is not None and page_png is not None
                    else None
                )
            ),
            ocr_confidence=float(s.ocr_confidence) if s.ocr_confidence else None,
        )
        for s, quote_text in sources
    ]
    if pdf_document is not None:
        pdf_document.close()
    return anchors
