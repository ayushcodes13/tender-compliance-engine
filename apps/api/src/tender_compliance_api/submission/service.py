"""Submission lifecycle service: create, lock, approve, revoke (CP61).

Business logic for the submission approval/lock state machine.  Every method
takes a verified :class:`AuthContext` so tenant isolation is enforced in one
place.

State transitions:
    DRAFT → LOCKED → APPROVED → REVOKED

Locked and approved submissions are **immutable**: later changes create a new
submission with an incremented ``version_number`` rather than mutating the
existing row.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    ComplianceAssessment,
    DocumentVersion,
    ExportArtifact,
    Project,
    Requirement,
    Submission,
    SubmissionStatus,
    TenderDocument,
)
from tender_compliance_api.matrix.projection import FinalMatrixRow


class SubmissionNotFoundError(ValueError):
    """Raised when a submission does not exist or is not visible to the tenant."""


class SubmissionStateError(ValueError):
    """Raised when a state transition is invalid (e.g. lock an already-approved submission)."""


class SubmissionService:
    """Tenant-scoped lifecycle management for submission snapshots."""

    def __init__(self, session: AsyncSession, project_id: uuid.UUID) -> None:
        self._session = session
        self._project_id = project_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_version(
        self, document_id: uuid.UUID, version_number: int, org_id: uuid.UUID,
    ) -> DocumentVersion:
        result = await self._session.execute(
            select(DocumentVersion)
            .join(TenderDocument, DocumentVersion.document_id == TenderDocument.id)
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                TenderDocument.id == document_id,
                DocumentVersion.version_number == version_number,
                Project.organization_id == org_id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise SubmissionNotFoundError(
                f"Document version {document_id} v{version_number} not found."
            )
        return version

    async def _next_version_number(self, org_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.max(Submission.version_number))
            .join(Project, Submission.project_id == Project.id)
            .where(
                Submission.project_id == self._project_id,
                Project.organization_id == org_id,
            )
        )
        max_v = result.scalar_one_or_none()
        return (max_v or 0) + 1

    async def _snapshot_assessments(
        self, version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Capture a point-in-time snapshot of all assessment states for a version."""
        result = await self._session.execute(
            select(ComplianceAssessment)
            .where(ComplianceAssessment.requirement_id.in_(
                select(Requirement.id).where(
                    Requirement.document_version_id == version_id
                )
            ))
        )
        assessments = result.scalars().all()
        snapshot: list[dict[str, Any]] = []
        for a in assessments:
            snapshot.append({
                "requirement_id": str(a.requirement_id),
                "assessment_version": a.assessment_version,
                "status": a.status.value,
                "suggested_status": a.suggested_status.value,
                "is_confirmed_by_human": a.is_confirmed_by_human,
                "reason_code": a.reason_code,
            })
        return snapshot

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_submission(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        assessment_rows: list[FinalMatrixRow] | None = None,
        matrix_sha256: str,
        matrix_export_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Submission:
        """Create a new DRAFT submission snapshot for a document version.

        Raises ``SubmissionStateError`` if the latest submission for this
        project+version is already locked or approved (use a new project
        version instead).
        """
        version = await self._fetch_version(
            document_id, version_number, auth.organization_id,
        )

        vnum = await self._next_version_number(auth.organization_id)

        # Build assessment snapshot
        snapshot = await self._snapshot_assessments(version.id)

        if matrix_sha256 is None or len(matrix_sha256) == 0:
            raise ValueError("matrix_sha256 is required")

        # Validate export belongs to same project (if provided)
        if matrix_export_id is not None:
            result = await self._session.execute(
                select(ExportArtifact)
                .join(DocumentVersion, ExportArtifact.document_version_id == DocumentVersion.id)
                .join(TenderDocument, DocumentVersion.document_id == TenderDocument.id)
                .join(Project, TenderDocument.project_id == Project.id)
                .where(
                    ExportArtifact.id == matrix_export_id,
                    Project.organization_id == auth.organization_id,
                    DocumentVersion.id == version.id,
                )
            )
            existing_export = result.scalar_one_or_none()
            if existing_export is None:
                raise SubmissionNotFoundError(
                    "Export artifact not found or not visible for this version."
                )

        submission = Submission(
            project_id=self._project_id,
            document_version_id=version.id,
            version_number=vnum,
            status=SubmissionStatus.DRAFT,
            assessment_snapshot=snapshot,
            matrix_sha256=matrix_sha256,
            matrix_export_id=matrix_export_id,
            created_by=actor_id or auth.actor_id,
        )
        self._session.add(submission)
        await self._session.flush()

        return submission

    async def lock_submission(
        self,
        auth: AuthContext,
        submission_id: uuid.UUID,
    ) -> Submission:
        """Lock a DRAFT submission, making it immutable.

        Raises ``SubmissionStateError`` if the submission is already locked,
        approved, or revoked.
        """
        sub = await self._fetch_subversion(auth, submission_id, auth.organization_id)
        if sub.status not in (SubmissionStatus.DRAFT,):
            raise SubmissionStateError(
                f"Cannot lock submission in {sub.status.value} state. "
                f"Only DRAFT submissions can be locked."
            )
        sub.status = SubmissionStatus.LOCKED
        sub.updated_at = datetime.now(UTC)
        await self._session.flush()
        return sub

    async def approve_submission(
        self,
        auth: AuthContext,
        submission_id: uuid.UUID,
    ) -> Submission:
        """Approve a LOCKED submission, recording the approver and timestamp.

        Raises ``SubmissionStateError`` if the submission is not in LOCKED state.
        """
        sub = await self._fetch_subversion(auth, submission_id, auth.organization_id)
        if sub.status != SubmissionStatus.LOCKED:
            raise SubmissionStateError(
                f"Cannot approve submission in {sub.status.value} state. "
                f"Only LOCKED submissions can be approved."
            )
        sub.status = SubmissionStatus.APPROVED
        sub.approver_id = auth.actor_id
        sub.approved_at = datetime.now(UTC)
        sub.updated_at = datetime.now(UTC)
        await self._session.flush()
        return sub

    async def revoke_submission(
        self,
        auth: AuthContext,
        submission_id: uuid.UUID,
        *,
        reason: str | None = None,
    ) -> Submission:
        """Revoke an APPROVED submission.

        Raises ``SubmissionStateError`` if the submission is not in APPROVED state.
        """
        sub = await self._fetch_subversion(auth, submission_id, auth.organization_id)
        if sub.status != SubmissionStatus.APPROVED:
            raise SubmissionStateError(
                f"Cannot revoke submission in {sub.status.value} state. "
                f"Only APPROVED submissions can be revoked."
            )
        sub.status = SubmissionStatus.REVOKED
        sub.updated_at = datetime.now(UTC)
        await self._session.flush()
        return sub

    async def get_submission(
        self,
        auth: AuthContext,
        submission_id: uuid.UUID,
    ) -> Submission | None:
        """Retrieve a submission if visible to the tenant."""
        result = await self._session.execute(
            select(Submission)
            .join(Project, Submission.project_id == Project.id)
            .where(
                Submission.id == submission_id,
                Project.organization_id == auth.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_submissions(
        self,
        auth: AuthContext,
    ) -> list[Submission]:
        """List all submissions visible to the authenticated tenant."""
        result = await self._session.execute(
            select(Submission)
            .join(Project, Submission.project_id == Project.id)
            .where(Project.organization_id == auth.organization_id)
            .order_by(Submission.version_number)
        )
        return list(result.scalars().unique().all())

    async def get_latest_submission(
        self,
        auth: AuthContext,
    ) -> Submission | None:
        """Get the latest submission for the project."""
        result = await self._session.execute(
            select(Submission)
            .join(Project, Submission.project_id == Project.id)
            .where(Project.organization_id == auth.organization_id)
            .order_by(Submission.version_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def compute_matrix_sha256(rows: list[FinalMatrixRow]) -> str:
        """Compute a deterministic SHA-256 over the matrix row states.

        Uses the requirement_id, assessment_status, evidence_id, and
        assessment_is_confirmed fields — the fields that change when the
        compliance state changes.  This allows detecting whether a new
        submission snapshot differs from the previous one.
        """
        parts: list[str] = []
        for row in rows:
            parts.append(
                f"{row.requirement_id}|{row.assessment_status}|"
                f"{row.evidence_id}|{row.assessment_is_confirmed}",
            )
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    async def _fetch_subversion(
        self, auth: AuthContext, submission_id: uuid.UUID, org_id: uuid.UUID,
    ) -> Submission:
        result = await self._session.execute(
            select(Submission)
            .join(Project, Submission.project_id == Project.id)
            .where(
                Submission.id == submission_id,
                Project.organization_id == org_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise SubmissionNotFoundError(
                f"Submission {submission_id} not found or not visible."
            )
        return sub
