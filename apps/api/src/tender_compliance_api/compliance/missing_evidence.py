"""CP57 — Missing evidence, clarification questions, and deviations.

This module provides :class:`MissingEvidenceService` for:

1.  **Clarification requests** — questions posed when evidence is insufficient
    or ambiguous, or when a conflict (CP56) has been detected that requires
    human input before a compliance determination can proceed.
2.  **Deviations** — when a vendor proposes to deviate from the original
    tender requirement (different scope, value, or capability).

Design rules:
- Clarification requests are **never** auto-answered.  The question text is
  verbatim — never synthesized.  The answer comes from a human / OEM.
- Deviations are **never** auto-accepted.  They require explicit human
  review and must be ACCEPTED or REJECTED.
- Every action is audited.
- Tenant isolation at every query.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    ClarificationRequest,
    ClarificationStatus,
    Conflict,
    Deviation,
    DeviationStatus,
    DeviationType,
    DocumentVersion,
    Evidence,
    EvidenceReviewState,
    Project,
    QualitativeAssessment,
    Requirement,
    TenderDocument,
)


@dataclass
class ClarificationContext:
    """Structured metadata for why a clarification is being requested."""

    reason: str
    """e.g. ``missing_evidence``, ``ambiguous_requirement``, ``conflict``."""

    parameter: str | None = None
    """The parameter that is missing or ambiguous."""

    conflict_id: str | None = None
    """If triggered by a CP56 conflict, the conflict ID."""

    evidence_ids: list[str] | None = None
    """Evidence IDs that were examined but found insufficient."""

    detail: str | None = None
    """Free-form additional context."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"reason": self.reason}
        if self.parameter is not None:
            d["parameter"] = self.parameter
        if self.conflict_id is not None:
            d["conflict_id"] = self.conflict_id
        if self.evidence_ids is not None:
            d["evidence_ids"] = self.evidence_ids
        if self.detail is not None:
            d["detail"] = self.detail
        return d


class MissingEvidenceService:
    """Service for clarification requests and deviations (CP57).

    All public methods are async and tenant-scoped through
    :class:`~tender_compliance_api.auth.context.AuthContext`.
    """

    def __init__(
        self, db: AsyncSession, audit: AuditService
    ) -> None:
        self._db = db
        self._audit = audit

    # ------------------------------------------------------------------
    # Clarification requests
    # ------------------------------------------------------------------

    async def create_clarification(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        question: str,
        context: ClarificationContext,
        requirement_id: uuid.UUID | None = None,
        related_evidence_ids: list[str] | None = None,
        related_conflict_ids: list[str] | None = None,
    ) -> ClarificationRequest:
        """Create a clarification request (status = PENDING)."""
        # Validate project access.
        if not await self._project_exists(auth, project_id):
            raise ValueError(
                f"Project {project_id} not accessible to organization "
                f"{auth.organization_id}"
            )
        if requirement_id is not None:
            if await self._fetch_requirement(auth, project_id, requirement_id) is None:
                raise ValueError(
                    f"Requirement {requirement_id} not found in project "
                    f"{project_id}"
                )

        cr = ClarificationRequest(
            id=uuid.uuid4(),
            project_id=project_id,
            requirement_id=requirement_id,
            question=question,
            context=context.to_dict(),
            status=ClarificationStatus.PENDING,
            related_evidence_ids=related_evidence_ids,
            related_conflict_ids=related_conflict_ids,
            asked_by=auth.actor_id,
            asked_at=datetime.now(UTC),
        )
        self._db.add(cr)
        await self._db.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="clarification_requested",
            entity_type="clarification_request",
            entity_id=cr.id,
            project_id=project_id,
            metadata={
                "requirement_id": str(requirement_id) if requirement_id else None,
                "reason": context.reason,
                "parameter": context.parameter,
            },
        )
        return cr

    async def answer_clarification(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        clarification_id: uuid.UUID,
        answer: str,
    ) -> ClarificationRequest | None:
        """Record a human/OEM answer to a clarification request.

        Returns ``None`` if the clarification does not exist in the tenant
        scope (tenant isolation).
        """
        cr = await self._fetch_clarification(auth, project_id, clarification_id)
        if cr is None:
            return None
        if cr.status == ClarificationStatus.ANSWERED:
            raise ValueError(
                "Clarification request has already been answered."
            )

        cr.answer = answer
        cr.status = ClarificationStatus.ANSWERED
        cr.answered_by = auth.actor_id
        cr.answered_at = datetime.now(UTC)
        cr.updated_at = datetime.now(UTC)
        self._db.add(cr)
        await self._db.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="clarification_answered",
            entity_type="clarification_request",
            entity_id=cr.id,
            project_id=project_id,
            metadata={"answer_length": len(answer)},
        )
        return cr

    async def list_clarifications(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID | None = None,
        status: ClarificationStatus | None = None,
    ) -> list[ClarificationRequest]:
        """List clarification requests for a project (optionally filtered)."""
        stmt = (
            select(ClarificationRequest)
            .join(Project)
            .where(
                ClarificationRequest.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        if requirement_id is not None:
            stmt = stmt.where(
                ClarificationRequest.requirement_id == requirement_id
            )
        if status is not None:
            stmt = stmt.where(ClarificationRequest.status == status)
        stmt = stmt.order_by(ClarificationRequest.asked_at.desc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_clarification(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        clarification_id: uuid.UUID,
    ) -> ClarificationRequest | None:
        return await self._fetch_clarification(auth, project_id, clarification_id)

    async def edit_clarification(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        clarification_id: uuid.UUID,
        question: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ClarificationRequest | None:
        """Edit a clarification request's question text and/or context.

        Allows a human reviewer to refine an auto-generated clarification
        question (or its structured context metadata) before it is sent to
        the OEM/customer.  Returns ``None`` if the clarification does not
        exist in the tenant scope (tenant isolation).

        Only ``PENDING`` clarifications may be edited.  ``ANSWERED``
        clarifications are locked — editing them raises :class:`ValueError`.
        The question text is stored verbatim; no normalization or
        synthesis is applied.
        """
        cr = await self._fetch_clarification(auth, project_id, clarification_id)
        if cr is None:
            return None
        if cr.status == ClarificationStatus.ANSWERED:
            raise ValueError(
                "Cannot edit an answered clarification request; "
                "the question is locked once answered."
            )
        changed = False
        if question is not None:
            cr.question = question
            changed = True
        if context is not None:
            cr.context = context
            changed = True
        if changed:
            cr.updated_at = datetime.now(UTC)
        self._db.add(cr)
        await self._db.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="clarification_edited",
            entity_type="clarification_request",
            entity_id=cr.id,
            project_id=project_id,
            metadata={
                "question": question is not None,
                "context": context is not None,
            },
        )
        return cr

    async def auto_generate_clarifications(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> list[ClarificationRequest]:
        """Automatically generate clarification requests for a requirement.

        Scans the requirement for conditions that warrant human input:

        1.  No accepted evidence exists for a parameter referenced in the
            requirement → ``missing_evidence``.
        2.  A CP56 conflict was detected for this requirement → ``conflict``.
        3.  The requirement text is flagged with OCR_WARNING uncertainty →
            ``ambiguous_requirement``.
        """
        req = await self._fetch_requirement(auth, project_id, requirement_id)
        if req is None:
            raise ValueError(
                f"Requirement {requirement_id} not found in project "
                f"{project_id}"
            )

        created: list[ClarificationRequest] = []

        # 1. Check for missing evidence.
        evidence_stmt = (
            select(Evidence.id)
            .join(Requirement)
            .join(
                DocumentVersion,
                Requirement.document_version_id == DocumentVersion.id,
            )
            .join(
                TenderDocument,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
                Evidence.requirement_id == requirement_id,
                Evidence.review_state == EvidenceReviewState.ACCEPTED,
            )
        )
        ev_result = await self._db.execute(evidence_stmt)
        evidence_ids = [str(r) for r in ev_result.scalars().all()]

        if not evidence_ids:
            cr = await self.create_clarification(
                auth=auth,
                project_id=project_id,
                question=(
                    f"No accepted evidence was found for the requirement: "
                    f"\"{req.raw_source or req.normalized_text}\". "
                    f"Please provide supporting documentation for this "
                    f"requirement."
                ),
                context=ClarificationContext(
                    reason="missing_evidence",
                    detail="No accepted evidence items found for this requirement.",
                ),
                requirement_id=requirement_id,
            )
            created.append(cr)

        # 2. Check for unresolved conflicts (CP56).
        conflict_stmt = (
            select(Conflict)
            .join(Project)
            .where(
                Conflict.project_id == project_id,
                Project.organization_id == auth.organization_id,
                Conflict.requirement_id == requirement_id,
                Conflict.resolution == "unresolved",
            )
        )
        conflict_result = await self._db.execute(conflict_stmt)
        unresolved_conflicts = conflict_result.scalars().all()

        for conflict in unresolved_conflicts:
            cr = await self.create_clarification(
                auth=auth,
                project_id=project_id,
                question=(
                    f"A conflict was detected for parameter "
                    f"'{conflict.parameter or '(unspecified)'}' in this "
                    f"requirement. Please clarify which value is correct."
                ),
                context=ClarificationContext(
                    reason="conflict",
                    parameter=conflict.parameter,
                    conflict_id=str(conflict.id),
                    evidence_ids=[
                        str(s.get("evidence_id"))
                        for s in conflict.sources
                        if s.get("evidence_id")
                    ],
                    detail=f"Conflict type: {conflict.conflict_type}",
                ),
                requirement_id=requirement_id,
                related_conflict_ids=[str(conflict.id)],
                related_evidence_ids=[
                    str(s.get("evidence_id"))
                    for s in conflict.sources
                    if s.get("evidence_id")
                ],
            )
            created.append(cr)

        # 3. Check for OCR warning on qualitative assessments.
        qa_stmt = (
            select(QualitativeAssessment)
            .join(Requirement)
            .join(
                DocumentVersion,
                Requirement.document_version_id == DocumentVersion.id,
            )
            .join(
                TenderDocument,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
                QualitativeAssessment.requirement_id == requirement_id,
            )
            .order_by(QualitativeAssessment.assessment_version.desc())
        )
        qa_result = await self._db.execute(qa_stmt)
        latest_qa = qa_result.scalars().first()

        if latest_qa is not None and latest_qa.verdict.value == "uncertain":
            cr = await self.create_clarification(
                auth=auth,
                project_id=project_id,
                question=(
                    f"The requirement \"{req.raw_source or req.normalized_text}\" "
                    f"was assessed as UNCERTAIN, likely due to OCR-derived "
                    f"evidence. Please verify the source text and provide "
                    f"clearer documentation."
                ),
                context=ClarificationContext(
                    reason="ambiguous_requirement",
                    detail="Latest qualitative assessment returned UNCERTAIN verdict.",
                ),
                requirement_id=requirement_id,
            )
            created.append(cr)

        return created

    # ------------------------------------------------------------------
    # Deviations
    # ------------------------------------------------------------------

    async def create_deviation(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        deviation_type: DeviationType,
        original_requirement: str,
        proposed_alternative: str | None = None,
        rationale: str | None = None,
    ) -> Deviation:
        """Create a deviation proposal (status = PROPOSED)."""
        if not await self._project_exists(auth, project_id):
            raise ValueError(
                f"Project {project_id} not accessible to organization "
                f"{auth.organization_id}"
            )
        if await self._fetch_requirement(auth, project_id, requirement_id) is None:
            raise ValueError(
                f"Requirement {requirement_id} not found in project "
                f"{project_id}"
            )

        dev = Deviation(
            id=uuid.uuid4(),
            project_id=project_id,
            requirement_id=requirement_id,
            deviation_type=deviation_type,
            original_requirement=original_requirement,
            proposed_alternative=proposed_alternative,
            rationale=rationale,
            status=DeviationStatus.PROPOSED,
            proposed_by=auth.actor_id,
            proposed_at=datetime.now(UTC),
        )
        self._db.add(dev)
        await self._db.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="deviation_proposed",
            entity_type="deviation",
            entity_id=dev.id,
            project_id=project_id,
            metadata={
                "requirement_id": str(requirement_id),
                "deviation_type": deviation_type.value,
            },
        )
        return dev

    async def review_deviation(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        deviation_id: uuid.UUID,
        status: DeviationStatus,
        review_notes: str | None = None,
    ) -> Deviation | None:
        """Review a deviation (set ACCEPTED or REJECTED).

        Returns ``None`` if the deviation does not exist in the tenant
        scope (tenant isolation).
        """
        if status == DeviationStatus.PROPOSED:
            raise ValueError(
                "Cannot set deviation to PROPOSED via review; "
                "use create_deviation to propose."
            )
        dev = await self._fetch_deviation(auth, project_id, deviation_id)
        if dev is None:
            return None
        if dev.status != DeviationStatus.PROPOSED:
            raise ValueError(
                f"Deviation is already {dev.status.value} — cannot change again."
            )

        dev.status = status
        dev.review_notes = review_notes
        dev.reviewed_by = auth.actor_id
        dev.reviewed_at = datetime.now(UTC)
        dev.updated_at = datetime.now(UTC)
        self._db.add(dev)
        await self._db.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="deviation_reviewed",
            entity_type="deviation",
            entity_id=dev.id,
            project_id=project_id,
            metadata={
                "status": status.value,
                "review_notes": review_notes,
            },
        )
        return dev

    async def list_deviations(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID | None = None,
        status: DeviationStatus | None = None,
    ) -> list[Deviation]:
        """List deviations for a project (optionally filtered)."""
        stmt = (
            select(Deviation)
            .join(Project)
            .where(
                Deviation.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        if requirement_id is not None:
            stmt = stmt.where(Deviation.requirement_id == requirement_id)
        if status is not None:
            stmt = stmt.where(Deviation.status == status)
        stmt = stmt.order_by(Deviation.proposed_at.desc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _project_exists(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> bool:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.organization_id == auth.organization_id,
        )
        result = await self._db.execute(stmt)
        return result.scalars().first() is not None

    async def _fetch_requirement(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> Requirement | None:
        stmt = (
            select(Requirement)
            .join(DocumentVersion)
            .join(TenderDocument)
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                Requirement.id == requirement_id,
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _fetch_clarification(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        clarification_id: uuid.UUID,
    ) -> ClarificationRequest | None:
        stmt = (
            select(ClarificationRequest)
            .join(Project)
            .where(
                ClarificationRequest.id == clarification_id,
                ClarificationRequest.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _fetch_deviation(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        deviation_id: uuid.UUID,
    ) -> Deviation | None:
        stmt = (
            select(Deviation)
            .join(Project)
            .where(
                Deviation.id == deviation_id,
                Deviation.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()
