"""Seed the reserved document-worker audit actor.

Revision ID: 0035_worker_audit_actor
Revises: 0034_obligation_coverage_audit
Create Date: 2026-10-09
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision: str = "0035_worker_audit_actor"
down_revision: str | None = "0035_coverage_error_category"
branch_labels: str | None = None
depends_on: str | None = None

_WORKER_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000100")
_WORKER_PROVIDER = "system"
_WORKER_PROVIDER_ID = "tender-compliance-document-worker"
_LEGACY_WORKER_PROVIDER_IDS = {"system-worker"}


def upgrade() -> None:
    """Ensure the fixed worker actor exists before any job writes an audit."""
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("auth_provider", sa.String(length=64)),
        sa.column("auth_provider_user_id", sa.String(length=255)),
        sa.column("full_name", sa.String(length=255)),
    )
    bind = op.get_bind()
    existing = bind.execute(
        sa.select(users.c.auth_provider, users.c.auth_provider_user_id).where(
            users.c.id == _WORKER_ACTOR_ID
        )
    ).one_or_none()
    if existing is not None:
        if existing.auth_provider == _WORKER_PROVIDER and (
            existing.auth_provider_user_id == _WORKER_PROVIDER_ID
        ):
            return
        if (
            existing.auth_provider == _WORKER_PROVIDER
            and existing.auth_provider_user_id in _LEGACY_WORKER_PROVIDER_IDS
        ):
            bind.execute(
                sa.update(users)
                .where(users.c.id == _WORKER_ACTOR_ID)
                .values(auth_provider_user_id=_WORKER_PROVIDER_ID)
            )
            return
        raise RuntimeError(
            "The reserved document-worker actor ID is already assigned to "
            "a different identity"
        )

    op.bulk_insert(
        users,
        [
            {
                "id": _WORKER_ACTOR_ID,
                "auth_provider": _WORKER_PROVIDER,
                "auth_provider_user_id": _WORKER_PROVIDER_ID,
                "full_name": "Tender Compliance document worker",
            }
        ],
    )


def downgrade() -> None:
    """Remove only the reserved worker identity created by this migration."""
    op.execute(
        sa.delete(sa.table("users")).where(
            sa.column("id", sa.Uuid()) == _WORKER_ACTOR_ID,
            sa.column("auth_provider", sa.String()) == _WORKER_PROVIDER,
            sa.column("auth_provider_user_id", sa.String()) == _WORKER_PROVIDER_ID,
        )
    )
