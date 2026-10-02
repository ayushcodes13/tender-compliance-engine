"""CP57 — Missing evidence, clarification questions, and deviations API routes.

Endpoints:
- POST /projects/{project_id}/clarifications  — create a clarification request
- POST /projects/{project_id}/requirements/{req_id}/clarifications/auto
       — auto-generate clarifications for a requirement
- GET  /projects/{project_id}/clarifications — list
- GET  /projects/{project_id}/clarifications/{id} — get one
- PATCH /projects/{project_id}/clarifications/{id} — edit question/context (PENDING only)
- POST /projects/{project_id}/clarifications/{id}/answer — answer
- POST /projects/{project_id}/deviations — create a deviation
- GET  /projects/{project_id}/deviations — list
- POST /projects/{project_id}/deviations/{id}/review — review
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.compliance.missing_evidence import (
    ClarificationContext,
    MissingEvidenceService,
)
from tender_compliance_api.db.models import (
    ClarificationStatus,
    DeviationStatus,
    DeviationType,
)
from tender_compliance_api.db.session import get_session

router = APIRouter(
    prefix="/api/projects",
    tags=["missing-evidence"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ClarificationContextSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reason: str
    parameter: str | None = None
    conflict_id: str | None = None
    evidence_ids: list[str] | None = None
    detail: str | None = None


class ClarificationRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID | None
    question: str
    context: dict[str, Any]
    status: str
    related_evidence_ids: list[str] | None
    related_conflict_ids: list[str] | None
    asked_by: uuid.UUID | None
    asked_at: datetime
    answer: str | None
    answered_by: uuid.UUID | None
    answered_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class CreateClarificationRequest(BaseModel):
    question: str
    context: ClarificationContextSchema
    requirement_id: uuid.UUID | None = None
    related_evidence_ids: list[str] | None = None
    related_conflict_ids: list[str] | None = None


class AnswerClarificationRequest(BaseModel):
    answer: str


class UpdateClarificationRequest(BaseModel):
    """Partial update of a clarification request's question/context.

    Allows a human reviewer to edit an auto-generated clarification question
    before it is sent to the OEM/customer.  Fields that are ``None`` are
    not modified.
    """
    question: str | None = None
    context: dict[str, Any] | None = None


class DeviationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    deviation_type: str
    original_requirement: str
    proposed_alternative: str | None
    rationale: str | None
    status: str
    proposed_by: uuid.UUID | None
    proposed_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime | None


class CreateDeviationRequest(BaseModel):
    requirement_id: uuid.UUID
    deviation_type: DeviationType
    original_requirement: str
    proposed_alternative: str | None = None
    rationale: str | None = None


class ReviewDeviationRequest(BaseModel):
    status: DeviationStatus
    review_notes: str | None = None

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _get_service(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
) -> MissingEvidenceService:
    return MissingEvidenceService(db=session, audit=AuditService(session))


# ---------------------------------------------------------------------------
# Endpoints — Clarifications
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/clarifications",
    response_model=ClarificationRequestSchema,
    summary="Create a clarification request",
)
async def create_clarification(
    project_id: uuid.UUID,
    req: CreateClarificationRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> ClarificationRequestSchema:
    try:
        cr = await service.create_clarification(
            auth=auth,
            project_id=project_id,
            question=req.question,
            context=ClarificationContext(
                reason=req.context.reason,
                parameter=req.context.parameter,
                conflict_id=req.context.conflict_id,
                evidence_ids=req.context.evidence_ids,
                detail=req.context.detail,
            ),
            requirement_id=req.requirement_id,
            related_evidence_ids=req.related_evidence_ids,
            related_conflict_ids=req.related_conflict_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return ClarificationRequestSchema.model_validate(cr)


@router.post(
    "/{project_id}/requirements/{requirement_id}/clarifications/auto",
    response_model=list[ClarificationRequestSchema],
    summary="Auto-generate clarification requests for a requirement",
)
async def auto_generate_clarifications(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> list[ClarificationRequestSchema]:
    try:
        created = await service.auto_generate_clarifications(
            auth=auth,
            project_id=project_id,
            requirement_id=requirement_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return [ClarificationRequestSchema.model_validate(cr) for cr in created]


@router.get(
    "/{project_id}/clarifications",
    response_model=list[ClarificationRequestSchema],
    summary="List clarification requests for a project",
)
async def list_clarifications(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID | None = None,
    status: ClarificationStatus | None = None,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> list[ClarificationRequestSchema]:
    results = await service.list_clarifications(
        auth=auth,
        project_id=project_id,
        requirement_id=requirement_id,
        status=status,
    )
    return [ClarificationRequestSchema.model_validate(cr) for cr in results]


@router.get(
    "/{project_id}/clarifications/{clarification_id}",
    response_model=ClarificationRequestSchema,
    summary="Get a single clarification request",
)
async def get_clarification(
    project_id: uuid.UUID,
    clarification_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> ClarificationRequestSchema:
    cr = await service.get_clarification(
        auth=auth,
        project_id=project_id,
        clarification_id=clarification_id,
    )
    if cr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clarification {clarification_id} not found in project "
            f"{project_id}",
        )
    return ClarificationRequestSchema.model_validate(cr)


@router.post(
    "/{project_id}/clarifications/{clarification_id}/answer",
    response_model=ClarificationRequestSchema,
    summary="Answer a clarification request",
)
async def answer_clarification(
    project_id: uuid.UUID,
    clarification_id: uuid.UUID,
    req: AnswerClarificationRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> ClarificationRequestSchema:
    try:
        cr = await service.answer_clarification(
            auth=auth,
            project_id=project_id,
            clarification_id=clarification_id,
            answer=req.answer,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if cr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clarification {clarification_id} not found in project "
            f"{project_id}",
        )
    return ClarificationRequestSchema.model_validate(cr)


@router.patch(
    "/{project_id}/clarifications/{clarification_id}",
    response_model=ClarificationRequestSchema,
    summary="Edit a clarification request's question text and/or context",
)
async def edit_clarification(
    project_id: uuid.UUID,
    clarification_id: uuid.UUID,
    req: UpdateClarificationRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> ClarificationRequestSchema:
    """Edit a PENDING clarification request.

    ANSWERED clarifications are locked and cannot be edited.  Tenant
    isolation is enforced — a 404 is returned if the clarification does
    not belong to the authenticated organization's project.
    """
    try:
        cr = await service.edit_clarification(
            auth=auth,
            project_id=project_id,
            clarification_id=clarification_id,
            question=req.question,
            context=req.context,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if cr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Clarification {clarification_id} not found in project "
            f"{project_id}",
        )
    return ClarificationRequestSchema.model_validate(cr)


# ---------------------------------------------------------------------------
# Endpoints — Deviations
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/deviations",
    response_model=DeviationSchema,
    summary="Create a deviation proposal",
)
async def create_deviation(
    project_id: uuid.UUID,
    req: CreateDeviationRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> DeviationSchema:
    try:
        dev = await service.create_deviation(
            auth=auth,
            project_id=project_id,
            requirement_id=req.requirement_id,
            deviation_type=req.deviation_type,
            original_requirement=req.original_requirement,
            proposed_alternative=req.proposed_alternative,
            rationale=req.rationale,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return DeviationSchema.model_validate(dev)


@router.get(
    "/{project_id}/deviations",
    response_model=list[DeviationSchema],
    summary="List deviation proposals for a project",
)
async def list_deviations(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID | None = None,
    status: DeviationStatus | None = None,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> list[DeviationSchema]:
    results = await service.list_deviations(
        auth=auth,
        project_id=project_id,
        requirement_id=requirement_id,
        status=status,
    )
    return [DeviationSchema.model_validate(d) for d in results]


@router.post(
    "/{project_id}/deviations/{deviation_id}/review",
    response_model=DeviationSchema,
    summary="Review a deviation (ACCEPTED or REJECTED)",
)
async def review_deviation(
    project_id: uuid.UUID,
    deviation_id: uuid.UUID,
    req: ReviewDeviationRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: MissingEvidenceService = Depends(_get_service),  # noqa: B008
) -> DeviationSchema:
    try:
        dev = await service.review_deviation(
            auth=auth,
            project_id=project_id,
            deviation_id=deviation_id,
            status=req.status,
            review_notes=req.review_notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if dev is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deviation {deviation_id} not found in project "
            f"{project_id}",
        )
    return DeviationSchema.model_validate(dev)
