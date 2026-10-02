"""Compliance assessment service (CP54).

Derives deterministic system assessments of tender requirements against
accepted vendor evidence, using the comparison engine from CP53.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func as sqla_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    AssessmentComment,
    AssessmentCommentType,
    ClarificationRequest,
    ComplianceAssessment,
    ComplianceStatus,
    Conflict,
    Deviation,
    DocumentVersion,
    Evidence,
    EvidenceReviewState,
    Project,
    Requirement,
    TenderDocument,
    VendorSpec,
)
from tender_compliance_api.extraction.constraint_parser import (
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.spec_comparison import (
    ComparisonResult,
    ComparisonVerdict,
    compare_spec,
)
from tender_compliance_api.extraction.vendor_spec import ParsedVendorSpec

# Mapping from ComparisonVerdict to ComplianceStatus.
_VERDICT_TO_STATUS: dict[ComparisonVerdict, ComplianceStatus] = {
    ComparisonVerdict.MATCH: ComplianceStatus.COMPLIANT,
    ComparisonVerdict.CLOSE: ComplianceStatus.PARTIAL,
    ComparisonVerdict.MISMATCH: ComplianceStatus.NON_COMPLIANT,
    ComparisonVerdict.INCOMPARABLE: ComplianceStatus.HUMAN_REVIEW_REQUIRED,
    ComparisonVerdict.NOT_DEMONSTRATED: ComplianceStatus.NOT_DEMONSTRATED,
}

# Priority ordering for "best" result selection (lower = more compliant).
_VERDICT_PRIORITY: dict[ComparisonVerdict, int] = {
    ComparisonVerdict.MATCH: 0,
    ComparisonVerdict.CLOSE: 1,
    ComparisonVerdict.MISMATCH: 3,
    ComparisonVerdict.INCOMPARABLE: 4,
    ComparisonVerdict.NOT_DEMONSTRATED: 5,
}


class ComplianceAssessmentService:
    """Deterministic compliance assessment with evidence linkage (CP54)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    async def assess_requirement(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> ComplianceAssessment | None:
        """Run a deterministic assessment for one requirement.

        1. Fetches the requirement (tenant-scoped).
        2. Fetches accepted evidence for the requirement.
        3. For each evidence item, fetches accepted vendor specs.
        4. Runs ``compare_spec()`` on each (constraint, vendor_spec) pair.
        5. Produces a ComplianceAssessment with the best (most compliant) result.
        6. Increments ``assessment_version`` if a prior assessment exists.
        """

        # Fetch the requirement (tenant-scoped via join to project)
        req_stmt = (
            select(Requirement)
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
                Requirement.id == requirement_id,
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        req_row = await self._session.execute(req_stmt)
        requirement = req_row.scalar_one_or_none()
        if requirement is None:
            return None

        # Parse constraints from the verbatim raw_source (deterministic, idempotent)
        constraints: list[ParsedConstraint] = parse_constraint(
            requirement.raw_source or "",
            ocr_warning=bool(requirement.ocr_warning),
        )

        # Fetch accepted evidence for this requirement
        ev_stmt = select(Evidence).where(
            Evidence.requirement_id == requirement_id,
            Evidence.review_state == EvidenceReviewState.ACCEPTED,
        )
        ev_rows = await self._session.execute(ev_stmt)
        evidence_items = ev_rows.scalars().all()

        if not evidence_items:
            return await self._create_assessment(
                requirement=requirement,
                project_id=project_id,
                evidence=None,
                vendor_spec=None,
                status=ComplianceStatus.NOT_DEMONSTRATED,
                reason_code="no_evidence_found",
                reason_text="No accepted evidence exists for this requirement.",
                comparison_result=None,
                auth=auth,
            )

        if not constraints:
            return await self._create_assessment(
                requirement=requirement,
                project_id=project_id,
                evidence=evidence_items[0],
                vendor_spec=None,
                status=ComplianceStatus.NOT_DEMONSTRATED,
                reason_code="no_constraint_parsed",
                reason_text="Requirement has no parseable numeric constraint.",
                comparison_result=None,
                auth=auth,
            )

        # Find accepted vendor specs linked to evidence for this requirement
        best_result: ComparisonResult | None = None
        best_priority: int = 999
        matched_vendor_spec: VendorSpec | None = None
        matched_evidence: Evidence | None = None

        for evidence_item in evidence_items:
            vs_stmt = select(VendorSpec).where(
                VendorSpec.evidence_id == evidence_item.id,
            )
            vs_rows = await self._session.execute(vs_stmt)
            vendor_specs = vs_rows.scalars().all()

            for vs in vendor_specs:
                parsed_vs = _vendor_spec_to_parsed(vs)
                for constraint in constraints:
                    result = compare_spec(constraint, parsed_vs)
                    priority = _VERDICT_PRIORITY.get(result.verdict, 999)
                    if priority < best_priority:
                        best_result = result
                        best_priority = priority
                        matched_vendor_spec = vs
                        matched_evidence = evidence_item

        # Determine final status from best comparison result
        if best_result is None:
            # Evidence exists but no matching vendor specs found
            return await self._create_assessment(
                requirement=requirement,
                project_id=project_id,
                evidence=evidence_items[0],
                vendor_spec=None,
                status=ComplianceStatus.NOT_DEMONSTRATED,
                reason_code="no_matching_vendor_spec",
                reason_text=(
                    "Evidence exists for this requirement but no matching "
                    "vendor specification was found."
                ),
                comparison_result=None,
                auth=auth,
            )

        status = _VERDICT_TO_STATUS[best_result.verdict]
        reason_text: str | None
        if (
            best_result.verdict is ComparisonVerdict.MISMATCH
            and best_result.comparison_rule == "parameter_mismatch"
        ):
            reason_code = "parameter_mismatch"
            reason_text = (
                "Vendor spec parameter does not match the requirement "
                "parameter (accuracy vs resolution, etc.)."
            )
        else:
            reason_code = best_result.comparison_rule
            reason_text = (
                "; ".join(best_result.reasons) if best_result.reasons else None
            )

        return await self._create_assessment(
            requirement=requirement,
            project_id=project_id,
            evidence=matched_evidence,
            vendor_spec=matched_vendor_spec,
            status=status,
            reason_code=reason_code,
            reason_text=reason_text,
            comparison_result=best_result,
            auth=auth,
        )

    async def _create_assessment(
        self,
        *,
        requirement: Requirement,
        project_id: uuid.UUID,
        evidence: Evidence | None,
        vendor_spec: VendorSpec | None,
        status: ComplianceStatus,
        reason_code: str,
        reason_text: str | None,
        comparison_result: ComparisonResult | None,
        auth: AuthContext,
    ) -> ComplianceAssessment:
        """Create a new versioned assessment, incrementing version if one exists."""

        # Get the next version number for this requirement
        stmt = (
            select(sqla_func.max(ComplianceAssessment.assessment_version)).where(
                ComplianceAssessment.requirement_id == requirement.id,
            )
        )
        row = await self._session.execute(stmt)
        max_version = row.scalar_one_or_none()
        new_version = (max_version or 0) + 1

        assessment = ComplianceAssessment(
            project_id=project_id,
            requirement_id=requirement.id,
            evidence_id=evidence.id if evidence else None,
            vendor_spec_id=vendor_spec.id if vendor_spec else None,
            suggested_status=status,
            status=status,
            reason_code=reason_code,
            reason_text=reason_text,
            comparison_result_json=_result_to_dict(comparison_result),
            assessment_version=new_version,
            is_confirmed_by_human=False,
        )
        self._session.add(assessment)
        await self._session.flush()

        # Audit log
        await self._audit.log(
            organization_id=auth.organization_id,
            action="compliance_assessment_created",
            actor_id=auth.actor_id,
            entity_type="compliance_assessment",
            entity_id=assessment.id,
            project_id=project_id,
            metadata={
                "requirement_id": str(requirement.id),
                "status": status.value,
                "reason_code": reason_code,
                "assessment_version": new_version,
            },
        )

        return assessment

    async def list_assessments(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
    ) -> list[ComplianceAssessment]:
        """List all assessments for a project, tenant-scoped."""

        stmt = (
            select(ComplianceAssessment)
            .join(Project, ComplianceAssessment.project_id == Project.id)
            .where(
                ComplianceAssessment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(
                ComplianceAssessment.requirement_id,
                ComplianceAssessment.assessment_version,
            )
        )
        row = await self._session.execute(stmt)
        return list(row.scalars().all())

    async def get_latest_assessment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> ComplianceAssessment | None:
        """Get the latest assessment for a specific requirement, tenant-scoped."""

        stmt = (
            select(ComplianceAssessment)
            .join(Project, ComplianceAssessment.project_id == Project.id)
            .where(
                ComplianceAssessment.requirement_id == requirement_id,
                ComplianceAssessment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(ComplianceAssessment.assessment_version.desc())
            .limit(1)
        )
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def confirm_assessment(
        self,
        auth: AuthContext,
        assessment_id: uuid.UUID,
    ) -> ComplianceAssessment | None:
        """Confirm an assessment as final human review.

        Sets ``is_confirmed_by_human=True`` and records the reviewer.
        The final ``status`` is set to the ``suggested_status`` (human
        confirmation of the system's deterministic suggestion).
        """

        stmt = (
            select(ComplianceAssessment)
            .join(Project, ComplianceAssessment.project_id == Project.id)
            .where(
                ComplianceAssessment.id == assessment_id,
                Project.organization_id == auth.organization_id,
            )
        )
        row = await self._session.execute(stmt)
        assessment = row.scalar_one_or_none()
        if assessment is None:
            return None

        assessment.is_confirmed_by_human = True
        assessment.reviewer_id = auth.actor_id
        assessment.reviewed_at = datetime.now(UTC)
        assessment.status = assessment.suggested_status
        assessment.updated_at = datetime.now(UTC)
        self._session.add(assessment)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            action="compliance_assessment_confirmed",
            actor_id=auth.actor_id,
            entity_type="compliance_assessment",
            entity_id=assessment_id,
            project_id=assessment.project_id,
            metadata={
                "status": assessment.status.value,
                "reviewer_id": str(auth.actor_id),
            },
        )

        return assessment

    # ------------------------------------------------------------------
    # CP58 — Human review: override, reopen, comments, combined review
    # ------------------------------------------------------------------

    async def _fetch_assessment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> ComplianceAssessment | None:
        """Fetch a single assessment, tenant-scoped. Shared by review methods."""
        stmt = (
            select(ComplianceAssessment)
            .join(Project, ComplianceAssessment.project_id == Project.id)
            .where(
                ComplianceAssessment.id == assessment_id,
                ComplianceAssessment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def _next_assessment_version(
        self, requirement_id: uuid.UUID
    ) -> int:
        """Return the next assessment_version for a requirement."""
        stmt = (
            select(sqla_func.max(ComplianceAssessment.assessment_version)).where(
                ComplianceAssessment.requirement_id == requirement_id,
            )
        )
        row = await self._session.execute(stmt)
        max_version = row.scalar_one_or_none()
        return (max_version or 0) + 1

    async def override_assessment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID,
        status: ComplianceStatus,
        reason: str,
        evidence_id: uuid.UUID | None = None,
    ) -> ComplianceAssessment | None:
        """Create a new assessment version with a human-overridden status.

        The **original** assessment row is never modified — a new row with an
        incremented ``assessment_version`` is created.  The original
        ``suggested_status`` is preserved on the new row so the system's
        deterministic suggestion remains auditable even after override.

        ``status`` must be one of the six product-defined
        :class:`ComplianceStatus` values.  The override is always the human's
        deliberate choice — it cannot be ``suggested_status`` via this method
        (use :meth:`confirm_assessment` instead, which does not create a new
        version).
        """
        original = await self._fetch_assessment(auth, project_id, assessment_id)
        if original is None:
            return None

        if status == original.suggested_status and evidence_id is None:
            raise ValueError(
                "Override status matches the suggested status; use "
                "confirm_assessment instead, or specify a different status / "
                "evidence."
            )

        new_version = await self._next_assessment_version(original.requirement_id)

        overridden = ComplianceAssessment(
            project_id=original.project_id,
            requirement_id=original.requirement_id,
            evidence_id=evidence_id if evidence_id is not None else original.evidence_id,
            vendor_spec_id=original.vendor_spec_id,
            suggested_status=original.suggested_status,
            status=status,
            reason_code="human_override",
            reason_text=reason,
            comparison_result_json=original.comparison_result_json,
            assessment_version=new_version,
            is_confirmed_by_human=True,
            reviewer_id=auth.actor_id,
            reviewed_at=datetime.now(UTC),
        )
        self._session.add(overridden)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="compliance_assessment_overridden",
            entity_type="compliance_assessment",
            entity_id=overridden.id,
            project_id=project_id,
            metadata={
                "original_assessment_id": str(original.id),
                "original_status": original.status.value,
                "overridden_status": status.value,
                "assessment_version": new_version,
            },
        )

        # Persist the override reason as an audit comment.
        comment = AssessmentComment(
            assessment_id=overridden.id,
            project_id=project_id,
            author_id=auth.actor_id,
            comment_type=AssessmentCommentType.OVERRIDE_REASON,
            comment=reason,
            assessment_version=new_version,
        )
        self._session.add(comment)
        await self._session.flush()

        return overridden

    async def reopen_assessment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID,
        reason: str | None = None,
    ) -> ComplianceAssessment | None:
        """Reopen a confirmed assessment for re-review.

        Creates a new assessment version that reverts to the system's
        ``suggested_status`` with ``is_confirmed_by_human=False``.  The
        original confirmed assessment row is preserved (append-only).
        """
        original = await self._fetch_assessment(auth, project_id, assessment_id)
        if original is None:
            return None
        if not original.is_confirmed_by_human:
            raise ValueError(
                "Only confirmed assessments can be reopened."
            )

        new_version = await self._next_assessment_version(original.requirement_id)

        reopened = ComplianceAssessment(
            project_id=original.project_id,
            requirement_id=original.requirement_id,
            evidence_id=original.evidence_id,
            vendor_spec_id=original.vendor_spec_id,
            suggested_status=original.suggested_status,
            status=original.suggested_status,
            reason_code="reopened",
            reason_text=reason or "Assessment reopened for re-review.",
            comparison_result_json=original.comparison_result_json,
            assessment_version=new_version,
            is_confirmed_by_human=False,
            reviewer_id=auth.actor_id,
            reviewed_at=datetime.now(UTC),
        )
        self._session.add(reopened)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="compliance_assessment_reopened",
            entity_type="compliance_assessment",
            entity_id=reopened.id,
            project_id=project_id,
            metadata={
                "original_assessment_id": str(original.id),
                "assessment_version": new_version,
            },
        )

        if reason:
            comment = AssessmentComment(
                assessment_id=reopened.id,
                project_id=project_id,
                author_id=auth.actor_id,
                comment_type=AssessmentCommentType.REOPEN_REASON,
                comment=reason,
                assessment_version=new_version,
            )
            self._session.add(comment)
            await self._session.flush()

        return reopened

    async def add_comment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID,
        comment: str,
        comment_type: AssessmentCommentType = AssessmentCommentType.COMMENT,
    ) -> AssessmentComment | None:
        """Add a reviewer comment to an assessment, tenant-scoped."""
        assessment = await self._fetch_assessment(
            auth, project_id, assessment_id
        )
        if assessment is None:
            return None

        ac = AssessmentComment(
            assessment_id=assessment_id,
            project_id=project_id,
            author_id=auth.actor_id,
            comment_type=comment_type,
            comment=comment,
            assessment_version=assessment.assessment_version,
        )
        self._session.add(ac)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="assessment_comment_added",
            entity_type="assessment_comment",
            entity_id=ac.id,
            project_id=project_id,
            metadata={
                "assessment_id": str(assessment_id),
                "comment_type": comment_type.value,
            },
        )
        return ac

    async def list_comments(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> list[AssessmentComment]:
        """List all comments for an assessment, tenant-scoped and ordered."""
        stmt = (
            select(AssessmentComment)
            .join(Project, AssessmentComment.project_id == Project.id)
            .where(
                AssessmentComment.assessment_id == assessment_id,
                AssessmentComment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(AssessmentComment.created_at.asc())
        )
        rows = await self._session.execute(stmt)
        return list(rows.scalars().all())

    async def get_requirement_review(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Combined review view for a single requirement.

        Returns the latest compliance assessment (with its deterministic
        comparison details) plus all related CP56 conflicts, CP57
        clarifications, and CP57 deviations — everything a human reviewer needs
        to make a final determination in one query.
        """
        assessment = await self.get_latest_assessment(
            auth, project_id, requirement_id
        )
        if assessment is None:
            return None

        conflict_stmt = (
            select(Conflict)
            .join(Project, Conflict.project_id == Project.id)
            .where(
                Conflict.requirement_id == requirement_id,
                Conflict.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(Conflict.id)
        )
        conflict_rows = await self._session.execute(conflict_stmt)
        conflicts = list(conflict_rows.scalars().all())

        clarification_stmt = (
            select(ClarificationRequest)
            .join(Project, ClarificationRequest.project_id == Project.id)
            .where(
                ClarificationRequest.requirement_id == requirement_id,
                ClarificationRequest.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(ClarificationRequest.asked_at.desc())
        )
        clarification_rows = await self._session.execute(clarification_stmt)
        clarifications = list(clarification_rows.scalars().all())

        deviation_stmt = (
            select(Deviation)
            .join(Project, Deviation.project_id == Project.id)
            .where(
                Deviation.requirement_id == requirement_id,
                Deviation.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(Deviation.proposed_at.desc())
        )
        deviation_rows = await self._session.execute(deviation_stmt)
        deviations = list(deviation_rows.scalars().all())

        comparison = (
            assessment.comparison_result_json
            if isinstance(assessment.comparison_result_json, dict)
            else None
        )

        return {
            "requirement_id": str(requirement_id),
            "assessment": {
                "id": str(assessment.id),
                "suggested_status": assessment.suggested_status.value,
                "status": assessment.status.value,
                "reason_code": assessment.reason_code,
                "reason_text": assessment.reason_text,
                "is_confirmed_by_human": assessment.is_confirmed_by_human,
                "reviewer_id": (
                    str(assessment.reviewer_id) if assessment.reviewer_id else None
                ),
                "reviewed_at": (
                    assessment.reviewed_at.isoformat()
                    if assessment.reviewed_at
                    else None
                ),
                "assessment_version": assessment.assessment_version,
                "evidence_id": (
                    str(assessment.evidence_id)
                    if assessment.evidence_id
                    else None
                ),
                "vendor_spec_id": (
                    str(assessment.vendor_spec_id)
                    if assessment.vendor_spec_id
                    else None
                ),
                "comparison_result": comparison,
            },
            "conflicts": [
                {
                    "id": str(c.id),
                    "conflict_type": c.conflict_type,
                    "parameter": c.parameter,
                    "entity": c.entity,
                    "resolution": c.resolution.value,
                    "sources": c.sources,
                    "tender_claim": c.tender_claim,
                }
                for c in conflicts
            ],
            "clarifications": [
                {
                    "id": str(c.id),
                    "question": c.question,
                    "context": c.context,
                    "status": c.status.value,
                    "asked_at": c.asked_at.isoformat(),
                    "answer": c.answer,
                    "answered_at": c.answered_at.isoformat() if c.answered_at else None,
                }
                for c in clarifications
            ],
            "deviations": [
                {
                    "id": str(d.id),
                    "deviation_type": d.deviation_type.value,
                    "original_requirement": d.original_requirement,
                    "proposed_alternative": d.proposed_alternative,
                    "status": d.status.value,
                    "proposed_at": d.proposed_at.isoformat(),
                    "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
                }
                for d in deviations
            ],
        }


def _vendor_spec_to_parsed(vs: VendorSpec) -> ParsedVendorSpec:
    """Convert a persisted VendorSpec model to a ParsedVendorSpec."""

    return ParsedVendorSpec(
        parameter=vs.parameter,
        entity=vs.entity,
        value=float(vs.value) if vs.value is not None else None,
        lower_bound=float(vs.lower_bound) if vs.lower_bound is not None else None,
        upper_bound=float(vs.upper_bound) if vs.upper_bound is not None else None,
        unit=vs.unit,
        tolerance=float(vs.tolerance) if vs.tolerance is not None else None,
        qualitative_statement=vs.qualitative_statement,
        conditions=vs.conditions,
        source_text=vs.source_text,
        source_page_number=vs.source_page_number,
        char_start=vs.char_start,
        char_end=vs.char_end,
        ocr_confidence=float(vs.ocr_confidence) if vs.ocr_confidence else None,
        location_type=vs.location_type,
        extraction_method=vs.extraction_method.value,
        extraction_version=vs.extraction_version,
        normalization_state=vs.normalization_state,
        issues=tuple(vs.issues or ()),
    )


def _result_to_dict(result: ComparisonResult | None) -> dict[str, object] | None:
    """Serialize a ComparisonResult to a JSON-safe dict for storage."""

    if result is None:
        return None
    return {
        "verdict": result.verdict.value,
        "tender_text": result.tender_text,
        "vendor_text": result.vendor_text,
        "comparison_rule": result.comparison_rule,
        "conversion": result.conversion,
        "reasons": list(result.reasons),
        "tender_value": result.tender_value,
        "vendor_value": result.vendor_value,
        "tender_unit": result.tender_unit,
        "vendor_unit": result.vendor_unit,
        "normalized_tender_value": result.normalized_tender_value,
        "normalized_vendor_value": result.normalized_vendor_value,
        "details": result.details,
    }


__all__ = ["ComplianceAssessmentService", "ComplianceStatus"]
