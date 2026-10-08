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

import hashlib
import math
import re
import struct
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    DocumentPage,
    ExtractionDiagnostics,
    ExtractionWindowAudit,
    Requirement,
    RequirementSource,
)
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


def _page_quote_fragment(
    *, source_text: str | None, raw_source: str, location_type: str
) -> str:
    """Use an exact page-local excerpt when the persisted anchor has one."""
    if location_type != "exact" or not source_text:
        return raw_source
    normalized_source = re.sub(r"\s+", " ", source_text).strip()
    normalized_raw = re.sub(r"\s+", " ", raw_source).strip()
    if (
        normalized_source
        and normalized_source != normalized_raw
        and normalized_source in normalized_raw
    ):
        return source_text
    return raw_source


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

    anchor_id: str | None = None
    requirement_id: UUID | None = None
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


def _ocr_quote_bbox(
    ocr_words: list[dict[str, Any]] | None,
    quote: str,
    rendered_png: bytes,
) -> dict[str, float] | None:
    """Map one unique whitespace-normalized OCR word sequence to pixels."""
    if (
        not ocr_words
        or len(rendered_png) < 24
        or rendered_png[:8] != b"\x89PNG\r\n\x1a\n"
        or not quote.strip()
    ):
        return None
    try:
        image_width, image_height = struct.unpack(">II", rendered_png[16:24])
        quote_tokens = re.sub(r"\s+", " ", quote).strip().split(" ")
        page_words: list[tuple[str, dict[str, Any]]] = []
        for item in ocr_words:
            text = item.get("text")
            bbox = item.get("bbox")
            if not isinstance(text, str) or not text or not isinstance(bbox, dict):
                continue
            if re.search(r"\s", text):
                return None
            page_words.append((text, bbox))
        if not quote_tokens or len(quote_tokens) > len(page_words):
            return None
        starts = [
            index
            for index in range(len(page_words) - len(quote_tokens) + 1)
            if [word for word, _bbox in page_words[index:index + len(quote_tokens)]]
            == quote_tokens
        ]
        if len(starts) != 1 or image_width <= 0 or image_height <= 0:
            return None
        matched = page_words[starts[0]:starts[0] + len(quote_tokens)]
        boxes: list[tuple[float, float, float, float]] = []
        for _word, bbox in matched:
            x = float(bbox["x"])
            y = float(bbox["y"])
            width = float(bbox["width"])
            height = float(bbox["height"])
            values = (x, y, width, height)
            if (
                not all(math.isfinite(value) for value in values)
                or x < 0 or y < 0 or width <= 0 or height <= 0
                or x + width > image_width or y + height > image_height
            ):
                return None
            boxes.append((x, y, x + width, y + height))
        x0 = min(box[0] for box in boxes)
        y0 = min(box[1] for box in boxes)
        x1 = max(box[2] for box in boxes)
        y1 = max(box[3] for box in boxes)
        return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
    except (KeyError, TypeError, ValueError, OverflowError):
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
    quote: str | None = Query(default=None, max_length=2048),
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
        select(RequirementSource, Requirement.raw_source, DocumentPage.ocr_words)
        .join(Requirement, Requirement.id == RequirementSource.requirement_id)
        .outerjoin(
            DocumentPage,
            (DocumentPage.document_version_id == RequirementSource.document_version_id)
            & (DocumentPage.page_number == RequirementSource.page_number),
        )
        .where(
            RequirementSource.document_version_id == version.id,
            RequirementSource.page_number == page_number,
        )
    )
    sources = cast(
        list[tuple[RequirementSource, str, list[dict[str, Any]] | None]],
        list(result.all()),
    )
    quote_page: DocumentPage | None = None
    quote_record: DocumentPage | None = None
    coverage_bbox: dict[str, float] | None = None
    if quote and quote.strip():
        quote_record = (
            await session.execute(
                select(DocumentPage).where(
                    DocumentPage.document_version_id == version.id,
                    DocumentPage.page_number == page_number,
                )
            )
        ).scalar_one_or_none()
        if quote_record is not None and quote_record.cleaned_text:
            normalized_page_text = re.sub(r"\s+", " ", quote_record.cleaned_text).strip()
            normalized_quote = re.sub(r"\s+", " ", quote).strip()
            if normalized_quote and normalized_page_text.count(normalized_quote) == 1:
                quote_page = quote_record
        if quote_record is not None:
            latest_diagnostics = (
                await session.execute(
                    select(ExtractionDiagnostics)
                    .where(
                        ExtractionDiagnostics.document_version_id == version.id
                    )
                    .order_by(
                        ExtractionDiagnostics.created_at.desc(),
                        ExtractionDiagnostics.id.desc(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if latest_diagnostics and latest_diagnostics.processing_run_id:
                audits = (
                    await session.execute(
                        select(ExtractionWindowAudit).where(
                            ExtractionWindowAudit.processing_run_id
                            == latest_diagnostics.processing_run_id
                        )
                    )
                ).scalars().all()
                normalized_quote = re.sub(r"\s+", " ", quote).strip()
                for audit in audits:
                    findings = audit.potential_omissions
                    if not isinstance(findings, list):
                        continue
                    for finding in findings:
                        if (
                            not isinstance(finding, dict)
                            or finding.get("page_number") != page_number
                            or not isinstance(finding.get("source_quote"), str)
                            or re.sub(r"\s+", " ", finding["source_quote"]).strip()
                            != normalized_quote
                        ):
                            continue
                        candidate_bbox = finding.get("bbox")
                        if not isinstance(candidate_bbox, dict):
                            continue
                        try:
                            values = {
                                key: float(candidate_bbox[key])
                                for key in ("x", "y", "width", "height")
                            }
                        except (KeyError, TypeError, ValueError, OverflowError):
                            continue
                        if (
                            all(math.isfinite(value) for value in values.values())
                            and values["x"] >= 0
                            and values["y"] >= 0
                            and values["width"] > 0
                            and values["height"] > 0
                        ):
                            coverage_bbox = values
                            break
                    if coverage_bbox is not None:
                        break
    page_png: bytes | None = None
    pdf_document: Any | None = None
    if quote_page is not None or coverage_bbox is not None or any(
        source.bbox is None for source, _quote, _words in sources
    ):
        try:
            page_png, _ = await svc.get_page_image_bytes(
                auth, document_id, version_number, page_number, storage
            )
            if quote_page is not None or any(
                source.bbox is None for source, _quote, _words in sources
            ):
                original_key = await svc.get_stored_object_key(
                    auth, document_id, version_number
                )
                import pymupdf

                pdf_document = pymupdf.open(  # type: ignore[no-untyped-call]
                    stream=await storage.get(original_key), filetype="pdf"
                )
        except Exception:  # noqa: BLE001 — text/page navigation still works
            pdf_document = None
    anchors: list[SourceAnchor] = []
    for source, quote_text, ocr_words in sources:
        quote_text = _page_quote_fragment(
            source_text=source.source_text,
            raw_source=quote_text,
            location_type=source.location_type,
        )
        bbox = dict(source.bbox) if source.bbox else None
        if bbox is None and page_png is not None:
            if pdf_document is not None:
                bbox = _pdf_quote_bbox(
                    pdf_document, page_number, quote_text, page_png
                )
            if bbox is None:
                bbox = _ocr_quote_bbox(ocr_words, quote_text, page_png)
        anchors.append(
            SourceAnchor(
                anchor_id=str(source.id),
                requirement_id=source.requirement_id,
                clause_number=source.clause_number,
                page_number=source.page_number,
                location_type=source.location_type,
                source_text=source.source_text,
                quote_text=quote_text,
                bbox=bbox,
                ocr_confidence=(
                    float(source.ocr_confidence)
                    if source.ocr_confidence
                    else None
                ),
            )
        )
    if quote is not None and (quote_page is not None or coverage_bbox is not None):
        source_quote = re.sub(r"\s+", " ", quote).strip()
        if not any(anchor.quote_text == source_quote for anchor in anchors):
            bbox = coverage_bbox
            bbox_location_type = "approximate" if bbox is not None else None
            if bbox is not None and page_png is not None:
                image_width, image_height = struct.unpack(">II", page_png[16:24])
                if (
                    bbox["x"] + bbox["width"] > image_width
                    or bbox["y"] + bbox["height"] > image_height
                ):
                    bbox = None
                    bbox_location_type = None
            if bbox is None and quote_page is not None and page_png is not None:
                if pdf_document is not None:
                    bbox = _pdf_quote_bbox(
                        pdf_document, page_number, source_quote, page_png
                    )
                if bbox is None:
                    bbox = _ocr_quote_bbox(
                        quote_page.ocr_words, source_quote, page_png
                    )
            anchor_digest = hashlib.sha256(
                f"{version.id}:{page_number}:{source_quote}".encode()
            ).hexdigest()
            anchors.append(
                SourceAnchor(
                    anchor_id=f"coverage-{anchor_digest}",
                    requirement_id=None,
                    clause_number=None,
                    page_number=page_number,
                    location_type=(
                        bbox_location_type
                        or ("exact" if quote_page is not None else "approximate")
                    ),
                    source_text=source_quote,
                    quote_text=source_quote,
                    bbox=bbox,
                    ocr_confidence=(
                        float(quote_record.ocr_confidence)
                        if quote_record is not None
                        and quote_record.ocr_confidence is not None
                        else None
                    ),
                )
            )
    if pdf_document is not None:
        pdf_document.close()
    return anchors
