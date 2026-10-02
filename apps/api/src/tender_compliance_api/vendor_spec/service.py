"""Vendor specification extraction service (CP52).

Wires the deterministic :func:`~tender_compliance_api.extraction.vendor_spec`
parser to persistence, enforcing the Phase 2 guardrail that every vendor
fact must point to accepted evidence.

The service operates on OEM text segments that are linked to accepted
:class:`~tender_compliance_api.db.models.Evidence` rows.  When extracting
from a specific evidence item, only that evidence's source segments are
searched; when extracting broadly, all accepted evidence for a requirement
is scanned.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    Evidence,
    EvidenceLocation,
    EvidenceReviewState,
    OemDocument,
    OemDocumentVersion,
    OemTextSegment,
    Project,
    Requirement,
    VendorSpec,
    VendorSpecExtractionMethod,
)
from tender_compliance_api.extraction.vendor_spec import (
    VENDOR_SPEC_VERSION,
    parse_vendor_specs,
)


class VendorSpecService:
    """Deterministic vendor spec extraction with evidence linkage (CP52)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    async def _verify_evidence_access(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        evidence_id: uuid.UUID,
    ) -> Evidence | None:
        """Return the evidence if it belongs to *auth*'s org and is accepted."""

        stmt = (
            select(Evidence)
            .join(
                EvidenceLocation,
                Evidence.id == EvidenceLocation.evidence_id,
            )
            .join(
                OemTextSegment,
                EvidenceLocation.oem_text_segment_id
                == OemTextSegment.id,
            )
            .join(
                OemDocumentVersion,
                OemTextSegment.oem_document_version_id
                == OemDocumentVersion.id,
            )
            .join(
                OemDocument,
                OemDocumentVersion.document_id == OemDocument.id,
            )
            .join(Project, OemDocument.project_id == Project.id)
            .join(
                Requirement,
                Evidence.requirement_id == Requirement.id,
            )
            .where(
                and_(
                    Evidence.id == evidence_id,
                    Evidence.requirement_id == requirement_id,
                    Project.id == project_id,
                    Project.organization_id == auth.organization_id,
                    Evidence.review_state == EvidenceReviewState.ACCEPTED,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def extract_specs_for_evidence(
        self,
        auth: AuthContext,
        project_id: str,
        requirement_id: str,
        evidence_id: str,
        *,
        force_rerun: bool = False,
    ) -> list[VendorSpec]:
        """Extract vendor specifications from an accepted evidence item.

        Runs the deterministic parser over every OEM text segment linked to
        the evidence's locations.  Existing vendor specs for this evidence are
        replaced (idempotent reprocessing).

        Args:
            auth: Authenticated context (org scoping).
            project_id: UUID of the owning project.
            requirement_id: UUID of the requirement.
            evidence_id: UUID of the accepted evidence item.
            force_rerun: If True, re-extracts even if specs already exist.

        Returns:
            The created :class:`VendorSpec` rows.
        """

        proj_id = uuid.UUID(project_id)
        req_id = uuid.UUID(requirement_id)
        ev_id = uuid.UUID(evidence_id)

        # Verify the evidence is accessible and accepted.
        evidence = await self._verify_evidence_access(
            auth, proj_id, req_id, ev_id
        )
        if evidence is None:
            return []

        # If specs already exist and force_rerun is False, return them.
        if not force_rerun:
            existing = await self._session.execute(
                select(VendorSpec).where(
                    and_(
                        VendorSpec.evidence_id == ev_id,
                    )
                )
            )
            existing_list = list(existing.scalars().all())
            if existing_list:
                return existing_list

        # Load the evidence's locations with their segments.
        stmt = (
            select(EvidenceLocation, OemTextSegment)
            .where(EvidenceLocation.evidence_id == ev_id)
            .outerjoin(
                OemTextSegment,
                EvidenceLocation.oem_text_segment_id
                == OemTextSegment.id,
            )
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        # Also delete any existing specs for this evidence (idempotent).
        await self._session.execute(
            delete(VendorSpec).where(
                VendorSpec.evidence_id == ev_id
            )
        )
        await self._session.flush()

        created: list[VendorSpec] = []

        for loc, seg in rows:
            if seg is None:
                continue

            ocr_warning = (
                loc.ocr_confidence is not None and loc.ocr_confidence < 0.9
            ) or (seg.ocr_confidence is not None and seg.ocr_confidence < 0.9)

            specs = parse_vendor_specs(
                seg.text,
                ocr_warning=ocr_warning,
                source_page_number=seg.page_number,
                char_start=loc.char_start or seg.start_char,
                char_end=loc.char_end or seg.end_char,
                ocr_confidence=seg.ocr_confidence,
                location_type=loc.location_type,
            )

            for ps in specs:
                vs = VendorSpec(
                    evidence_id=ev_id,
                    requirement_id=req_id,
                    oem_document_version_id=evidence.oem_document_version_id,
                    oem_text_segment_id=seg.id if seg else None,
                    parameter=ps.parameter,
                    entity=ps.entity,
                    value=ps.value,
                    lower_bound=ps.lower_bound,
                    upper_bound=ps.upper_bound,
                    unit=ps.unit,
                    tolerance=ps.tolerance,
                    qualitative_statement=ps.qualitative_statement,
                    conditions=ps.conditions,
                    source_text=ps.source_text,
                    source_page_number=ps.source_page_number,
                    char_start=ps.char_start,
                    char_end=ps.char_end,
                    ocr_confidence=ps.ocr_confidence,
                    location_type=ps.location_type,
                    extraction_method=VendorSpecExtractionMethod.DETERMINISTIC,
                    extraction_version=VENDOR_SPEC_VERSION,
                    normalization_state=ps.normalization_state,
                    issues=list(ps.issues) if ps.issues else None,
                )
                self._session.add(vs)
                created.append(vs)

        await self._session.flush()

        # Audit the extraction.
        await self._audit.log(
            organization_id=auth.organization_id,
            action="vendor_spec.extracted",
            actor_id=auth.actor_id,
            entity_type="evidence",
            entity_id=ev_id,
            project_id=proj_id,
            metadata={
                "extraction_version": VENDOR_SPEC_VERSION,
                "num_specs": len(created),
                "requirement_id": str(req_id),
            },
        )

        await self._session.commit()

        # Refresh to get committed state.
        for vs in created:
            await self._session.refresh(vs)

        return created

    async def list_vendor_specs(
        self,
        auth: AuthContext,
        project_id: str,
        requirement_id: str,
        *,
        evidence_id: str | None = None,
    ) -> list[VendorSpec]:
        """List vendor specs for a requirement (tenant-scoped).

        Optionally filter by evidence_id.  Only specs from accepted evidence
        are returned.
        """

        proj_id = uuid.UUID(project_id)
        req_id = uuid.UUID(requirement_id)

        stmt = (
            select(VendorSpec)
            .join(Evidence, VendorSpec.evidence_id == Evidence.id)
            .join(
                OemDocumentVersion,
                VendorSpec.oem_document_version_id
                == OemDocumentVersion.id,
            )
            .join(
                OemDocument,
                OemDocumentVersion.document_id == OemDocument.id,
            )
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                and_(
                    VendorSpec.requirement_id == req_id,
                    Project.id == proj_id,
                    Project.organization_id == auth.organization_id,
                    Evidence.review_state == EvidenceReviewState.ACCEPTED,
                )
            )
        )

        if evidence_id is not None:
            stmt = stmt.where(
                VendorSpec.evidence_id == uuid.UUID(evidence_id)
            )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())
