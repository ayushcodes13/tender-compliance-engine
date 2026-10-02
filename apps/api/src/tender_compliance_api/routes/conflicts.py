"""CP56 — Conflict and contradiction detection API routes.

Endpoints:
- GET  /projects/{project_id}/requirements/{requirement_id}/conflicts
- POST /projects/{project_id}/requirements/{requirement_id}/detect-conflicts
- GET  /projects/{project_id}/conflicts/{conflict_id}
- POST /projects/{project_id}/conflicts/{conflict_id}/resolve
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.compliance.conflict_detection import (
    ConflictDetectionService,
    ConflictSource,
    DetectedConflict,
)
from tender_compliance_api.db.models import ConflictResolution
from tender_compliance_api.db.session import get_session

router = APIRouter(
    prefix="/api/projects",
    tags=["conflicts"],
)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ConflictSourceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    vendor_spec_id: str | None
    oem_document_version_id: str | None
    source_text: str
    value: float | None
    unit: str | None
    source_page_number: int | None
    condition: str | None


class ConflictSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    requirement_id: uuid.UUID
    conflict_type: str
    parameter: str | None
    entity: str | None
    sources: list[dict[str, Any]]
    tender_claim: str | None
    tender_vendor_spec_id: uuid.UUID | None
    resolution: str
    resolution_notes: str | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class ResolveConflictRequest(BaseModel):
    resolution: ConflictResolution
    notes: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class DetectedConflictSchema(BaseModel):
    conflict_type: str
    parameter: str | None
    entity: str | None
    sources: list[ConflictSourceSchema]
    tender_claim: str | None
    tender_vendor_spec_id: uuid.UUID | None

    @classmethod
    def from_detected(cls, dc: DetectedConflict) -> DetectedConflictSchema:
        return cls(
            conflict_type=dc.conflict_type,
            parameter=dc.parameter,
            entity=dc.entity,
            sources=[
                ConflictSourceSchema(
                    evidence_id=s.evidence_id,
                    vendor_spec_id=s.vendor_spec_id,
                    oem_document_version_id=s.oem_document_version_id,
                    source_text=s.source_text,
                    value=s.value,
                    unit=s.unit,
                    source_page_number=s.source_page_number,
                    condition=s.condition,
                )
                for s in dc.sources
            ],
            tender_claim=dc.tender_claim,
            tender_vendor_spec_id=dc.tender_vendor_spec_id,
        )


# ---------------------------------------------------------------------------
# Router dependencies
# ---------------------------------------------------------------------------


def _get_service(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
) -> ConflictDetectionService:
    return ConflictDetectionService(
        db=session, audit=AuditService(session)
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{project_id}/requirements/{requirement_id}/conflicts",
    response_model=list[ConflictSchema],
    summary="List all conflicts for a requirement",
)
async def list_conflicts(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: ConflictDetectionService = Depends(_get_service),  # noqa: B008
) -> list[ConflictSchema]:
    conflicts = await service.list_conflicts(
        auth=auth, project_id=project_id, requirement_id=requirement_id
    )
    return [ConflictSchema.model_validate(c) for c in conflicts]


@router.post(
    "/{project_id}/requirements/{requirement_id}/detect-conflicts",
    response_model=list[DetectedConflictSchema],
    summary="Run conflict detection for a requirement",
)
async def detect_conflicts(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    persist: bool = Body(
        default=False,
        description="If true, detected conflicts are also persisted.",
    ),
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: ConflictDetectionService = Depends(_get_service),  # noqa: B008
) -> list[DetectedConflictSchema]:
    if persist:
        persisted = await service.detect_and_record(
            auth=auth,
            project_id=project_id,
            requirement_id=requirement_id,
        )
        # Convert persisted Conflict records back to DetectedConflictSchema.
        result: list[DetectedConflictSchema] = []
        for c in persisted:
            sources: list[ConflictSource] = []
            for s in c.sources:
                sources.append(
                    ConflictSource(
                        evidence_id=s.get("evidence_id", ""),
                        vendor_spec_id=s.get("vendor_spec_id"),
                        oem_document_version_id=s.get(
                            "oem_document_version_id"
                        ),
                        source_text=s.get("source_text", ""),
                        value=s.get("value"),
                        unit=s.get("unit"),
                        source_page_number=s.get("source_page_number"),
                        condition=s.get("condition"),
                    )
                )
            result.append(
                DetectedConflictSchema.from_detected(
                    DetectedConflict(
                        conflict_type=c.conflict_type,
                        parameter=c.parameter,
                        entity=c.entity,
                        sources=sources,
                        tender_claim=c.tender_claim,
                        tender_vendor_spec_id=c.tender_vendor_spec_id,
                    )
                )
            )
        return result

    detected = await service.detect_conflicts(
        auth=auth, project_id=project_id, requirement_id=requirement_id
    )
    return [DetectedConflictSchema.from_detected(dc) for dc in detected]


@router.get(
    "/{project_id}/conflicts/{conflict_id}",
    response_model=ConflictSchema,
    summary="Get a single conflict by ID",
)
async def get_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: ConflictDetectionService = Depends(_get_service),  # noqa: B008
) -> ConflictSchema:
    conflict = await service.get_conflict(
        auth=auth,
        project_id=project_id,
        conflict_id=conflict_id,
    )
    if conflict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict {conflict_id} not found in project {project_id}",
        )
    return ConflictSchema.model_validate(conflict)


@router.post(
    "/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=ConflictSchema,
    summary="Resolve a conflict (ACCEPTED or REJECTED)",
)
async def resolve_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req_body: ResolveConflictRequest = Depends(),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    service: ConflictDetectionService = Depends(_get_service),  # noqa: B008
) -> ConflictSchema:
    try:
        conflict = await service.resolve_conflict(
            auth=auth,
            project_id=project_id,
            conflict_id=conflict_id,
            resolution=req_body.resolution,
            notes=req_body.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if conflict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict {conflict_id} not found in project {project_id}",
        )
    return ConflictSchema.model_validate(conflict)
