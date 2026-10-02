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

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import RequirementSource
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import DocumentNotFoundError, DocumentService
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter

router = APIRouter(prefix="/projects", tags=["source-viewer"])


def get_storage_adapter() -> ObjectStorageAdapter:
    """Return the configured storage adapter (FakeStorageAdapter by default).

    Uses :class:`FakeStorageAdapter` when no endpoint is configured
    (development / CI).  In production this returns an S3StorageAdapter.
    """
    settings = get_settings()
    if not settings.object_storage_endpoint:
        return FakeStorageAdapter()
    # Imported lazily so tests never need boto3 credentials configured.
    from tender_compliance_api.storage.s3 import S3StorageAdapter

    return S3StorageAdapter(
        endpoint_url=settings.object_storage_endpoint,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=settings.object_storage_bucket,
        region=settings.object_storage_region,
    )


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
    bbox: dict[str, Any] | None
    ocr_confidence: float | None


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
        structural_metadata=dict(page.structural_metadata)
        if page.structural_metadata
        else None,
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
        select(RequirementSource).where(
            RequirementSource.document_version_id == version.id,
            RequirementSource.page_number == page_number,
        )
    )
    sources = list(result.scalars().all())
    return [
        SourceAnchor(
            requirement_id=s.requirement_id,
            clause_number=s.clause_number,
            page_number=s.page_number,
            location_type=s.location_type,
            source_text=s.source_text,
            bbox=dict(s.bbox) if s.bbox else None,
            ocr_confidence=float(s.ocr_confidence) if s.ocr_confidence else None,
        )
        for s in sources
    ]
