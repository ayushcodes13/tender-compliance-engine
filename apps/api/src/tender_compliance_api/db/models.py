"""ORM models for tenant identity and audit entities (CP08).

All models register onto the shared ``Base`` (db/base.py) so that Alembic
autogenerate keeps migrations in sync.  These are the first application
tables; the baseline migration (0001) created none.

Phase 1 scope — only the identity/audit foundation.  No vendor-compliance
or OEM-evidence tables (those are Phase 2).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import UUID as SaUUID
from sqlalchemy.orm import Mapped, mapped_column

from tender_compliance_api.db.base import Base


class Organization(Base):
    """Tenant boundary for projects and documents."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"Organization(id={self.id!r}, name={self.name!r})"


class User(Base):
    """Product-relevant identity metadata backed by an external provider.

    ``auth_provider`` identifies the issuer (e.g. ``"dev"``, ``"oidc"``).
    ``auth_provider_user_id`` is the stable identifier from that provider.
    Only fields needed for authorization are stored — never document bodies.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auth_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"User(id={self.id!r}, auth_provider={self.auth_provider!r})"


class Membership(Base):
    """Explicit link between a User and an Organization with a constrained role.

    Roles accepted by the service layer: ``owner``, ``admin``, ``member``,
    ``viewer``.  Uniqueness on (organization_id, user_id) prevents
    duplicate memberships.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_memberships_org_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Membership(org={self.organization_id!r}, "
            f"user={self.user_id!r}, role={self.role!r})"
        )


class AuditLog(Base):
    """Cross-cutting, organization-scoped audit event.

    Stores identifiers and action metadata — never confidential document
    bodies (per SECURITY.md).  ``project_id`` is intentionally omitted here
    (no Project table yet); it will be added in CP09 alongside the Project
    model.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True
    )
    # Minimal structured metadata as JSON.  Never store confidential bodies.
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"AuditLog(org={self.organization_id!r}, action={self.action!r})"
        )
