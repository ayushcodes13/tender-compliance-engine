"""Initial baseline.

This is the base migration (down_revision = None).  It intentionally
creates **no application tables**.  The schema source of truth is Alembic
migrations — no ``metadata.create_all()`` is ever called from application
code (per AGENTS.md and docs/BYND-REUSE-AUDIT.md).

The first application tables arrive in subsequent checkpoints (CP08+).
This baseline only establishes Alembic's version-tracking so that every
later schema change can be reproduced from an empty database.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-10-01

"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Upgrade schema.

    No operations: this baseline establishes only the Alembic version table.
    """
    pass


def downgrade() -> None:
    """Downgrade schema.

    No operations: the baseline has no schema to remove.
    """
    pass
