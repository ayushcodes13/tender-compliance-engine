"""Requirement list/detail/edit/structure API routes (CP35, CP38, CP39).

Tenant-scoped endpoints for listing, inspecting, editing, and reorganizing
requirements within a specific document version.  All routes are
authorized via :class:`AuthContext` (organization-scoped) and further
restricted to the document version's project.

Response schemas are explicit Pydantic models — never raw ORM objects on the
wire — and never include full document bodies (guardrail from CP35).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import write_audit_event
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    CoverageFindingReview,
    DocumentPage,
    DocumentVersion,
    ExportArtifact,
    ExportFormat,
    ExportStatus,
    ExtractionWindowAudit,
    Project,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    TenderDocument,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import (
    ConcurrentEditError,
    DocumentNotFoundError,
    DocumentService,
    TransitionError,
    validate_ocr_page_quote_from_image,
)
from tender_compliance_api.errors import EXPORT_FAILURE
from tender_compliance_api.extraction.coverage_audit import (
    quote_is_covered,
    quote_is_present_in_source,
)
from tender_compliance_api.logs import (
    error_category,
    get_correlation_id,
    get_logger,
    log_event,
)

router = APIRouter(prefix="/projects", tags=["requirements"])
logger = get_logger("routes.requirements")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ConstraintSummary(BaseModel):
    """A single structured constraint (numeric or qualitative)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parameter: str
    operator: str | None
    numeric_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    unit: str | None
    tolerance: float | None
    qualitative_condition: str | None
    normalization_state: str
    raw_fragment: str
    raw_value_lexical: str | None = None
    created_at: datetime


class RequirementSourceSummary(BaseModel):
    """A source anchor for a requirement."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requirement_id: UUID
    page_number: int
    clause_number: str | None
    location_type: str
    source_text: str | None
    quote_text: str | None = None
    ocr_confidence: float | None


class RequirementSummary(BaseModel):
    """A single requirement in list view (no document body, no full sources)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requirement_type: str
    normalized_text: str
    uncertainty: str
    review_state: str
    ocr_warning: bool
    clause_number: str | None
    display_order: int | None
    mandatory: bool | None
    superseded: bool
    created_at: datetime


class RequirementDetail(BaseModel):
    """Full detail view of a requirement with constraints and sources."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_version_id: UUID
    requirement_type: str
    normalized_text: str
    raw_source: str
    uncertainty: str
    review_state: str
    ocr_warning: bool
    clause_number: str | None
    reconciliation_group_id: str | None
    display_order: int | None
    mandatory: bool | None
    superseded: bool
    created_at: datetime
    updated_at: datetime | None
    constraints: list[ConstraintSummary]
    sources: list[RequirementSourceSummary]
    revisions: list[RevisionSummary]
    notes: list[NoteSummary]
    categories: list[CategorySummary]

    @model_validator(mode="after")
    def attach_verbatim_quote(self) -> RequirementDetail:
        """Expose the requirement quote separately from its page text window."""
        for source in self.sources:
            source.quote_text = self.raw_source
        return self


class RequirementListResponse(BaseModel):
    """Paginated list of requirements."""

    model_config = ConfigDict(from_attributes=True)

    items: list[RequirementSummary]
    total: int
    limit: int
    offset: int


class RevisionSummary(BaseModel):
    """A single immutable revision row (CP38)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    previous_normalized_text: str
    updated_at_at_edit: datetime | None
    actor_id: UUID | None
    note: str | None
    created_at: datetime


class EditRequirementRequest(BaseModel):
    """Request body for editing a requirement's normalized text (CP38)."""

    normalized_text: str
    expected_updated_at: datetime | None = None
    note: str | None = None


class AddRequirementFromSourceRequest(BaseModel):
    """Reviewer-confirmed source excerpt from a coverage finding."""

    page_number: int = Field(..., ge=1)
    source_quote: str = Field(..., min_length=1, max_length=2048)
    requirement_type: Literal["obligation", "prohibition", "permission"]

    @field_validator("source_quote")
    @classmethod
    def quote_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_quote must contain non-whitespace text")
        return value


class ReviewCoverageFindingRequest(BaseModel):
    """A reviewer decision tied to one source quote on one page."""

    page_number: int = Field(..., ge=1)
    source_quote: str = Field(..., min_length=1, max_length=2048)
    decision: Literal["covered_by_requirement", "not_in_scope"]
    requirement_id: UUID | None = None
    rationale: str | None = Field(default=None, max_length=2000)

    @field_validator("source_quote")
    @classmethod
    def quote_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_quote must contain non-whitespace text")
        return value

    @model_validator(mode="after")
    def decision_fields_are_consistent(self) -> ReviewCoverageFindingRequest:
        if self.decision == "covered_by_requirement" and self.requirement_id is None:
            raise ValueError("requirement_id is required for covered_by_requirement")
        if self.decision == "not_in_scope" and not (self.rationale or "").strip():
            raise ValueError("A rationale is required for not_in_scope")
        if self.decision == "not_in_scope" and self.requirement_id is not None:
            raise ValueError("requirement_id is only valid for covered_by_requirement")
        return self


class CoverageFindingReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_number: int
    source_quote: str
    source_quote_sha256: str
    decision: str
    rationale: str | None
    requirement_id: UUID | None
    actor_id: UUID | None
    created_at: datetime


async def _coverage_finding_exists(
    session: AsyncSession,
    document_version_id: UUID,
    page_number: int,
    source_quote: str,
) -> bool:
    audits = list(
        (
            await session.execute(
                select(ExtractionWindowAudit).where(
                    ExtractionWindowAudit.document_version_id == document_version_id
                )
            )
        ).scalars().all()
    )
    for audit in audits:
        spans = audit.source_spans if isinstance(audit.source_spans, list) else []
        span_pages = {
            span.get("page_number")
            for span in spans
            if isinstance(span, dict) and isinstance(span.get("page_number"), int)
        }
        omissions = audit.potential_omissions
        if not isinstance(omissions, list):
            continue
        for item in omissions:
            if isinstance(item, dict):
                quote = item.get("source_quote")
                item_page = item.get("page_number")
                candidate_pages = (
                    {item_page} if isinstance(item_page, int) else span_pages
                )
            else:
                quote = item
                candidate_pages = span_pages
            if quote == source_quote and page_number in candidate_pages:
                return True
    return False


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/coverage-reviews",
    response_model=list[CoverageFindingReviewResponse],
)
async def list_coverage_finding_reviews(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[CoverageFindingReviewResponse]:
    """Return latest decisions for findings retained in this version's audit."""
    scoped = await session.execute(
        select(DocumentVersion.id)
        .join(TenderDocument, TenderDocument.id == DocumentVersion.document_id)
        .join(Project, Project.id == TenderDocument.project_id)
        .where(
            Project.id == project_id,
            Project.organization_id == auth.organization_id,
            TenderDocument.id == document_id,
            DocumentVersion.version_number == version_number,
        )
    )
    version_id = scoped.scalar_one_or_none()
    if version_id is None:
        raise HTTPException(status_code=404, detail="Document version not found")

    source_quotes: dict[tuple[int, str], str] = {}
    audits = list(
        (
            await session.execute(
                select(ExtractionWindowAudit).where(
                    ExtractionWindowAudit.document_version_id == version_id
                )
            )
        ).scalars().all()
    )
    for audit in audits:
        spans = audit.source_spans if isinstance(audit.source_spans, list) else []
        span_pages = {
            span.get("page_number")
            for span in spans
            if isinstance(span, dict) and isinstance(span.get("page_number"), int)
        }
        omissions = audit.potential_omissions
        if not isinstance(omissions, list):
            continue
        for item in omissions:
            if isinstance(item, dict):
                quote = item.get("source_quote")
                item_page = item.get("page_number")
                candidate_pages = (
                    {item_page} if isinstance(item_page, int) else span_pages
                )
            else:
                quote = item
                candidate_pages = span_pages
            if isinstance(quote, str):
                digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
                for page_number in candidate_pages:
                    if isinstance(page_number, int):
                        source_quotes[(page_number, digest)] = quote

    reviews = list(
        (
            await session.execute(
                select(CoverageFindingReview)
                .where(CoverageFindingReview.document_version_id == version_id)
                .order_by(
                    CoverageFindingReview.created_at.asc(),
                    CoverageFindingReview.id.asc(),
                )
            )
        ).scalars().all()
    )
    latest: dict[tuple[int, str], CoverageFindingReview] = {}
    for review in reviews:
        identity = (review.page_number, review.source_quote_sha256)
        if identity in source_quotes:
            latest[identity] = review
    return [
        CoverageFindingReviewResponse.model_validate(
            {
                "id": review.id,
                "page_number": review.page_number,
                "source_quote": source_quotes[identity],
                "source_quote_sha256": review.source_quote_sha256,
                "decision": review.decision,
                "rationale": review.rationale,
                "requirement_id": review.requirement_id,
                "actor_id": review.actor_id,
                "created_at": review.created_at,
            }
        )
        for identity, review in sorted(latest.items())
    ]


class CategorySummary(BaseModel):
    """A category in the project category tree (CP39)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    parent_id: UUID | None
    name: str
    display_order: int


class CategoryCreateRequest(BaseModel):
    """Request body for creating a category (CP39)."""

    name: str = Field(..., min_length=1, max_length=256)
    parent_id: UUID | None = None


class NoteSummary(BaseModel):
    """A reviewer note on a requirement (CP39)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requirement_id: UUID
    actor_id: UUID | None
    text: str
    created_at: datetime
    updated_at: datetime | None


class NoteCreateRequest(BaseModel):
    """Request body for adding a reviewer note (CP39)."""

    text: str = Field(..., min_length=1, max_length=2048)


class SplitChildSpec(BaseModel):
    """A single child requirement spec for the split endpoint (CP39)."""

    normalized_text: str
    raw_source: str
    requirement_type: str | None = None
    clause_number: str | None = None
    uncertainty: str | None = None
    ocr_warning: bool | None = None


class SplitRequirementRequest(BaseModel):
    """Request body for splitting a requirement (CP39)."""

    new_requirements: list[SplitChildSpec] = Field(..., min_length=1)


class MergeRequirementRequest(BaseModel):
    """Request body for merging requirements (CP39)."""

    requirement_ids: list[UUID] = Field(..., min_length=2)
    merged_normalized_text: str
    merged_raw_sources: list[str] = Field(..., min_length=2)


class SupersedeRequirementRequest(BaseModel):
    """Request body for superseding a requirement (CP39)."""

    superseded_by: UUID | None = None
    note: str | None = None


class SetMandatoryRequest(BaseModel):
    """Request body for setting the mandatory tri-state flag (CP39)."""

    value: bool | None = None


class CategoryAssignmentRequest(BaseModel):
    """Request body for assigning a category to a requirement (CP39)."""

    category_id: UUID


class ReorderRequirementsRequest(BaseModel):
    """Request body for persisting a new display order (CP39)."""

    order: list[UUID] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements",
    response_model=RequirementListResponse,
    response_model_exclude_none=True,
)
async def list_requirements(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    review_state: RequirementReviewState | None = Query(None),  # noqa: B008
    requirement_type: str | None = Query(None),  # noqa: B008
    search: str | None = Query(None),  # noqa: B008
    include_superseded: bool = Query(default=False),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementListResponse:
    """List requirements for a document version (tenant-scoped).

    Supports filtering by ``review_state`` and ``requirement_type``, a
    case-insensitive ``search`` on normalized/raw text, and stable
    pagination via ``limit``/``offset``.  Results are ordered by creation
    time descending (then by ID for determinism).

    The response never includes full document bodies — only identifiers,
    normalised text, and summary metadata.
    """
    svc = DocumentService(session)
    try:
        items = await svc.list_requirements(
            auth,
            document_id,
            version_number,
            review_state=review_state,
            requirement_type=requirement_type,
            search=search,
            include_superseded=include_superseded,
            limit=limit,
            offset=offset,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Count total with the same filters (separate query for pagination metadata).
    version = await svc.get_version_or_raise(auth, document_id, version_number)
    count_stmt = (
        select(func.count(Requirement.id))
        .where(Requirement.document_version_id == version.id)
    )
    if review_state is not None:
        count_stmt = count_stmt.where(Requirement.review_state == review_state)
    if requirement_type is not None:
        count_stmt = count_stmt.where(Requirement.requirement_type == requirement_type)
    if not include_superseded:
        count_stmt = count_stmt.where(Requirement.superseded.is_(False))
    if search:
        pattern = f"%{search}%"
        count_stmt = count_stmt.where(
            or_(
                Requirement.normalized_text.ilike(pattern),
                Requirement.raw_source.ilike(pattern),
            )
        )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    return RequirementListResponse(
        items=[RequirementSummary.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}",
    response_model=RequirementDetail,
    response_model_exclude_none=True,
)
async def get_requirement_detail(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementDetail:
    """Retrieve a single requirement with its constraints and source anchors.

    The response includes structured constraints (CP33/CP34) and source
    anchors, but **not** the full document body — only identifiers and
    location metadata so the frontend can fetch the exact page on demand.
    """
    svc = DocumentService(session)
    try:
        req = await svc.get_requirement(
            auth, document_id, version_number, requirement_id
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RequirementDetail.model_validate(req)


@router.patch(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}",
    response_model=RequirementDetail,
    response_model_exclude_none=True,
)
async def edit_requirement(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: EditRequirementRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementDetail:
    """Edit a requirement's normalized text with immutable revision history (CP38).

    - ``raw_source`` is **never** modified — only ``normalized_text`` changes.
    - If ``normalized_text`` is unchanged, no revision row is created (no-op).
    - If ``expected_updated_at`` is provided and does not match the current
      ``updated_at``, returns ``409 Conflict`` with the current timestamp
      so the client can refresh and retry.
    - A :class:`RequirementRevision` row capturing the *previous* text is
      created for every material edit.

    Returns the updated requirement with its revision history.
    """
    svc = DocumentService(session)
    try:
        req = await svc.update_requirement_normalized_text(
            auth,
            document_id,
            version_number,
            requirement_id,
            body.normalized_text,
            expected_updated_at=body.expected_updated_at,
            note=body.note,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConcurrentEditError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "concurrent_edit",
                "message": str(exc),
                "current_updated_at": exc.current_updated_at.isoformat()
                if exc.current_updated_at
                else None,
            },
        ) from exc

    await session.commit()
    await session.refresh(req)
    return RequirementDetail.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/from-source",
    response_model=RequirementDetail,
    response_model_exclude_none=True,
    status_code=201,
)
async def add_requirement_from_source(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    body: AddRequirementFromSourceRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementDetail:
    """Add a reviewer-confirmed coverage finding only when its quote is on-page."""
    scoped = await session.execute(
        select(DocumentVersion)
        .join(TenderDocument, TenderDocument.id == DocumentVersion.document_id)
        .join(Project, Project.id == TenderDocument.project_id)
        .where(
            Project.id == project_id,
            Project.organization_id == auth.organization_id,
            TenderDocument.id == document_id,
            DocumentVersion.version_number == version_number,
        )
    )
    version = scoped.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document version not found")

    page = (
        await session.execute(
            select(DocumentPage).where(
                DocumentPage.document_version_id == version.id,
                DocumentPage.page_number == body.page_number,
            )
        )
    ).scalar_one_or_none()
    if page is None or not page.cleaned_text:
        raise HTTPException(status_code=422, detail="The selected page has no verifiable text")
    page_text = page.cleaned_text

    tokens = re.split(r"\s+", body.source_quote.strip())
    quote_pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens))
    matches = list(quote_pattern.finditer(page_text))
    page_metadata = page.structural_metadata or {}
    ocr_derived = bool(
        page.ocr_needed
        or page.ocr_confidence is not None
        or page.ocr_words
        or page_metadata.get("visual_verification_required")
    )
    image_validation: dict[str, object] | None = None
    if not matches:
        if not ocr_derived:
            raise HTTPException(
                status_code=422,
                detail="The excerpt does not match text on the selected page",
            )
        image_validation = await validate_ocr_page_quote_from_image(page, body.source_quote)
        if image_validation.get("status") != "exact":
            raise HTTPException(
                status_code=422,
                detail="The excerpt could not be verified against the rendered OCR page",
            )

    quote_digest = hashlib.sha256(body.source_quote.encode("utf-8")).hexdigest()
    promotion_key = hashlib.sha256(
        f"coverage-source:v2:{version.id}:{quote_digest}".encode()
    ).hexdigest()
    existing = (
        await session.execute(
            select(Requirement)
            .where(
                Requirement.document_version_id == version.id,
                Requirement.promotion_key == promotion_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.superseded:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A matching requirement was superseded; restore or replace it "
                    "before adding this finding"
                ),
            )
        same_page_source = next(
            (
                source
                for source in existing.sources
                if source.page_number == body.page_number
                and source.source_text == body.source_quote
            ),
            None,
        )
        if same_page_source is not None:
            return RequirementDetail.model_validate(existing)

        exact_match = len(matches) == 1 and matches[0].group(0) == body.source_quote
        source = RequirementSource(
            document_version_id=version.id,
            page_number=body.page_number,
            clause_number=None,
            char_start=matches[0].start() if exact_match else None,
            char_end=matches[0].end() if exact_match else None,
            location_type="exact" if exact_match else "approximate",
            source_text=body.source_quote,
            ocr_confidence=page.ocr_confidence,
        )
        existing.sources.append(source)
        if ocr_derived:
            existing.ocr_warning = True
            existing.uncertainty = "uncertain"
            existing.review_state = RequirementReviewState.OCR_WARNING
        await session.flush()
        await write_audit_event(
            session,
            auth,
            "requirement.add_coverage_source",
            entity_type="requirement",
            entity_id=existing.id,
            project_id=project_id,
            metadata={
                "document_version_id": str(version.id),
                "page_number": body.page_number,
                **(
                    {"visual_source_validation": image_validation}
                    if image_validation is not None
                    else {}
                ),
            },
        )
        await session.commit()
        await session.refresh(existing)
        return RequirementDetail.model_validate(existing)

    exact_match = len(matches) == 1 and matches[0].group(0) == body.source_quote
    # ocr_needed is cleared when OCR completes. Persisted OCR confidence or
    # OCR word geometry still identifies OCR-derived text and must retain its
    # uncertainty after successful recognition.
    ocr_warning = ocr_derived
    req = Requirement(
        document_version_id=version.id,
        processing_run_id=None,
        promotion_key=promotion_key,
        requirement_type=body.requirement_type,
        normalized_text=body.source_quote,
        raw_source=body.source_quote,
        uncertainty="uncertain" if ocr_warning else "confirmed",
        clause_number=None,
        ocr_warning=ocr_warning,
        review_state=(
            RequirementReviewState.OCR_WARNING
            if ocr_warning
            else RequirementReviewState.UNREVIEWED
        ),
        sources=[
            RequirementSource(
                document_version_id=version.id,
                page_number=body.page_number,
                clause_number=None,
                char_start=matches[0].start() if exact_match else None,
                char_end=matches[0].end() if exact_match else None,
                location_type="exact" if exact_match else "approximate",
                source_text=body.source_quote,
                ocr_confidence=page.ocr_confidence,
            )
        ],
    )
    session.add(req)
    await session.flush()
    await write_audit_event(
        session,
        auth,
        "requirement.add_from_coverage_finding",
        entity_type="requirement",
        entity_id=req.id,
        project_id=project_id,
        metadata={
            "document_version_id": str(version.id),
            "page_number": body.page_number,
            **(
                {"visual_source_validation": image_validation}
                if image_validation is not None
                else {}
            ),
        },
    )
    await session.commit()
    await session.refresh(req)
    return RequirementDetail.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/coverage-reviews",
    response_model=CoverageFindingReviewResponse,
    status_code=201,
)
async def review_coverage_finding(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    body: ReviewCoverageFindingRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> CoverageFindingReviewResponse:
    """Append a source-verified reviewer decision; prior decisions remain intact."""
    scoped = await session.execute(
        select(DocumentVersion)
        .join(TenderDocument, TenderDocument.id == DocumentVersion.document_id)
        .join(Project, Project.id == TenderDocument.project_id)
        .where(
            Project.id == project_id,
            Project.organization_id == auth.organization_id,
            TenderDocument.id == document_id,
            DocumentVersion.version_number == version_number,
        )
    )
    version = scoped.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document version not found")

    if not await _coverage_finding_exists(
        session,
        version.id,
        body.page_number,
        body.source_quote,
    ):
        raise HTTPException(
            status_code=422,
            detail="The excerpt is not a current coverage finding on the selected page",
        )

    page = (
        await session.execute(
            select(DocumentPage).where(
                DocumentPage.document_version_id == version.id,
                DocumentPage.page_number == body.page_number,
            )
        )
    ).scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="Source page not found")

    page_text = page.cleaned_text or ""
    source_matches = quote_is_present_in_source(page_text, body.source_quote)
    page_metadata = page.structural_metadata or {}
    ocr_derived = bool(
        page.ocr_needed
        or page.ocr_confidence is not None
        or page.ocr_words
        or page_metadata.get("visual_verification_required")
    )
    image_validation: dict[str, object] | None = None
    if not source_matches:
        if not ocr_derived:
            raise HTTPException(
                status_code=422,
                detail="The excerpt does not match text on the selected page",
            )
        image_validation = await validate_ocr_page_quote_from_image(page, body.source_quote)
        if image_validation.get("status") != "exact":
            raise HTTPException(
                status_code=422,
                detail="The excerpt could not be verified against the rendered OCR page",
            )

    if body.decision == "covered_by_requirement":
        assert body.requirement_id is not None
        covered_rows = list(
            (
                await session.execute(
                    select(Requirement, RequirementSource)
                    .join(
                        RequirementSource,
                        RequirementSource.requirement_id == Requirement.id,
                    )
                    .where(
                        Requirement.id == body.requirement_id,
                        Requirement.document_version_id == version.id,
                        Requirement.superseded.is_(False),
                        RequirementSource.document_version_id == version.id,
                        RequirementSource.page_number == body.page_number,
                    )
                )
            ).all()
        )
        if not any(
            quote_is_covered(body.source_quote, [requirement.raw_source])
            for requirement, _source in covered_rows
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "The selected active requirement does not cover this excerpt "
                    "on the selected page"
                ),
            )

    quote_hash = hashlib.sha256(body.source_quote.encode("utf-8")).hexdigest()
    review = CoverageFindingReview(
        document_version_id=version.id,
        page_number=body.page_number,
        source_quote_sha256=quote_hash,
        decision=body.decision,
        rationale=body.rationale.strip() if body.rationale else None,
        requirement_id=body.requirement_id,
        actor_id=auth.actor_id,
    )
    session.add(review)
    await session.flush()
    await write_audit_event(
        session,
        auth,
        "coverage_finding.review",
        entity_type="coverage_finding_review",
        entity_id=review.id,
        project_id=project_id,
        metadata={
            "document_version_id": str(version.id),
            "page_number": body.page_number,
            "source_quote_sha256": quote_hash,
            "decision": body.decision,
            "requirement_id": (
                str(body.requirement_id) if body.requirement_id is not None else None
            ),
            **(
                {"visual_source_validation": image_validation}
                if image_validation is not None
                else {}
            ),
        },
    )
    await session.commit()
    await session.refresh(review)
    return CoverageFindingReviewResponse.model_validate(
        {
            "id": review.id,
            "page_number": review.page_number,
            "source_quote": body.source_quote,
            "source_quote_sha256": review.source_quote_sha256,
            "decision": review.decision,
            "rationale": review.rationale,
            "requirement_id": review.requirement_id,
            "actor_id": review.actor_id,
            "created_at": review.created_at,
        }
    )


# ---------------------------------------------------------------------------
# Requirement structure (CP39)
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/split",
    response_model=list[RequirementSummary],
    response_model_exclude_none=True,
)
async def split_requirement(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: SplitRequirementRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[RequirementSummary]:
    """Split a requirement into multiple children (CP39).

    Creates new requirement rows from each spec in ``new_requirements``,
    marks the original as ``superseded``, and creates ``SPLIT_INTO``
    relations to preserve lineage.  The original's ``raw_source`` is
    never modified.
    """
    svc = DocumentService(session)
    try:
        children = await svc.split_requirement(
            auth,
            document_id,
            version_number,
            requirement_id,
            [s.model_dump() for s in body.new_requirements],
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return [RequirementSummary.model_validate(c) for c in children]


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/merge",
    response_model=RequirementSummary,
    response_model_exclude_none=True,
)
async def merge_requirements(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    body: MergeRequirementRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementSummary:
    """Merge multiple requirements into one (CP39).

    Creates a new requirement whose ``raw_source`` concatenates all
    contributing fragments.  Source requirements are marked
    ``superseded`` and ``MERGED_INTO`` relations are created.
    """
    svc = DocumentService(session)
    try:
        merged = await svc.merge_requirements(
            auth,
            document_id,
            version_number,
            body.requirement_ids,
            body.merged_normalized_text,
            body.merged_raw_sources,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return RequirementSummary.model_validate(merged)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/supersede",
    response_model=RequirementSummary,
    response_model_exclude_none=True,
)
async def supersede_requirement(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: SupersedeRequirementRequest | None = Body(None),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementSummary:
    """Supersede a requirement (auditable soft-delete, CP39).

    Marks the requirement as ``superseded`` (excluded from default
    list/detail queries) and optionally creates a ``SUPERSEDES`` relation
    to a replacement requirement.
    """
    svc = DocumentService(session)
    try:
        req = await svc.supersede_requirement(
            auth,
            document_id,
            version_number,
            requirement_id,
            superseded_by=body.superseded_by if body else None,
            note=body.note if body else None,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return RequirementSummary.model_validate(req)


@router.patch(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/mandatory",
    response_model=RequirementSummary,
    response_model_exclude_none=True,
)
async def set_mandatory(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: SetMandatoryRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementSummary:
    """Set the tri-state mandatory flag on a requirement (CP39)."""
    svc = DocumentService(session)
    try:
        req = await svc.set_requirement_mandatory(
            auth,
            document_id,
            version_number,
            requirement_id,
            body.value,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return RequirementSummary.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/categories",
    response_model=RequirementDetail,
    response_model_exclude_none=True,
)
async def assign_category(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: CategoryAssignmentRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementDetail:
    """Assign a category to a requirement (CP39)."""
    svc = DocumentService(session)
    try:
        req = await svc.assign_category(
            auth,
            document_id,
            version_number,
            requirement_id,
            body.category_id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return RequirementDetail.model_validate(req)


@router.delete(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/categories/{category_id}",
    response_model=RequirementDetail,
    response_model_exclude_none=True,
)
async def unassign_category(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    category_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementDetail:
    """Remove a category assignment from a requirement (CP39)."""
    svc = DocumentService(session)
    try:
        req = await svc.unassign_category(
            auth,
            document_id,
            version_number,
            requirement_id,
            category_id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return RequirementDetail.model_validate(req)


@router.patch(
    "/{project_id}/documents/{document_id}/versions/{version_number}/reorder",
    response_model=list[RequirementSummary],
    response_model_exclude_none=True,
)
async def reorder_requirements(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    body: ReorderRequirementsRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[RequirementSummary]:
    """Persist a new stable sort order for requirements (CP39)."""
    svc = DocumentService(session)
    try:
        reqs = await svc.reorder_requirements(
            auth,
            document_id,
            version_number,
            body.order,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return [RequirementSummary.model_validate(r) for r in reqs]


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/notes",
    response_model=NoteSummary,
    response_model_exclude_none=True,
)
async def add_note(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: NoteCreateRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> NoteSummary:
    """Add a reviewer note to a requirement (CP39)."""
    svc = DocumentService(session)
    try:
        note = await svc.add_note(
            auth,
            document_id,
            version_number,
            requirement_id,
            body.text,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return NoteSummary.model_validate(note)


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/notes",
    response_model=list[NoteSummary],
    response_model_exclude_none=True,
)
async def list_notes(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[NoteSummary]:
    """List reviewer notes for a requirement, new-first (CP39)."""
    svc = DocumentService(session)
    try:
        notes = await svc.get_requirement_notes(
            auth, document_id, version_number, requirement_id
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [NoteSummary.model_validate(n) for n in notes]


# ---------------------------------------------------------------------------
# Category management (CP39)
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/categories",
    response_model=list[CategorySummary],
    response_model_exclude_none=True,
)
async def list_categories(
    project_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[CategorySummary]:
    """List categories for a project, ordered by display_order (CP39)."""
    from tender_compliance_api.db.models import Category as _Cat  # noqa: PLC0415

    result = await session.execute(
        select(_Cat)
        .where(_Cat.project_id == project_id)
        .order_by(_Cat.display_order.asc(), _Cat.name)
    )
    return [CategorySummary.model_validate(c) for c in result.scalars().all()]


# ---------------------------------------------------------------------------
# Review state machine (CP40)
# ---------------------------------------------------------------------------


class ReviewTransitionRequest(BaseModel):
    """Request body for transitioning review state (CP40)."""

    target_state: str
    override_uncertainty: bool = False


class MarkReviewedRequest(BaseModel):
    """Request body for the mark-reviewed shorthand (CP40)."""

    override_uncertainty: bool = False


class ReviewCountsResponse(BaseModel):
    """Real review counts for a document version (CP40)."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    active: int
    unreviewed: int
    reviewed: int
    needs_clarification: int
    ocr_warning: int
    superseded: int


class RequirementTransitionResponse(BaseModel):
    """Response for a review state transition (CP40)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    review_state: str
    updated_at: datetime | None


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/transition",
    response_model=RequirementTransitionResponse,
    response_model_exclude_none=True,
)
async def transition_review_state(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: ReviewTransitionRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementTransitionResponse:
    """Transition a requirement's review state (CP40).

    Validates against the review-state machine:
    UNREVIEWED → {REVIEWED, NEEDS_CLARIFICATION, OCR_WARNING}
    REVIEWED → {UNREVIEWED, NEEDS_CLARIFICATION}
    NEEDS_CLARIFICATION → {UNREVIEWED, REVIEWED, OCR_WARNING}
    OCR_WARNING → {UNREVIEWED, REVIEWED, NEEDS_CLARIFICATION}

    Transitions to REVIEWED while ``uncertainty`` is not ``confirmed`` require
    ``override_uncertainty=true`` (audited).
    """
    try:
        target = RequirementReviewState(body.target_state)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review state: {body.target_state}. "
            f"Valid values: {[s.value for s in RequirementReviewState]}",
        ) from None

    svc = DocumentService(session)
    try:
        req = await svc.transition_review_state(
            auth,
            document_id,
            version_number,
            requirement_id,
            target,
            override_uncertainty=body.override_uncertainty,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
            },
        ) from exc

    await session.commit()
    return RequirementTransitionResponse.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/mark-reviewed",
    response_model=RequirementTransitionResponse,
    response_model_exclude_none=True,
)
async def mark_reviewed(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    body: MarkReviewedRequest | None = Body(None),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementTransitionResponse:
    """Mark a requirement as reviewed (CP40).

    Shorthand for transitioning to ``REVIEWED``. If the requirement's
    uncertainty is not ``confirmed``, pass ``override_uncertainty=true``
    to force the transition (audited).
    """
    override = body.override_uncertainty if body else False
    svc = DocumentService(session)
    try:
        req = await svc.mark_reviewed(
            auth,
            document_id,
            version_number,
            requirement_id,
            override_uncertainty=override,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
            },
        ) from exc
    await session.commit()
    return RequirementTransitionResponse.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/reopen",
    response_model=RequirementTransitionResponse,
    response_model_exclude_none=True,
)
async def reopen_requirement(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementTransitionResponse:
    """Reopen a requirement (transition to UNREVIEWED, CP40)."""
    svc = DocumentService(session)
    try:
        req = await svc.reopen(auth, document_id, version_number, requirement_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
            },
        ) from exc
    await session.commit()
    return RequirementTransitionResponse.model_validate(req)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/requirements/{requirement_id}/escalate",
    response_model=RequirementTransitionResponse,
    response_model_exclude_none=True,
)
async def escalate_requirement(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    requirement_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RequirementTransitionResponse:
    """Escalate a requirement to NEEDS_CLARIFICATION (CP40)."""
    svc = DocumentService(session)
    try:
        req = await svc.escalate(auth, document_id, version_number, requirement_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_transition",
                "message": str(exc),
            },
        ) from exc
    await session.commit()
    return RequirementTransitionResponse.model_validate(req)


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/review-counts",
    response_model=ReviewCountsResponse,
    response_model_exclude_none=True,
)
async def get_review_counts(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ReviewCountsResponse:
    """Compute real review counts for a document version (CP40).

    Returns counts for: total, active (non-superseded), unreviewed,
    reviewed, needs_clarification, ocr_warning, superseded.
    """
    svc = DocumentService(session)
    try:
        counts = await svc.get_project_review_counts(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReviewCountsResponse(**counts)


# ---------------------------------------------------------------------------
# Matrix projection (CP41)
# ---------------------------------------------------------------------------


class MatrixRowResponse(BaseModel):
    """A single matrix row — the canonical Phase 1 projection (CP41).

    Columns: S.No., Requirement ID, Tender Requirement, Category, Clause,
    Source Page, Mandatory, User Notes, Review Status.
    """

    model_config = ConfigDict(from_attributes=True)

    serial: int
    requirement_id: UUID
    tender_requirement: str
    category: str | None
    clause: str | None
    source_page: int | None
    mandatory: bool | None
    user_notes: str | None
    review_status: str

    normalized_text: str
    raw_source: str
    uncertainty: str
    ocr_warning: bool


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/matrix",
    response_model=list[MatrixRowResponse],
    response_model_exclude_none=True,
)
async def get_matrix(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[MatrixRowResponse]:
    """Return the canonical Phase 1 matrix projection (CP41).

    Excludes superseded requirements.  Preserves explicit ``display_order``
    (NULLs sort last), falling back to ``created_at`` desc then ``id``.
    Missing source fields are represented honestly as null.
    """
    svc = DocumentService(session)
    try:
        rows = await svc.get_matrix_rows(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [MatrixRowResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Final compliance matrix projection (CP59)
# ---------------------------------------------------------------------------


class FinalMatrixRowResponse(BaseModel):
    """A single row in the final (Phase 2) compliance matrix (CP59).

    Extends the Phase 1 columns with vendor response/specification,
    evidence, assessment, and review-state summary fields.
    """

    model_config = ConfigDict(from_attributes=True)

    # --- Phase 1 columns ---
    serial: int
    requirement_id: UUID
    tender_requirement: str
    category: str | None
    clause: str | None
    source_page: int | None
    source_anchor_id: UUID | None = None
    mandatory: bool | None
    user_notes: str | None
    review_status: str
    normalized_text: str
    raw_source: str
    uncertainty: str
    ocr_warning: bool

    # --- Phase 2: Evidence + Vendor Spec ---
    evidence_id: UUID | None
    evidence_score: float | None
    evidence_oem_document: str | None
    evidence_oem_version: int | None

    # --- Phase 2: Vendor Spec ---
    vendor_spec_parameter: str | None
    vendor_spec_value: float | None
    vendor_spec_unit: str | None
    vendor_spec_lower_bound: float | None
    vendor_spec_upper_bound: float | None
    vendor_spec_source_text: str | None
    vendor_spec_source_page: int | None
    vendor_spec_extraction_method: str | None
    vendor_spec_issues: list[str] | None

    # --- Phase 2: Assessment ---
    assessment_status: str | None
    assessment_suggested_status: str | None
    assessment_reason_code: str | None
    assessment_reason_text: str | None
    assessment_is_confirmed: bool | None
    assessment_reviewer_id: UUID | None
    assessment_reviewed_at: datetime | None
    assessment_version: int | None

    # --- Phase 2: Review state summary ---
    has_unresolved_conflict: bool
    clarification_statuses: list[str]
    deviation_statuses: list[str]


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/final-matrix",
    response_model=list[FinalMatrixRowResponse],
    response_model_exclude_none=True,
)
async def get_final_matrix(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[FinalMatrixRowResponse]:
    """Return the final (Phase 2) compliance matrix projection (CP59).

    Keeps the original Phase 1 tender columns and layers on vendor response,
    evidence citation, assessment status, conflict/clarification/deviation
    state, and reviewer metadata.  Unresolved requirements remain visible.
    """
    svc = DocumentService(session)
    try:
        rows = await svc.get_final_matrix_rows(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [FinalMatrixRowResponse.model_validate(r) for r in rows]


class ExportArtifactResponse(BaseModel):
    """Metadata for an export artifact (CP42)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_version_id: UUID
    stored_object_id: UUID | None
    actor_id: UUID | None
    status: str
    error_message: str | None
    requirement_count: int
    workbook_sha256: str
    generated_at: datetime | None
    export_format: str | None = None
    validation_status: str = "not_run"
    validation_report: dict[str, Any] | None = None

    @field_validator("error_message", mode="before")
    @classmethod
    def hide_raw_error_message(cls, value: str | None) -> str | None:
        """Redact raw error text from historical and newly stored records."""
        return EXPORT_FAILURE if value else None


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/exports",
    response_model=ExportArtifactResponse,
    response_model_exclude_none=True,
)
async def create_export(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ExportArtifactResponse:
    """Generate a matrix XLSX export for a document version (CP42).

    Uses the canonical matrix projection.  The workbook is stored in object
    storage and an audit event is logged.  If generation fails, a FAILED
    artifact is recorded and the error is propagated.
    """
    svc = DocumentService(session)
    try:
        artifact = await svc.export_matrix(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        # The service already recorded a FAILED artifact and audit event.
        # Find the most recent failed artifact for this version.
        result = await session.execute(
            select(ExportArtifact)
            .where(
                ExportArtifact.document_version_id == (
                    select(DocumentVersion.id)
                    .where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.version_number == version_number,
                    )
                ),
                ExportArtifact.status == ExportStatus.FAILED,
            )
            .order_by(ExportArtifact.generated_at.desc())
            .limit(1)
        )
        failing_artifact = result.scalar_one_or_none()
        if failing_artifact is None:
            log_event(
                logger,
                logging.ERROR,
                "matrix_export_failed_without_artifact",
                correlation_id=get_correlation_id(),
                operation="matrix_export",
                error_type=type(exc).__name__,
                error_category=error_category(exc),
            )
            raise HTTPException(
                status_code=500,
                detail=EXPORT_FAILURE,
            ) from None
        await session.commit()
        return ExportArtifactResponse.model_validate(failing_artifact)

    await session.commit()
    return ExportArtifactResponse.model_validate(artifact)


@router.post(
    "/{project_id}/documents/{document_id}/versions/{version_number}/final-matrix/exports",
    response_model=ExportArtifactResponse,
    response_model_exclude_none=True,
)
async def create_final_matrix_export(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    fmt: ExportFormat = Query(  # noqa: B008
        default=ExportFormat.XLSX,
        description="Export format: xlsx, docx, or pdf",
    ),
    template: Literal["vendor-response"] | None = Query(  # noqa: B008
        default=None,
        description="Use the blank tender-derived vendor response template (DOCX only).",
    ),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ExportArtifactResponse:
    """Generate a final-matrix export or tender response template (CP60/CP68).

    Uses the canonical final matrix projection (CP59).  Supports XLSX, DOCX,
    and PDF formats.  The artifact is stored immutably in object storage and
    an audit event is logged. The optional vendor-response template uses the
    canonical Phase 1 requirements and is available as DOCX only. If generation
    fails, a FAILED artifact is recorded and the error is propagated.
    """
    if template is not None and fmt != ExportFormat.DOCX:
        raise HTTPException(
            status_code=422,
            detail="The vendor response template is available as DOCX only",
        )
    svc = DocumentService(session)
    try:
        artifact = await svc.export_final_matrix(
            auth,
            document_id,
            version_number,
            export_format=fmt,
            vendor_response_template=template == "vendor-response",
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        result = await session.execute(
            select(ExportArtifact)
            .where(
                ExportArtifact.document_version_id == (
                    select(DocumentVersion.id)
                    .where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.version_number == version_number,
                    )
                ),
                ExportArtifact.status == ExportStatus.FAILED,
                ExportArtifact.export_format == fmt,
            )
            .order_by(ExportArtifact.generated_at.desc())
            .limit(1)
        )
        failing_artifact = result.scalar_one_or_none()
        if failing_artifact is None:
            log_event(
                logger,
                logging.ERROR,
                "final_matrix_export_failed_without_artifact",
                correlation_id=get_correlation_id(),
                operation="final_matrix_export",
                error_type=type(exc).__name__,
                error_category=error_category(exc),
            )
            raise HTTPException(
                status_code=500,
                detail=EXPORT_FAILURE,
            ) from None
        await session.commit()
        return ExportArtifactResponse.model_validate(failing_artifact)

    await session.commit()
    return ExportArtifactResponse.model_validate(artifact)


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/exports",
    response_model=list[ExportArtifactResponse],
    response_model_exclude_none=True,
)
async def list_exports(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ExportArtifactResponse]:
    """List export artifacts for a document version (CP42)."""
    svc = DocumentService(session)
    try:
        artifacts = await svc.get_exports(auth, document_id, version_number)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [ExportArtifactResponse.model_validate(a) for a in artifacts]


@router.get(
    "/{project_id}/documents/{document_id}/versions/{version_number}/exports/{export_id}",
    response_class=Response,
    name="download_export",
)
async def download_export(
    project_id: UUID,
    document_id: UUID,
    version_number: int,
    export_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Any:
    """Download a completed XLSX/DOCX/PDF export with truthful HTTP metadata."""
    svc = DocumentService(session)
    try:
        workbook_bytes = await svc.download_export(
            auth, document_id, version_number, export_id
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "export_download_failed",
            correlation_id=get_correlation_id(),
            operation="export_download",
            error_type=type(exc).__name__,
            error_category=error_category(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=EXPORT_FAILURE,
        ) from None

    artifact = await session.get(ExportArtifact, export_id)
    export_format = (
        artifact.export_format.value
        if artifact is not None and artifact.export_format is not None
        else ExportFormat.XLSX.value
    )
    media_types = {
        ExportFormat.XLSX.value: (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        ExportFormat.DOCX.value: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ExportFormat.PDF.value: "application/pdf",
    }
    filenames = {
        ExportFormat.XLSX.value: "tender_compliance_export.xlsx",
        ExportFormat.DOCX.value: "tender_compliance_export.docx",
        ExportFormat.PDF.value: "tender_compliance_export.pdf",
    }
    filename = filenames.get(export_format, "tender_compliance_export.bin")
    return Response(
        content=workbook_bytes,
        media_type=media_types.get(export_format, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
