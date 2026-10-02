"""Submission approval/lock routes (CP61).

State machine: DRAFT → LOCKED → APPROVED → REVOKED

Each route is tenant-scoped via :class:`AuthContext`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import DocumentService
from tender_compliance_api.submission.service import (
    SubmissionNotFoundError,
    SubmissionService,
    SubmissionStateError,
)

router = APIRouter(
    prefix="/projects/{project_id}/submissions",
    tags=["submissions"],
)


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    document_version_id: uuid.UUID
    version_number: int
    status: str
    approver_id: uuid.UUID | None
    approved_at: datetime | None
    assessment_snapshot: list[dict[str, Any]]
    matrix_sha256: str
    matrix_export_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime | None
    updated_at: datetime | None


def _svc(session: AsyncSession, project_id: uuid.UUID) -> SubmissionService:
    return SubmissionService(session, project_id)


@router.post(
    "/{document_id}/versions/{version_number}",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def create_submission(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    version_number: int,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SubmissionResponse:
    """Create a new DRAFT submission snapshot for a document version (CP61).

    Snapshots the current final-matrix state (requirement IDs, assessment
    statuses, evidence links).  The SHA-256 of the assessment snapshot is
    computed by the service.
    """
    svc = _svc(session, project_id)
    doc_svc = DocumentService(session)
    try:
        rows = await doc_svc.get_final_matrix_rows(auth, document_id, version_number)
    except Exception as exc:
        raise HTTPException(404, str(exc)) from exc

    sha = SubmissionService.compute_matrix_sha256(rows)

    try:
        submission = await svc.create_submission(
            auth, document_id, version_number,
            matrix_sha256=sha,
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Submission failed: {exc}") from exc

    await session.commit()
    return SubmissionResponse.model_validate(submission)


@router.post(
    "/{submission_id}/lock",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def lock_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SubmissionResponse:
    """Lock a DRAFT submission, making it immutable (CP61)."""
    svc = _svc(session, project_id)
    try:
        sub = await svc.lock_submission(auth, submission_id)
    except SubmissionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SubmissionStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return SubmissionResponse.model_validate(sub)


@router.post(
    "/{submission_id}/approve",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def approve_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SubmissionResponse:
    """Approve a LOCKED submission, recording the approver and timestamp (CP61)."""
    svc = _svc(session, project_id)
    try:
        sub = await svc.approve_submission(auth, submission_id)
    except SubmissionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SubmissionStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return SubmissionResponse.model_validate(sub)


@router.post(
    "/{submission_id}/revoke",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def revoke_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    reason: str | None = Query(default=None, max_length=2048),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SubmissionResponse:
    """Revoke an APPROVED submission (CP61)."""
    svc = _svc(session, project_id)
    try:
        sub = await svc.revoke_submission(auth, submission_id)
    except SubmissionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SubmissionStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.commit()
    return SubmissionResponse.model_validate(sub)


@router.get(
    "/{submission_id}",
    response_model=SubmissionResponse,
    response_model_exclude_none=True,
)
async def get_submission(
    project_id: uuid.UUID,
    submission_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> SubmissionResponse:
    """Retrieve a submission if visible to the tenant (CP61)."""
    svc = _svc(session, project_id)
    sub = await svc.get_submission(auth, submission_id)
    if sub is None:
        raise HTTPException(404, "Submission not found.")
    return SubmissionResponse.model_validate(sub)


@router.get(
    "/",
    response_model=list[SubmissionResponse],
    response_model_exclude_none=True,
)
async def list_submissions(
    project_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[SubmissionResponse]:
    """List all submissions for this tenant's project (CP61)."""
    svc = _svc(session, project_id)
    subs = await svc.list_submissions(auth)
    return [SubmissionResponse.model_validate(s) for s in subs]
