"""Vendor specification extraction API routes (CP52).

Endpoints:
* ``GET  /projects/{id}/requirements/{rid}/evidence/{eid}/vendor-specs``
  — list extracted vendor specs for an accepted evidence item.
* ``POST /projects/{id}/requirements/{rid}/evidence/{eid}/vendor-specs/extract``
  — run deterministic vendor spec extraction on the evidence's source text.

Every vendor fact is traceable: the response includes ``source_text``,
``source_page_number``, and ``char_start``/``char_end`` offsets.  Only
specs extracted from **accepted** evidence are persisted or returned.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import VendorSpec
from tender_compliance_api.db.session import get_session
from tender_compliance_api.vendor_spec.service import VendorSpecService

router = APIRouter(
    prefix="/projects/{project_id}/requirements/{requirement_id}/evidence/{evidence_id}/vendor-specs",
    tags=["vendor_specs"],
)


class VendorSpecLocationResponse(BaseModel):
    """Source location anchor for a vendor spec."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    char_start: int | None = None
    char_end: int | None = None
    source_text: str | None = None


class VendorSpecResponse(BaseModel):
    """A single structured vendor specification."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    evidence_id: str
    requirement_id: str
    oem_document_version_id: str
    oem_text_segment_id: str | None = None
    parameter: str
    entity: str | None = None
    value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    unit: str | None = None
    tolerance: float | None = None
    qualitative_statement: str | None = None
    conditions: dict[str, Any] | None = None
    source_text: str
    source_page_number: int
    char_start: int | None = None
    char_end: int | None = None
    ocr_confidence: float | None = None
    location_type: str
    extraction_method: str
    extraction_version: str
    normalization_state: str
    issues: list[str] | None = None
    created_at: str | None = None


class ExtractResponse(BaseModel):
    """Response from running vendor spec extraction."""

    vendor_specs: list[VendorSpecResponse]
    num_extracted: int


@router.get("", response_model=list[VendorSpecResponse])
async def list_vendor_specs(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    evidence_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[VendorSpecResponse]:
    """List extracted vendor specs for an accepted evidence item (tenant-scoped)."""

    svc = VendorSpecService(session)
    specs = await svc.list_vendor_specs(
        auth,
        str(project_id),
        str(requirement_id),
        evidence_id=str(evidence_id),
    )

    return [_to_response(s) for s in specs]


@router.post("/extract", response_model=ExtractResponse)
async def extract_vendor_specs(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    evidence_id: uuid.UUID,
    force_rerun: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ExtractResponse:
    """Run deterministic vendor spec extraction on accepted evidence.

    Scans the OEM text segments linked to the evidence's locations and
    persists structured vendor specifications.  Existing specs for this
    evidence are replaced (idempotent).

    If the evidence is not in the ``accepted`` review state, no specs are
    extracted — unreviewed system candidates cannot produce vendor facts.
    """

    svc = VendorSpecService(session)
    specs = await svc.extract_specs_for_evidence(
        auth,
        str(project_id),
        str(requirement_id),
        str(evidence_id),
        force_rerun=force_rerun,
    )

    return ExtractResponse(
        vendor_specs=[_to_response(s) for s in specs],
        num_extracted=len(specs),
    )


def _to_response(spec: VendorSpec) -> VendorSpecResponse:
    """Convert a VendorSpec model instance to a response DTO."""
    return VendorSpecResponse(
        id=str(spec.id),
        evidence_id=str(spec.evidence_id),
        requirement_id=str(spec.requirement_id),
        oem_document_version_id=str(spec.oem_document_version_id),
        oem_text_segment_id=str(spec.oem_text_segment_id)
        if spec.oem_text_segment_id
        else None,
        parameter=spec.parameter,
        entity=spec.entity,
        value=float(spec.value) if spec.value is not None else None,
        lower_bound=float(spec.lower_bound)
        if spec.lower_bound is not None
        else None,
        upper_bound=float(spec.upper_bound)
        if spec.upper_bound is not None
        else None,
        unit=spec.unit,
        tolerance=float(spec.tolerance) if spec.tolerance is not None else None,
        qualitative_statement=spec.qualitative_statement,
        conditions=spec.conditions,
        source_text=spec.source_text,
        source_page_number=spec.source_page_number,
        char_start=spec.char_start,
        char_end=spec.char_end,
        ocr_confidence=float(spec.ocr_confidence)
        if spec.ocr_confidence is not None
        else None,
        location_type=spec.location_type,
        extraction_method=spec.extraction_method.value,
        extraction_version=spec.extraction_version,
        normalization_state=spec.normalization_state.value,
        issues=list(spec.issues) if spec.issues else None,
        created_at=spec.created_at.isoformat() if spec.created_at else None,
    )
