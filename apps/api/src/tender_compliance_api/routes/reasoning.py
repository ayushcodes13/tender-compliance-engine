"""Evidence-backed qualitative reasoning API routes (CP55).

Endpoints:
* ``POST /projects/{id}/requirements/{rid}/qualitative-assess``
  — run source-bounded qualitative reasoning for a requirement.
* ``GET  /projects/{id}/requirements/{rid}/qualitative-assessment``
  — get the latest qualitative assessment for a requirement.
* ``GET  /projects/{id}/qualitative-assessments``
  — list all qualitative assessments for a project.
* ``POST /projects/{id}/qualitative-assessments/{aid}/confirm``
  — confirm a qualitative assessment as final human review.

All reasoning is source-bounded: the service only consults the verbatim
source texts of accepted evidence items — never the full OEM document body.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.compliance.reasoning import (
    QualitativeReasoningService,
)
from tender_compliance_api.db.models import QualitativeAssessment
from tender_compliance_api.db.session import get_session

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["qualitative"],
)


class AttributionMismatchResponse(BaseModel):
    """An attribution/scope mismatch between requirement and evidence."""

    model_config = ConfigDict(from_attributes=True)

    field: str
    requirement_value: str | None = None
    evidence_value: str | None = None
    detail: str


class QualitativeAssessmentResponse(BaseModel):
    """A qualitative assessment result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    evidence_id: uuid.UUID | None = None
    compliance_assessment_id: uuid.UUID | None = None
    verdict: str
    reason_code: str
    reason_text: str | None = None
    attribution_mismatches: list[AttributionMismatchResponse] = []
    evidence_ids: list[str] = []
    source_contradiction: bool = False
    model_version: str
    prompt_version: str
    reasoning_version: str
    assessment_version: int
    is_confirmed_by_human: bool = False
    reviewer_id: uuid.UUID | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str | None = None


def _to_response(model: QualitativeAssessment) -> QualitativeAssessmentResponse:
    """Convert a QualitativeAssessment ORM model to its response schema."""

    attr_mismatches = []
    if model.attribution_mismatches:
        for am in model.attribution_mismatches:
            if isinstance(am, dict):
                attr_mismatches.append(
                    AttributionMismatchResponse(
                        field=am.get("field", ""),
                        requirement_value=am.get("requirement_value"),
                        evidence_value=am.get("evidence_value"),
                        detail=am.get("detail", ""),
                    )
                )

    evidence_ids = []
    if model.evidence_ids:
        evidence_ids = [str(eid) for eid in model.evidence_ids]

    return QualitativeAssessmentResponse(
        id=model.id,
        project_id=model.project_id,
        requirement_id=model.requirement_id,
        evidence_id=model.evidence_id,
        compliance_assessment_id=model.compliance_assessment_id,
        verdict=model.verdict.value,
        reason_code=model.reason_code,
        reason_text=model.reason_text,
        attribution_mismatches=attr_mismatches,
        evidence_ids=evidence_ids,
        source_contradiction=model.source_contradiction,
        model_version=model.model_version,
        prompt_version=model.prompt_version,
        reasoning_version=model.reasoning_version,
        assessment_version=model.assessment_version,
        is_confirmed_by_human=model.is_confirmed_by_human,
        reviewer_id=model.reviewer_id,
        reviewed_at=(
            model.reviewed_at.isoformat() if model.reviewed_at else None
        ),
        created_at=model.created_at.isoformat() if model.created_at else "",
        updated_at=(
            model.updated_at.isoformat() if model.updated_at else None
        ),
    )


@router.post(
    "/requirements/{requirement_id}/qualitative-assess",
    response_model=QualitativeAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assess_qualitative(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    evidence_id: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> QualitativeAssessmentResponse:
    """Run source-bounded qualitative reasoning for one requirement.

    The reasoner consults only the verbatim source texts of accepted
    evidence items — never the full OEM document body.  If a deterministic
    numeric comparison (CP53) already exists, its verdict is mirrored
    rather than re-evaluated.
    """

    service = QualitativeReasoningService(session)
    assessment = await service.assess_qualitative(
        auth=auth,
        project_id=project_id,
        requirement_id=requirement_id,
        evidence_id=evidence_id,
    )
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requirement {requirement_id} not found in project {project_id}",
        )
    return _to_response(assessment)


@router.get(
    "/requirements/{requirement_id}/qualitative-assessment",
    response_model=QualitativeAssessmentResponse | None,
)
async def get_latest_qualitative_assessment(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> QualitativeAssessmentResponse | None:
    """Get the latest qualitative assessment for a specific requirement."""

    service = QualitativeReasoningService(session)
    assessment = await service.get_latest_assessment(
        auth=auth, project_id=project_id, requirement_id=requirement_id
    )
    if assessment is None:
        return None
    return _to_response(assessment)


@router.get(
    "/qualitative-assessments",
    response_model=list[QualitativeAssessmentResponse],
)
async def list_qualitative_assessments(
    project_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[QualitativeAssessmentResponse]:
    """List all qualitative assessments for a project (tenant-scoped)."""

    service = QualitativeReasoningService(session)
    assessments = await service.list_assessments(
        auth=auth, project_id=project_id
    )
    return [_to_response(a) for a in assessments]


@router.post(
    "/qualitative-assessments/{assessment_id}/confirm",
    response_model=QualitativeAssessmentResponse,
)
async def confirm_qualitative_assessment(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> QualitativeAssessmentResponse:
    """Confirm a qualitative assessment as final human review."""

    service = QualitativeReasoningService(session)
    assessment = await service.confirm_assessment(
        auth=auth, assessment_id=assessment_id
    )
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Qualitative assessment {assessment_id} not found",
        )
    return _to_response(assessment)
