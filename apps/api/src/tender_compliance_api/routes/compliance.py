"""Compliance assessment API routes (CP54).

Endpoints:
* ``POST /projects/{project_id}/requirements/{requirement_id}/assess``
  — run deterministic assessment for a requirement.
* ``GET  /projects/{project_id}/compliance-assessments``
  — list assessments for a project (latest version per requirement).
* ``GET  /projects/{project_id}/requirements/{requirement_id}/compliance-assessment``
  — get the latest assessment for a specific requirement.
* ``POST /projects/{project_id}/compliance-assessments/{assessment_id}/confirm``
  — confirm an assessment as final human review.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.compliance.service import ComplianceAssessmentService
from tender_compliance_api.db.models import ComplianceAssessment, ComplianceStatus
from tender_compliance_api.db.session import get_session

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["compliance"],
)


class ComparisonResultResponse(BaseModel):
    """The stored ComparisonResult details from CP53."""

    model_config = ConfigDict(from_attributes=True)

    verdict: str | None = None
    tender_text: str | None = None
    vendor_text: str | None = None
    comparison_rule: str | None = None
    conversion: str | None = None
    reasons: list[str] | None = None
    tender_value: float | None = None
    vendor_value: float | None = None
    tender_unit: str | None = None
    vendor_unit: str | None = None
    normalized_tender_value: float | None = None
    normalized_vendor_value: float | None = None
    details: dict[str, Any] | None = None


class ComplianceAssessmentResponse(BaseModel):
    """A compliance assessment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    evidence_id: uuid.UUID | None = None
    vendor_spec_id: uuid.UUID | None = None
    suggested_status: ComplianceStatus
    status: ComplianceStatus
    reason_code: str
    reason_text: str | None = None
    comparison_result: ComparisonResultResponse | None = None
    assessment_version: int
    is_confirmed_by_human: bool
    reviewer_id: uuid.UUID | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str


def _model_to_response(model: ComplianceAssessment) -> ComplianceAssessmentResponse:
    """Convert a ComplianceAssessment ORM model to its response schema."""

    comparison_data = (
        model.comparison_result_json if isinstance(model.comparison_result_json, dict) else None
    )

    return ComplianceAssessmentResponse(
        id=model.id,
        project_id=model.project_id,
        requirement_id=model.requirement_id,
        evidence_id=model.evidence_id,
        vendor_spec_id=model.vendor_spec_id,
        suggested_status=model.suggested_status,
        status=model.status,
        reason_code=model.reason_code,
        reason_text=model.reason_text,
        comparison_result=ComparisonResultResponse(**(comparison_data or {})),
        assessment_version=model.assessment_version,
        is_confirmed_by_human=model.is_confirmed_by_human,
        reviewer_id=model.reviewer_id,
        reviewed_at=(
            model.reviewed_at.isoformat() if model.reviewed_at else None
        ),
        created_at=model.created_at.isoformat(),
        updated_at=model.updated_at.isoformat(),
    )


@router.post(
    "/requirements/{requirement_id}/assess",
    response_model=ComplianceAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assess_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ComplianceAssessmentResponse:
    """Run a deterministic compliance assessment for one requirement."""

    service = ComplianceAssessmentService(session)
    assessment = await service.assess_requirement(
        auth=auth,
        project_id=project_id,
        requirement_id=requirement_id,
    )
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requirement {requirement_id} not found in project {project_id}",
        )
    return _model_to_response(assessment)


@router.get(
    "/compliance-assessments",
    response_model=list[ComplianceAssessmentResponse],
)
async def list_assessments(
    project_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ComplianceAssessmentResponse]:
    """List all assessments for a project, latest version per requirement."""

    service = ComplianceAssessmentService(session)
    assessments = await service.list_assessments(auth=auth, project_id=project_id)
    return [_model_to_response(a) for a in assessments]


@router.get(
    "/requirements/{requirement_id}/compliance-assessment",
    response_model=ComplianceAssessmentResponse | None,
)
async def get_latest_assessment(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ComplianceAssessmentResponse | None:
    """Get the latest compliance assessment for a specific requirement."""

    service = ComplianceAssessmentService(session)
    assessment = await service.get_latest_assessment(
        auth=auth, project_id=project_id, requirement_id=requirement_id
    )
    if assessment is None:
        return None
    return _model_to_response(assessment)


@router.post(
    "/compliance-assessments/{assessment_id}/confirm",
    response_model=ComplianceAssessmentResponse,
)
async def confirm_assessment(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ComplianceAssessmentResponse:
    """Confirm an assessment as final human review."""

    service = ComplianceAssessmentService(session)
    assessment = await service.confirm_assessment(auth=auth, assessment_id=assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )
    return _model_to_response(assessment)
