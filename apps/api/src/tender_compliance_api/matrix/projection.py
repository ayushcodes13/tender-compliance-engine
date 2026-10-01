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
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.db.models import (
    Category,
    Requirement,
    RequirementNote,
    RequirementSource,
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
