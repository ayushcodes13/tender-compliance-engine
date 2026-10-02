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
* ``POST /projects/{project_id}/compliance-assessments/{assessment_id}/override``
  — override status with reason (CP58, new version, append-only).
* ``POST /projects/{project_id}/compliance-assessments/{assessment_id}/reopen``
  — reopen a confirmed assessment (CP58).
* ``POST /projects/{project_id}/compliance-assessments/{assessment_id}/comments``
  — add a reviewer comment (CP58).
* ``GET  /projects/{project_id}/compliance-assessments/{assessment_id}/comments``
  — list comments (CP58).
* ``GET  /projects/{project_id}/requirements/{requirement_id}/review``
  — combined review view: assessment + conflicts + clarifications +
    deviations (CP58).
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
from tender_compliance_api.db.models import (
    AssessmentCommentType,
    ComplianceAssessment,
    ComplianceStatus,
)
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


# ---------------------------------------------------------------------------
# CP58 — Human review: override, reopen, comments, combined review view
# ---------------------------------------------------------------------------


class AssessmentCommentResponse(BaseModel):
    """A reviewer comment on a compliance assessment version (CP58)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    project_id: uuid.UUID
    author_id: uuid.UUID | None = None
    comment_type: str
    comment: str
    assessment_version: int
    created_at: str


class OverrideAssessmentRequest(BaseModel):
    """Human override of a system assessment status."""

    status: ComplianceStatus
    reason: str
    evidence_id: uuid.UUID | None = None


class CreateCommentRequest(BaseModel):
    comment: str
    comment_type: AssessmentCommentType = AssessmentCommentType.COMMENT


@router.post(
    "/compliance-assessments/{assessment_id}/override",
    response_model=ComplianceAssessmentResponse,
    summary="Override a system assessment with a human-decided status",
)
async def override_assessment(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    req: OverrideAssessmentRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ComplianceAssessmentResponse:
    """Create a new assessment version with a human-overridden status.

    The original assessment row is preserved (append-only).  The override
    reason is recorded as an audit comment and in the assessment's
    ``reason_text``.
    """
    service = ComplianceAssessmentService(session)
    try:
        assessment = await service.override_assessment(
            auth=auth,
            project_id=project_id,
            assessment_id=assessment_id,
            status=req.status,
            reason=req.reason,
            evidence_id=req.evidence_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found in project "
            f"{project_id}",
        )
    return _model_to_response(assessment)


@router.post(
    "/compliance-assessments/{assessment_id}/reopen",
    response_model=ComplianceAssessmentResponse,
    summary="Reopen a confirmed assessment for re-review",
)
async def reopen_assessment(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    req: CreateCommentRequest | None = None,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ComplianceAssessmentResponse:
    """Create a new assessment version reverting to the unconfirmed state.

    The original confirmed row is preserved (append-only).  An optional reason
    can be provided via the request body.
    """
    service = ComplianceAssessmentService(session)
    reason = req.comment if req is not None else None
    assessment = await service.reopen_assessment(
        auth=auth,
        project_id=project_id,
        assessment_id=assessment_id,
        reason=reason,
    )
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found in project "
            f"{project_id}",
        )
    return _model_to_response(assessment)


@router.post(
    "/compliance-assessments/{assessment_id}/comments",
    response_model=AssessmentCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a reviewer comment to an assessment",
)
async def add_comment(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    req: CreateCommentRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AssessmentCommentResponse:
    """Add a comment to an assessment (tenant-scoped, append-only)."""
    service = ComplianceAssessmentService(session)
    comment = await service.add_comment(
        auth=auth,
        project_id=project_id,
        assessment_id=assessment_id,
        comment=req.comment,
        comment_type=req.comment_type,
    )
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found in project "
            f"{project_id}",
        )
    return AssessmentCommentResponse.model_validate(comment)


@router.get(
    "/compliance-assessments/{assessment_id}/comments",
    response_model=list[AssessmentCommentResponse],
    summary="List comments for an assessment",
)
async def list_comments(
    project_id: uuid.UUID,
    assessment_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[AssessmentCommentResponse]:
    """List all comments for an assessment, tenant-scoped."""
    service = ComplianceAssessmentService(session)
    comments = await service.list_comments(
        auth=auth, project_id=project_id, assessment_id=assessment_id,
    )
    return [AssessmentCommentResponse.model_validate(c) for c in comments]


@router.get(
    "/requirements/{requirement_id}/review",
    response_model=dict[str, Any],
    summary="Combined review state for a requirement (assessment, conflicts, "
    "clarifications, deviations)",
)
async def get_requirement_review(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Return the latest assessment, comparison details, and all related
    conflicts (CP56), clarifications (CP57), and deviations (CP57) for a
    requirement — everything a human reviewer needs in one call.
    """
    service = ComplianceAssessmentService(session)
    review = await service.get_requirement_review(
        auth=auth,
        project_id=project_id,
        requirement_id=requirement_id,
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No assessment found for requirement "
            f"{requirement_id} in project {project_id}",
        )
    return review
