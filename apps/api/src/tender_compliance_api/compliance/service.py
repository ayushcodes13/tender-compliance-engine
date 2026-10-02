"""Compliance assessment service (CP54).

Derives deterministic system assessments of tender requirements against
accepted vendor evidence, using the comparison engine from CP53.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func as sqla_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    ComplianceAssessment,
    ComplianceStatus,
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
