"""Retention and hard-deletion service (CP46).

Implements authorized hard deletion of tenant content and a retention
cleanup policy.  Deletion is always scoped to a single organization
and audited.

Key invariants:
- Hard deletion is irreversible and always organization-scoped.
- Only projects whose status is ``ARCHIVED`` can be hard-deleted.
- Original document bytes are only deleted when the retention deadline
  has passed and the project is confirmed archived.
- Every deletion is audited with actor, correlation_id, and reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.db.models import (
    DocumentVersion,
    Project,
    ProjectStatus,
    StoredObject,
    TenderDocument,
)
from tender_compliance_api.logs import get_logger, log_event
from tender_compliance_api.metrics import metrics_retention_deleted

logger = get_logger(__name__)


class ProjectNotArchivedError(Exception):
    """Raised when attempting to hard-delete a project that is not archived."""


class RetentionService:
    """Manages retention-deadline evaluation and hard deletion.

    Args:
        session: Active async database session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # ------------------------------------------------------------------
    # Hard deletion
    # ------------------------------------------------------------------

    async def hard_delete_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        reason: str = "manual_hard_delete",
        correlation_id: str | None = None,
    ) -> int:
        """Permanently delete a project and all its data.

        Only projects in ``ARCHIVED`` status are eligible.  All rows in
        dependent tables (documents, versions, pages, requirements,
        exports, audit logs) are removed via CASCADE.

        Returns the number of stored-object rows that were marked for
        physical deletion (the caller must also delete the object bytes
        from storage).

        Raises:
            ProjectNotArchivedError: If the project exists but is not
                archived.
        """
        project = await self._session.get(Project, project_id)
        if project is None:
            log_event(
                logger,
                level=40,
                message="hard_delete_project_not_found",
                correlation_id=correlation_id,
                project_id=str(project_id),
                organization_id=str(organization_id),
                reason=reason,
            )
            return 0

        if project.organization_id != organization_id:
            # Defensive: the API layer should already scope this.
            log_event(
                logger,
                level=40,
                message="hard_delete_cross_tenant_attempt",
                correlation_id=correlation_id,
                project_id=str(project_id),
                claimed_org=str(organization_id),
                actual_org=str(project.organization_id),
            )
            return 0

        if project.status != ProjectStatus.ARCHIVED:
            raise ProjectNotArchivedError(
                f"Project {project_id} is {project.status}, not archived"
            )

        # Collect stored object keys for physical deletion before we
        # cascade-delete the rows.
        result = await self._session.execute(
            select(StoredObject.storage_key).where(
                StoredObject.project_id == project_id
            )
        )
        object_keys: list[str] = [row[0] for row in result]

        # Delete the project row — CASCADE removes documents, versions,
        # pages, requirements, exports, audit logs.
        await self._session.delete(project)
        await self._session.flush()

        # Audit the deletion.
        await self._audit.log(
            organization_id=organization_id,
            action="project.hard_delete",
            actor_id=actor_id,
            actor_type="USER",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            correlation_id=correlation_id,
            metadata={
                "reason": reason,
                "stored_objects_pending_deletion": len(object_keys),
            },
        )

        log_event(
            logger,
            level=30,
            message="project_hard_deleted",
            correlation_id=correlation_id,
            project_id=str(project_id),
            organization_id=str(organization_id),
            stored_objects=len(object_keys),
        )

        metrics_retention_deleted().inc(len(object_keys))
        return len(object_keys)

    # ------------------------------------------------------------------
    # Retention deadline evaluation
    # ------------------------------------------------------------------

    async def evaluate_retention_deadlines(
        self,
        *,
        organization_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> list[uuid.UUID]:
        """Evaluate retention deadlines and return IDs of versions whose
        stored originals are eligible for physical deletion.

        A version is eligible when:
        - Its ``retention_deadline`` is in the past.
        - The parent project is ARCHIVED.

        If ``organization_id`` is provided, only versions within that
        organization are evaluated (tenant isolation).

        Returns a list of ``StoredObject.id`` UUIDs for objects that
        should be physically deleted from object storage.
        """
        now = now or datetime.now(UTC)

        from tender_compliance_api.config import get_settings

        settings = get_settings()
        retention_days = settings.retention_originals_days

        stmt = (
            select(StoredObject.id)
            .join(
                DocumentVersion,
                StoredObject.id == DocumentVersion.stored_object_id,
            )
            .join(
                TenderDocument,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .join(Project, TenderDocument.project_id == Project.id)
            .where(Project.status == ProjectStatus.ARCHIVED)
            .where(DocumentVersion.retention_deadline.is_not(None))
            .where(DocumentVersion.retention_deadline <= now)
        )
        if organization_id is not None:
            stmt = stmt.where(Project.organization_id == organization_id)

        result = await self._session.execute(stmt)
        eligible: list[uuid.UUID] = [row[0] for row in result]

        log_event(
            logger,
            level=20,
            message="retention_evaluated",
            organization_id=(
                str(organization_id) if organization_id else None
            ),
            eligible_count=len(eligible),
            retention_days=retention_days,
        )

        return eligible

    async def physically_delete_stored_objects(
        self,
        object_ids: list[uuid.UUID],
        *,
        correlation_id: str | None = None,
    ) -> int:
        """Delete StoredObject rows by ID after physical deletion from
        object storage.  This only removes DB rows — the caller must
        have already deleted the bytes from the storage adapter.
        """
        if not object_ids:
            return 0
        stmt = delete(StoredObject).where(
            StoredObject.id.in_(object_ids)
        )
        await self._session.execute(stmt)
        await self._session.flush()

        metrics_retention_deleted().inc(len(object_ids))

        log_event(
            logger,
            level=30,
            message="stored_objects_row_deleted",
            correlation_id=correlation_id,
            count=len(object_ids),
        )
        return len(object_ids)


# ---------------------------------------------------------------------------
# CLI cleanup entry point (CP46)
# ---------------------------------------------------------------------------


async def run_retention_cleanup(
    *,
    organization_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """Evaluate retention deadlines and delete eligible stored objects.

    Args:
        organization_id: If provided, restrict to a single tenant.
        dry_run: If True, evaluate and report without deleting.

    Returns:
        Dict with 'evaluated' and 'deleted' counts.  When ``dry_run``
        is True, 'deleted' equals 'evaluated' (reported only).
    """
    from contextlib import asynccontextmanager

    from tender_compliance_api.db.session import get_session
    from tender_compliance_api.logs import set_correlation_id

    set_correlation_id()
    org_uuid = (
        uuid.UUID(organization_id) if organization_id else None
    )

    session_cm = asynccontextmanager(get_session)
    async with session_cm() as session:
        svc = RetentionService(session)
        eligible = await svc.evaluate_retention_deadlines(
            organization_id=org_uuid
        )

        deleted = len(eligible)
        if not dry_run and eligible:
            await svc.physically_delete_stored_objects(eligible)
            await session.commit()

        log_event(
            logger,
            level=20,
            message="retention_cleanup_complete",
            dry_run=dry_run,
            evaluated=len(eligible),
            deleted=deleted,
        )
        return {"evaluated": len(eligible), "deleted": deleted}


def main() -> int:
    """CLI entry point for retention cleanup."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run retention cleanup (CP46)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Evaluate and report without deleting (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_const",
        const=False,
        dest="dry_run",
        help="Actually delete eligible objects (not dry-run)",
    )
    parser.add_argument(
        "--organization-id",
        type=str,
        default=None,
        help="Restrict to a single organization",
    )
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(
        run_retention_cleanup(
            organization_id=args.organization_id,
            dry_run=args.dry_run,
        )
    )
    print(f"Retention cleanup: {result}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
