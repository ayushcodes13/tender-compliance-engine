"""Reusable audit service.

Every mutation in a later checkpoint writes an audit event through one of
the two entry points here so log structure stays consistent.  Events are
always organization-scoped and never contain confidential document bodies
(per SECURITY.md).

The service does **not** commit — the caller's transaction boundary
controls persistence.  ``flush()`` is used so the caller can still
roll back.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import AuditLog


class AuditService:
    """Write audit events into a single organization-scoped table.

    Construct with an active :class:`AsyncSession`.  Events are added but
    not committed; the caller decides when to persist.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        organization_id: uuid.UUID,
        action: str,
        *,
        actor_id: uuid.UUID | None = None,
        actor_type: str = "USER",
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditLog:
        """Create and persist (flush) a single audit-log entry.

        Args:
            organization_id: Tenant scope — drives every audit query.
            action: Short verb describing the event (e.g. ``"project.create"``).
            actor_id: The actor's user UUID, or ``None`` for system events.
            actor_type: ``"USER"`` or ``"SYSTEM"`` (default ``"USER"``).
            entity_type: The kind of entity affected (e.g. ``"project"``).
            entity_id: The UUID of the affected entity, if applicable.
            project_id: Optional project scope (added in CP09).
            metadata: Small, non-confidential structured context.
            correlation_id: Request/background-job correlation ID (CP46).
                If not provided, falls back to the current logging context.

        Returns:
            The freshly created :class:`AuditLog` row.
        """
        if correlation_id is None:
            from tender_compliance_api.logs import get_correlation_id

            correlation_id = get_correlation_id()
        entry = AuditLog(
            organization_id=organization_id,
            project_id=project_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata,
            correlation_id=correlation_id,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry


async def write_audit_event(
    session: AsyncSession,
    auth: AuthContext,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> AuditLog:
    """Convenience wrapper: log an event attributed to *auth*'s actor."""
    service = AuditService(session)
    return await service.log(
        organization_id=auth.organization_id,
        action=action,
        actor_id=auth.actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        metadata=metadata,
        correlation_id=correlation_id,
    )
