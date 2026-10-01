"""Project lifecycle service (CP09).

Business rules live here — not in routes.  Every method takes a verified
:class:`AuthContext` so tenant isolation is enforced in one place.

Lifecycle transitions (not vendor compliance — that is Phase 2):

    DRAFT
      → TENDER_UPLOADED   (upload step, future CP)
      → ARCHIVED           (archive_project)
    ARCHIVED
      → DRAFT              (reopen_project)

  create_project always starts a project in DRAFT.
  archive_project is allowed from any non-ARCHIVED state.
  reopen_project is allowed only from ARCHIVED (resets to DRAFT).

The intermediate processing statuses (``tender_uploaded`` … ``exported``)
are reserved for future document-handling checkpoints.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import Project, ProjectStatus


class ProjectNotFoundError(Exception):
    """Raised when a project does not exist or belongs to another org."""


class ProjectArchivedError(Exception):
    """Raised when an operation is attempted on an archived project.

    Archival is terminal until explicitly reopened.
    """


class StateTransitionError(Exception):
    """Raised when a lifecycle transition is not permitted."""


class ProjectService:
    """Create, read, and lifecycle-manage Projects.

    Construct with an active :class:`AsyncSession`.  Audit events are
    flushed within the same transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> Project | None:
        """Return *project_id* if it belongs to *auth*'s organization."""
        result = await self._session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self, auth: AuthContext) -> list[Project]:
        """List all projects visible to *auth*'s organization."""
        result = await self._session.execute(
            select(Project)
            .where(Project.organization_id == auth.organization_id)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_or_raise(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> Project:
        """Like :meth:`get` but raises :class:`ProjectNotFoundError`."""
        project = await self.get(auth, project_id)
        if project is None:
            raise ProjectNotFoundError(
                f"project {project_id} not found in org {auth.organization_id}"
            )
        return project

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        auth: AuthContext,
        name: str,
        *,
        external_tender_id: str | None = None,
    ) -> Project:
        """Create a new project in the ``DRAFT`` state."""
        project = Project(
            organization_id=auth.organization_id,
            name=name,
            external_tender_id=external_tender_id,
            status=ProjectStatus.DRAFT,
            created_by=auth.actor_id,
        )
        self._session.add(project)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="project.create",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            metadata={"name": name, "external_tender_id": external_tender_id},
        )
        return project

    async def rename(
        self, auth: AuthContext, project_id: uuid.UUID, new_name: str
    ) -> Project:
        """Rename a non-archived project."""
        project = await self.get_or_raise(auth, project_id)
        if project.status == ProjectStatus.ARCHIVED:
            raise ProjectArchivedError(
                f"project {project_id} is archived; reopen before renaming"
            )
        project.name = new_name
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="project.rename",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={"new_name": new_name},
        )
        return project

    async def archive(self, auth: AuthContext, project_id: uuid.UUID) -> Project:
        """Move a project to the ``ARCHIVED`` state.

        Allowed from any non-archived state.  Raising
        :class:`StateTransitionError` for an already-archived project keeps
        the contract explicit instead of silently succeeding.
        """
        project = await self.get_or_raise(auth, project_id)
        if project.status == ProjectStatus.ARCHIVED:
            raise StateTransitionError(
                f"project {project_id} is already archived"
            )
        project.status = ProjectStatus.ARCHIVED
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="project.archive",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
        )
        return project

    async def reopen(self, auth: AuthContext, project_id: uuid.UUID) -> Project:
        """Reset an archived project back to ``DRAFT``."""
        project = await self.get_or_raise(auth, project_id)
        if project.status != ProjectStatus.ARCHIVED:
            raise StateTransitionError(
                f"project {project_id} is in {project.status!r}; "
                "only archived projects can be reopened"
            )
        project.status = ProjectStatus.DRAFT
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="project.reopen",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
        )
        return project

    async def mark_uploaded(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> Project:
        """Transition a project from DRAFT to TENDER_UPLOADED.

        Only allowed from DRAFT.  Archived and already-uploaded projects
        raise an error.
        """
        project = await self.get_or_raise(auth, project_id)
        if project.status == ProjectStatus.ARCHIVED:
            raise ProjectArchivedError(
                f"project {project_id} is archived; reopen before uploading"
            )
        if project.status != ProjectStatus.DRAFT:
            raise StateTransitionError(
                f"project {project_id} is in {project.status!r}; "
                "expected DRAFT"
            )
        old_status = project.status
        project.status = ProjectStatus.TENDER_UPLOADED
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="project.mark_uploaded",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={"from": old_status.value, "to": project.status.value},
        )
        return project
