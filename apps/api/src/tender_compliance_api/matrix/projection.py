"""Canonical Phase 1 matrix projection (CP41).

A single deterministic function powers both the matrix UI and the XLSX export.
It projects the current non-superseded requirement state of a document version
into the matrix column layout:

    S.No. | Requirement ID | Tender Requirement | Category | Clause | Source Page
          | Mandatory | User Notes | Review Status

Missing fields are represented honestly as ``None`` — never fabricated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.db.models import (
    Category,
    ClarificationRequest,
    ComplianceAssessment,
    Conflict,
    ConflictResolution,
    Deviation,
    Evidence,
    EvidenceReviewState,
    OemDocument,
    OemDocumentVersion,
    Requirement,
    RequirementNote,
    RequirementSource,
    VendorSpec,
    requirement_categories,
)


@dataclass(frozen=True)
class MatrixRow:
    """A single row in the Phase 1 compliance matrix.

    Column order matches the canonical projection defined in checkpoint.md
    (CP41).  All fields are read at query time — no business logic is
    duplicated in the exporter.

    ``normalized_text``, ``raw_source``, ``uncertainty``, and ``ocr_warning``
    are carried for transparency and used by the XLSX writer; they are not
    displayed in the default matrix UI but are available for the export.
    """

    serial: int
    requirement_id: UUID
    tender_requirement: str
    category: str | None
    clause: str | None
    source_page: int | None
    mandatory: bool | None
    user_notes: str | None
    review_status: str

    # Source-provenance fields (not in the default matrix view):
    normalized_text: str
    raw_source: str
    uncertainty: str
    ocr_warning: bool

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict (used by the XLSX writer)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


async def project_matrix_rows(
    session: AsyncSession,
    document_version_id: UUID,
) -> list[MatrixRow]:
    """Return the canonical matrix rows for a document version.

    Excludes superseded requirements.  Preserves explicit ``display_order``
    (NULLs sort last), falling back to ``created_at`` desc then ``id``.

    Every column is populated from a deterministic query so that the
    matrix UI and the XLSX writer share one source of truth.
    """
    # 1. Fetch all non-superseded requirements in canonical order.
    req_result = await session.execute(
        select(Requirement)
        .where(
            Requirement.document_version_id == document_version_id,
            Requirement.superseded.is_(False),
        )
        .order_by(
            Requirement.display_order.asc().nulls_last(),
            Requirement.created_at.desc(),
            Requirement.id.asc(),
        )
    )
    requirements: Sequence[Requirement] = (
        req_result.scalars().unique().all()
    )

    if not requirements:
        return []

    req_ids: list[UUID] = [r.id for r in requirements]

    # 2. Fetch latest note text per requirement (batch).
    note_result = await session.execute(
        select(
            RequirementNote.requirement_id,
            RequirementNote.text,
            RequirementNote.created_at,
        )
        .where(
            RequirementNote.requirement_id.in_(req_ids),
            RequirementNote.document_version_id == document_version_id,
        )
        .order_by(RequirementNote.created_at.desc())
    )
    latest_note_by_req: dict[UUID, str] = {}
    for note_row in note_result:
        if note_row.requirement_id not in latest_note_by_req:
            latest_note_by_req[note_row.requirement_id] = note_row.text

    # 3. Fetch the first category (by display_order) per requirement (batch).
    cat_result = await session.execute(
        select(Category.name, requirement_categories.c.requirement_id)
        .join(
            requirement_categories,
            Category.id == requirement_categories.c.category_id,
        )
        .where(requirement_categories.c.requirement_id.in_(req_ids))
        .order_by(Category.display_order.asc().nulls_last(), Category.name)
    )
    first_cat_by_req: dict[UUID, str] = {}
    for cat_row in cat_result:
        req_id = cat_row.requirement_id
        if req_id not in first_cat_by_req:
            first_cat_by_req[req_id] = cat_row.name

    # 4. Fetch the lowest page number per requirement (batch).
    page_result = await session.execute(
        select(
            RequirementSource.requirement_id,
            func.min(RequirementSource.page_number).label("min_page"),
        )
        .where(RequirementSource.requirement_id.in_(req_ids))
        .group_by(RequirementSource.requirement_id)
    )
    first_page_by_req: dict[UUID, int | None] = {}
    for page_row in page_result:
        first_page_by_req[page_row.requirement_id] = page_row.min_page

    # 5. Assemble MatrixRow objects in canonical order.
    rows: list[MatrixRow] = []
    for i, req in enumerate(requirements, start=1):
        rows.append(
            MatrixRow(
                serial=i,
                requirement_id=req.id,
                tender_requirement=req.normalized_text,
                category=first_cat_by_req.get(req.id),
                clause=req.clause_number,
                source_page=first_page_by_req.get(req.id),
                mandatory=req.mandatory,
                user_notes=latest_note_by_req.get(req.id),
                review_status=req.review_state.value,
                normalized_text=req.normalized_text,
                raw_source=req.raw_source,
                uncertainty=req.uncertainty,
                ocr_warning=req.ocr_warning,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# CP59 — Final compliance matrix and submission projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinalMatrixRow:
    """A single row in the final (Phase 2) compliance matrix.

    Extends the Phase 1 :class:`MatrixRow` columns with vendor-response,
    evidence, assessment, conflict, clarification, and deviation fields so
    that one canonical projection powers both the final matrix UI and all
    exports (CP60).

    Design principles:
    - Original Phase 1 tender columns are preserved verbatim.
    - Phase 2 columns are ``None`` when the corresponding state does not exist
      (e.g. no evidence accepted → ``None``, not a fabricated default).
    - Unreviewed / unresolved / not-demonstrated requirements are **visible**,
      never hidden — per CP59 guardrail.
    - Only the **latest** assessment per requirement is surfaced (highest
      ``assessment_version``); the full history remains in
      ``compliance_assessments``.
    """

    # --- Phase 1 columns (same as MatrixRow) ---
    serial: int
    requirement_id: UUID
    tender_requirement: str
    category: str | None
    clause: str | None
    source_page: int | None
    mandatory: bool | None
    user_notes: str | None
    review_status: str
    normalized_text: str
    raw_source: str
    uncertainty: str
    ocr_warning: bool

    # --- Phase 2: Evidence + Vendor Spec ---
    evidence_id: UUID | None
    evidence_score: float | None
    evidence_oem_document: str | None
    evidence_oem_version: int | None
    vendor_spec_parameter: str | None
    vendor_spec_value: float | None
    vendor_spec_unit: str | None
    vendor_spec_lower_bound: float | None
    vendor_spec_upper_bound: float | None
    vendor_spec_source_text: str | None
    vendor_spec_source_page: int | None
    vendor_spec_extraction_method: str | None
    vendor_spec_issues: list[str] | None

    # --- Phase 2: Assessment ---
    assessment_status: str | None
    assessment_suggested_status: str | None
    assessment_reason_code: str | None
    assessment_reason_text: str | None
    assessment_is_confirmed: bool | None
    assessment_reviewer_id: UUID | None
    assessment_reviewed_at: datetime | None
    assessment_version: int | None

    # --- Phase 2: Review state summary ---
    has_unresolved_conflict: bool
    clarification_statuses: list[str]
    deviation_statuses: list[str]

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict (used by the XLSX writer)."""
        return asdict(self)


async def project_final_matrix_rows(
    session: AsyncSession,
    document_version_id: UUID,
) -> list[FinalMatrixRow]:
    """Return the final (Phase 2) compliance matrix rows for a document version.

    Keeps all Phase 1 columns and layers on top:

    - The latest accepted evidence + its latest vendor spec per requirement.
    - The latest compliance assessment (highest ``assessment_version``).
    - Unresolved conflict count, clarification statuses, and deviation statuses.

    All Phase 2 columns are ``None`` when no corresponding state exists —
    nothing is fabricated.  Requirements without evidence remain visible
    with ``assessment_status = None``.
    """
    # 1. Fetch non-superseded requirements in canonical order (Phase 1 logic).
    req_result = await session.execute(
        select(Requirement)
        .where(
            Requirement.document_version_id == document_version_id,
            Requirement.superseded.is_(False),
        )
        .order_by(
            Requirement.display_order.asc().nulls_last(),
            Requirement.created_at.desc(),
            Requirement.id.asc(),
        )
    )
    requirements: Sequence[Requirement] = req_result.scalars().unique().all()

    if not requirements:
        return []

    req_ids: list[UUID] = [r.id for r in requirements]

    # 2. Phase 1 batch lookups (shared with project_matrix_rows).
    # Latest note per requirement.
    note_result = await session.execute(
        select(
            RequirementNote.requirement_id,
            RequirementNote.text,
            RequirementNote.created_at,
        )
        .where(
            RequirementNote.requirement_id.in_(req_ids),
        )
        .order_by(desc(RequirementNote.created_at))
    )
    latest_note_by_req: dict[UUID, str] = {}
    for note_row in note_result:
        if note_row.requirement_id not in latest_note_by_req:
            latest_note_by_req[note_row.requirement_id] = note_row.text

    # First category per requirement.
    cat_result = await session.execute(
        select(Category.name, requirement_categories.c.requirement_id)
        .join(
            requirement_categories,
            Category.id == requirement_categories.c.category_id,
        )
        .where(requirement_categories.c.requirement_id.in_(req_ids))
        .order_by(Category.display_order.asc().nulls_last(), Category.name)
    )
    first_cat_by_req: dict[UUID, str] = {}
    for cat_row in cat_result:
        if cat_row.requirement_id not in first_cat_by_req:
            first_cat_by_req[cat_row.requirement_id] = cat_row.name

    # Lowest source page per requirement.
    page_result = await session.execute(
        select(
            RequirementSource.requirement_id,
            func.min(RequirementSource.page_number).label("min_page"),
        )
        .where(RequirementSource.requirement_id.in_(req_ids))
        .group_by(RequirementSource.requirement_id)
    )
    first_page_by_req: dict[UUID, int | None] = {
        row.requirement_id: row.min_page for row in page_result
    }

    # 3. Latest accepted evidence + vendor spec per requirement (Phase 2).
    ev_result = await session.execute(
        select(
            Evidence.requirement_id,
            Evidence.id.label("evidence_id"),
            Evidence.score.label("evidence_score"),
            OemDocument.display_name.label("oem_display_name"),
            OemDocumentVersion.version_number.label("oem_version"),
            VendorSpec.parameter.label("vs_parameter"),
            VendorSpec.value.label("vs_value"),
            VendorSpec.unit.label("vs_unit"),
            VendorSpec.lower_bound.label("vs_lower"),
            VendorSpec.upper_bound.label("vs_upper"),
            VendorSpec.source_text.label("vs_source_text"),
            VendorSpec.source_page_number.label("vs_source_page"),
            VendorSpec.extraction_method.label("vs_extraction_method"),
            VendorSpec.issues.label("vs_issues"),
        )
        .join(VendorSpec, VendorSpec.evidence_id == Evidence.id)
        .join(
            OemDocumentVersion,
            VendorSpec.oem_document_version_id == OemDocumentVersion.id,
        )
        .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
        .where(
            Evidence.requirement_id.in_(req_ids),
            Evidence.review_state == EvidenceReviewState.ACCEPTED,
        )
        .order_by(
            desc(Evidence.created_at),
            desc(VendorSpec.created_at),
        )
    )
    latest_ev_by_req: dict[UUID, Any] = {}
    for ev_row in ev_result:
        req_id = ev_row.requirement_id
        if req_id not in latest_ev_by_req:
            latest_ev_by_req[req_id] = ev_row

    # 4. Latest compliance assessment per requirement (highest version).
    assess_result = await session.execute(
        select(
            ComplianceAssessment.requirement_id,
            ComplianceAssessment.status.label("assessment_status"),
            ComplianceAssessment.suggested_status.label(
                "assessment_suggested_status"
            ),
            ComplianceAssessment.reason_code.label("assessment_reason_code"),
            ComplianceAssessment.reason_text.label("assessment_reason_text"),
            ComplianceAssessment.is_confirmed_by_human.label(
                "assessment_is_confirmed"
            ),
            ComplianceAssessment.reviewer_id.label("assessment_reviewer_id"),
            ComplianceAssessment.reviewed_at.label("assessment_reviewed_at"),
            ComplianceAssessment.assessment_version.label(
                "assessment_version"
            ),
        )
        .where(ComplianceAssessment.requirement_id.in_(req_ids))
        .order_by(
            ComplianceAssessment.requirement_id,
            desc(ComplianceAssessment.assessment_version),
        )
    )
    latest_assess_by_req: dict[UUID, Any] = {}
    for assess_row in assess_result:
        # Rows ordered by version DESC within each requirement — first seen
        # is the latest version.
        if assess_row.requirement_id not in latest_assess_by_req:
            latest_assess_by_req[assess_row.requirement_id] = assess_row

    # 5. Unresolved conflict count per requirement.
    conflict_result = await session.execute(
        select(
            Conflict.requirement_id,
            func.count().label("conflict_count"),
        )
        .where(
            Conflict.requirement_id.in_(req_ids),
            Conflict.resolution == ConflictResolution.UNRESOLVED,
        )
        .group_by(Conflict.requirement_id)
    )
    conflict_count_by_req: dict[UUID, int] = {
        row.requirement_id: row.conflict_count
        for row in conflict_result
    }

    # 6. Clarification statuses per requirement.
    cl_result = await session.execute(
        select(
            ClarificationRequest.requirement_id,
            ClarificationRequest.status.label("clar_status"),
        ).where(ClarificationRequest.requirement_id.in_(req_ids))
    )
    clar_by_req: dict[UUID, list[str]] = {}
    for clar_row in cl_result:
        if clar_row.requirement_id is not None:
            clar_by_req.setdefault(
                clar_row.requirement_id, []
            ).append(clar_row.clar_status.value)
    for statuses in clar_by_req.values():
        statuses.sort()

    # 7. Deviation statuses per requirement.
    dev_result = await session.execute(
        select(
            Deviation.requirement_id,
            Deviation.status.label("dev_status"),
        ).where(Deviation.requirement_id.in_(req_ids))
    )
    dev_by_req: dict[UUID, list[str]] = {}
    for dev_row in dev_result:
        dev_by_req.setdefault(
            dev_row.requirement_id, []
        ).append(dev_row.dev_status.value)

    # 8. Assemble FinalMatrixRow objects in canonical order.
    rows: list[FinalMatrixRow] = []
    for i, req in enumerate(requirements, start=1):
        ev = latest_ev_by_req.get(req.id)
        assess = latest_assess_by_req.get(req.id)

        rows.append(
            FinalMatrixRow(
                serial=i,
                requirement_id=req.id,
                tender_requirement=req.normalized_text,
                category=first_cat_by_req.get(req.id),
                clause=req.clause_number,
                source_page=first_page_by_req.get(req.id),
                mandatory=req.mandatory,
                user_notes=latest_note_by_req.get(req.id),
                review_status=req.review_state.value,
                normalized_text=req.normalized_text,
                raw_source=req.raw_source,
                uncertainty=req.uncertainty,
                ocr_warning=req.ocr_warning,
                # Evidence + vendor spec.
                evidence_id=ev.evidence_id if ev else None,
                evidence_score=ev.evidence_score if ev else None,
                evidence_oem_document=ev.oem_display_name if ev else None,
                evidence_oem_version=ev.oem_version if ev else None,
                vendor_spec_parameter=ev.vs_parameter if ev else None,
                vendor_spec_value=float(ev.vs_value) if ev and ev.vs_value else None,
                vendor_spec_unit=ev.vs_unit if ev else None,
                vendor_spec_lower_bound=(
                    float(ev.vs_lower) if ev and ev.vs_lower else None
                ),
                vendor_spec_upper_bound=(
                    float(ev.vs_upper) if ev and ev.vs_upper else None
                ),
                vendor_spec_source_text=ev.vs_source_text if ev else None,
                vendor_spec_source_page=ev.vs_source_page if ev else None,
                vendor_spec_extraction_method=(
                    ev.vs_extraction_method.value
                    if ev and ev.vs_extraction_method
                    else None
                ),
                vendor_spec_issues=ev.vs_issues if ev else None,
                # Assessment.
                assessment_status=(
                    assess.assessment_status.value
                    if assess and assess.assessment_status
                    else None
                ),
                assessment_suggested_status=(
                    assess.assessment_suggested_status.value
                    if assess and assess.assessment_suggested_status
                    else None
                ),
                assessment_reason_code=(
                    assess.assessment_reason_code if assess else None
                ),
                assessment_reason_text=(
                    assess.assessment_reason_text if assess else None
                ),
                assessment_is_confirmed=(
                    assess.assessment_is_confirmed if assess else None
                ),
                assessment_reviewer_id=(
                    assess.assessment_reviewer_id if assess else None
                ),
                assessment_reviewed_at=(
                    assess.assessment_reviewed_at if assess else None
                ),
                assessment_version=(
                    assess.assessment_version if assess else None
                ),
                # Review state summary.
                has_unresolved_conflict=bool(
                    conflict_count_by_req.get(req.id, 0) > 0
                ),
                clarification_statuses=clar_by_req.get(req.id, []),
                deviation_statuses=dev_by_req.get(req.id, []),
            )
        )

    return rows
