"""Project lifecycle API routes (CP10).

Provides REST endpoints for creating, reading, updating, archiving, and
reopening projects.  All routes are tenant-scoped via AuthContext.

Business rules live in ProjectService (CP09); these routes are thin
transport adapters that manage the transaction boundary (commit/rollback)
and map domain errors to HTTP status codes.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import ProjectStatus
from tender_compliance_api.db.session import get_session
from tender_compliance_api.project import (
    ProjectArchivedError,
    ProjectNotFoundError,
    ProjectService,
    StateTransitionError,
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
