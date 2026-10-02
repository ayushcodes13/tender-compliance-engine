"""Evidence retrieval and curation API routes (CP50).

These endpoints allow:
* ``GET  /projects/{id}/requirements/{rid}/evidence`` — list existing
  evidence candidates for a requirement.
* ``POST /projects/{id}/requirements/{rid}/evidence/propose`` — run a
  deterministic keyword retrieval and propose evidence candidates.

The retrieval is intentionally conservative: zero/weak retrieval is treated
as **missing evidence**, not non-compliance.  Every candidate carries exact
source linkage (page, offset, segment id) so the reviewer can open the
actual OEM source.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    DocumentVersion,
    EvidenceReviewState,
    OemDocument,
    OemDocumentVersion,
    Project,
    Requirement,
    TenderDocument,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.retrieval.service import RetrievalService

router = APIRouter(
    prefix="/projects/{project_id}/requirements/{requirement_id}/evidence",
    tags=["evidence"],
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class EvidenceLocationResponse(BaseModel):
    """A source location anchor for an evidence candidate."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    clause_number: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    location_type: str
    source_text: str | None = None
    ocr_confidence: float | None = None


class EvidenceCandidateResponse(BaseModel):
    """A proposed evidence candidate returned by retrieval."""

    oem_document_version_id: str
    oem_document_display_name: str | None = None
    oem_document_type: str | None = None
    version_number: int
    score: float
    matched_terms: list[str]
    page_number: int
    char_start: int | None = None
    char_end: int | None = None
    source_text: str | None = None


class EvidenceResponse(BaseModel):
    """A persisted evidence candidate with its locations."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    oem_document_version_id: str
    score: float | None = None
    retrieval_method: str
    review_state: str
    created_at: str
    locations: list[EvidenceLocationResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _verify_requirement_access(
    session: AsyncSession,
    auth: AuthContext,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
) -> Requirement | None:
    """Return the requirement if it belongs to *auth*'s org, else None.

    Joins Requirement → DocumentVersion → TenderDocument → Project to
    enforce tenant scoping at the database level.
    """
    result = await session.execute(
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
            and_(
                Requirement.id == requirement_id,
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[EvidenceResponse])
async def list_evidence(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    review_state: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[EvidenceResponse]:
    """List evidence candidates for a requirement (tenant-scoped).

    Optionally filter by ``review_state`` (proposed, accepted, rejected).
    """
    req = await _verify_requirement_access(
        session, auth, project_id, requirement_id
    )
    if req is None:
        raise HTTPException(
            status_code=404,
            detail="Requirement not found in this project/organization",
        )

    svc = RetrievalService(session)
    items = await svc.list_evidence(
        auth,
        str(project_id),
        str(requirement_id),
        review_state=review_state,
    )

    responses: list[EvidenceResponse] = []
    for ev in items:
        locations = [
            EvidenceLocationResponse(
                page_number=loc.page_number,
                clause_number=loc.clause_number,
                char_start=loc.char_start,
                char_end=loc.char_end,
                location_type=loc.location_type,
                source_text=loc.source_text,
                ocr_confidence=loc.ocr_confidence,
            )
            for loc in (ev.locations or [])
        ]
        responses.append(
            EvidenceResponse(
                id=str(ev.id),
                oem_document_version_id=str(ev.oem_document_version_id),
                score=float(ev.score) if ev.score is not None else None,
                retrieval_method=ev.retrieval_method,
                review_state=ev.review_state.value,
                created_at=ev.created_at.isoformat() if ev.created_at else "",
                locations=locations,
            )
        )
    return responses


class ProposeRequest(BaseModel):
    """Request body for proposing evidence candidates."""

    query_terms: list[str] = Field(default_factory=list)
    k: int = Field(default=10, ge=1, le=100)
    persist: bool = Field(default=False)


@router.post(
    "/propose",
    response_model=list[EvidenceCandidateResponse],
)
async def propose_evidence(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    req: ProposeRequest = Body(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[EvidenceCandidateResponse]:
    """Run deterministic keyword retrieval and return ranked evidence.

    Searches all OEM text segments in the project, scores them with
    TF-IDF-style term-frequency weighting against *query_terms*, and returns
    the top-*k* candidates.  Each candidate is source-linked (page, char
    offsets, segment id).

    If ``persist`` is true, candidates are stored as ``Evidence`` rows
    (review_state=PROPOSED).

    Zero or low scores mean **no matching evidence found** — treated as
    missing evidence, never as non-compliance.
    """
    req_obj = await _verify_requirement_access(
        session, auth, project_id, requirement_id
    )
    if req_obj is None:
        raise HTTPException(
            status_code=404,
            detail="Requirement not found in this project/organization",
        )

    svc = RetrievalService(session)
    candidates = await svc.propose_evidence(
        auth,
        str(project_id),
        str(requirement_id),
        req.query_terms,
        k=req.k,
    )

    if req.persist and candidates:
        await svc.persist_evidence(
            auth,
            str(project_id),
            str(requirement_id),
            candidates,
        )

    # Build response with document metadata for each candidate.
    doc_meta: dict[str, tuple[str, str, int]] = {}
    for cand in candidates:
        key = cand.oem_document_version_id
        if key not in doc_meta:
            ver = await session.get(
                OemDocumentVersion,
                uuid.UUID(cand.oem_document_version_id),
            )
            if ver:
                doc = await session.get(OemDocument, ver.document_id)
                if doc:
                    doc_meta[key] = (
                        doc.display_name,
                        doc.document_type.value,
                        ver.version_number,
                    )
                else:
                    doc_meta[key] = ("", "", ver.version_number)
            else:
                doc_meta[key] = ("", "", 0)

    return [
        EvidenceCandidateResponse(
            oem_document_version_id=cand.oem_document_version_id,
            oem_document_display_name=doc_meta.get(
                cand.oem_document_version_id, ("", "", 0)
            )[0],
            oem_document_type=doc_meta.get(
                cand.oem_document_version_id, ("", "", 0)
            )[1],
            version_number=doc_meta.get(
                cand.oem_document_version_id, ("", "", 0)
            )[2],
            score=cand.score,
            matched_terms=cand.matched_terms,
            page_number=cand.page_number,
            char_start=cand.char_start,
            char_end=cand.char_end,
            source_text=cand.source_text,
        )
        for cand in candidates
    ]


@router.post(
    "/{evidence_id}/curate",
    response_model=EvidenceResponse,
)
async def curate_evidence(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    evidence_id: uuid.UUID,
    review_state: str = Query(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> EvidenceResponse:
    """Set the review state of an evidence candidate (accept/reject)."""
    try:
        EvidenceReviewState(review_state)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid review_state: {review_state}. "
            f"Valid: {[e.value for e in EvidenceReviewState]}",
        ) from None

    svc = RetrievalService(session)
    ev = await svc.curate_evidence(
        auth,
        str(evidence_id),
        review_state,
    )
    if ev is None:
        raise HTTPException(
            status_code=404,
            detail="Evidence not found in this project/organization",
        )

    return EvidenceResponse(
        id=str(ev.id),
        oem_document_version_id=str(ev.oem_document_version_id),
        score=float(ev.score) if ev.score is not None else None,
        retrieval_method=ev.retrieval_method,
        review_state=ev.review_state.value,
        created_at=ev.created_at.isoformat() if ev.created_at else "",
        locations=[
            EvidenceLocationResponse(
                page_number=loc.page_number,
                clause_number=loc.clause_number,
                char_start=loc.char_start,
                char_end=loc.char_end,
                location_type=loc.location_type,
                source_text=loc.source_text,
                ocr_confidence=loc.ocr_confidence,
            )
            for loc in (ev.locations or [])
        ],
    )
