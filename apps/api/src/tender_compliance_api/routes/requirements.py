"""Requirement list/detail API routes (CP35).

Tenant-scoped endpoints for listing and inspecting requirements within a
specific document version.  All routes are authorized via
:class:`AuthContext` (organization-scoped) and further restricted to the
document version's project.

Response schemas are explicit Pydantic models — never raw ORM objects on the
wire — and never include full document bodies (guardrail from CP35).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    Requirement,
    RequirementReviewState,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document import DocumentNotFoundError, DocumentService

router = APIRouter(prefix="/projects", tags=["requirements"])


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
    created_at: datetime
    constraints: list[ConstraintSummary]
    sources: list[RequirementSourceSummary]


class RequirementListResponse(BaseModel):
    """Paginated list of requirements."""

    model_config = ConfigDict(from_attributes=True)

    items: list[RequirementSummary]
    total: int
    limit: int
    offset: int


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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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
