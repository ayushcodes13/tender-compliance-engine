"""Project lifecycle API routes (CP10).

Provides REST endpoints for creating, reading, updating, archiving, and
reopening projects.  All routes are tenant-scoped via AuthContext.

Business rules live in ProjectService (CP09); these routes are thin
transport adapters that manage the transaction boundary (commit/rollback)
and map domain errors to HTTP status codes.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    Project,
    ProjectStatus,
    StoredObject,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.logs import get_correlation_id, get_logger, log_event
from tender_compliance_api.project import (
    ProjectArchivedError,
    ProjectNotFoundError,
    ProjectService,
    StateTransitionError,
)
from tender_compliance_api.retention import (
    RetentionService,
)

# Exception types raised by ProjectService that routes translate to HTTP.
_ProjectErrors = (
    ProjectNotFoundError,
    ProjectArchivedError,
    StateTransitionError,
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    """Request body for POST /projects."""

    name: str = Field(..., min_length=1, max_length=255)
    external_tender_id: str | None = None


class ProjectRename(BaseModel):
    """Request body for PATCH /projects/{id}  (rename)."""

    name: str = Field(..., min_length=1, max_length=255)


class ProjectResponse(BaseModel):
    """Serialized project representation returned by all routes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    external_tender_id: str | None
    status: ProjectStatus
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Error mapping helper
# ---------------------------------------------------------------------------


def _to_http(exc: Exception) -> HTTPException:
    """Translate a ProjectService domain error into an HTTPException."""
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    # ProjectArchivedError and StateTransitionError are both bad-request.
    return HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProjectResponse:
    """Create a new project in the DRAFT state."""
    svc = ProjectService(session)
    project = await svc.create(
        auth, name=body.name, external_tender_id=body.external_tender_id
    )
    response = ProjectResponse.model_validate(project)
    await session.commit()
    return response


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[ProjectResponse]:
    """List all projects visible to the authenticated organization."""
    svc = ProjectService(session)
    projects = await svc.list(auth)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProjectResponse:
    """Retrieve a single project by ID (tenant-scoped)."""
    svc = ProjectService(session)
    try:
        project = await svc.get_or_raise(auth, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: UUID,
    body: ProjectRename,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProjectResponse:
    """Rename a non-archived project."""
    svc = ProjectService(session)
    try:
        project = await svc.rename(auth, project_id, body.name)
    except _ProjectErrors as exc:
        raise _to_http(exc) from exc
    await session.refresh(project)
    response = ProjectResponse.model_validate(project)
    await session.commit()
    return response


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProjectResponse:
    """Move a project to the ARCHIVED state."""
    svc = ProjectService(session)
    try:
        project = await svc.archive(auth, project_id)
    except _ProjectErrors as exc:
        raise _to_http(exc) from exc
    await session.refresh(project)
    response = ProjectResponse.model_validate(project)
    await session.commit()
    return response


@router.post("/{project_id}/reopen", response_model=ProjectResponse)
async def reopen_project(
    project_id: UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> ProjectResponse:
    """Reset an archived project back to DRAFT."""
    svc = ProjectService(session)
    try:
        project = await svc.reopen(auth, project_id)
    except _ProjectErrors as exc:
        raise _to_http(exc) from exc
    await session.refresh(project)
    response = ProjectResponse.model_validate(project)
    await session.commit()
    return response


@router.delete("/{project_id}", status_code=204)
async def hard_delete_project(
    project_id: UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Permanently delete an archived project and all its data.

    The project must be in ``ARCHIVED`` state.  All documents, versions,
    pages, requirements, exports, and audit logs are removed via
    database CASCADE.  Stored object bytes in object storage are also
    deleted.  This action is irreversible and fully audited.

    Only the owning organization can perform this operation.
    """
    correlation_id = get_correlation_id()
    logger = get_logger("projects")

    # Verify the project belongs to this org before attempting deletion.
    project = await session.get(Project, project_id)
    if project is None or project.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.ARCHIVED:
        raise HTTPException(
            status_code=409,
            detail=f"Project must be archived before hard deletion "
            f"(current: {project.status})",
        )

    retention_svc = RetentionService(session)

    # Gather storage keys before cascade deletion.
    result = await session.execute(
        select(StoredObject.storage_key).where(
            StoredObject.project_id == project_id
        )
    )
    storage_keys = [row[0] for row in result]

    deleted_count = await retention_svc.hard_delete_project(
        organization_id=auth.organization_id,
        project_id=project_id,
        actor_id=auth.actor_id,
        correlation_id=correlation_id,
    )

    # Physically delete stored objects from object storage.
    storage_adapter: Any = getattr(request.app.state, "storage_adapter", None)
    if storage_adapter is not None:
        for key in storage_keys:
            try:
                await storage_adapter.delete(key)
            except Exception:  # noqa: BLE001
                # Log but don't fail the whole deletion — the DB rows
                # are gone; storage cleanup can be retried.
                log_event(
                    logger,
                    level=40,
                    message="storage_delete_failed",
                    correlation_id=correlation_id,
                    project_id=str(project_id),
                    storage_key_prefix=key[:8] if key else None,
                )

    await session.commit()

    log_event(
        logger,
        level=20,
        message="project_hard_deleted_api",
        correlation_id=correlation_id,
        project_id=str(project_id),
        organization_id=str(auth.organization_id),
        stored_objects=deleted_count,
    )
