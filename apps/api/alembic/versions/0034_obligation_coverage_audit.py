"""Persist independent obligation coverage audit outcomes."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034_obligation_coverage_audit"
down_revision = "0033_extraction_window_audits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extraction_window_audits",
        sa.Column(
            "coverage_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_run",
        ),
    )
    op.add_column(
        "extraction_window_audits",
        sa.Column(
            "potential_omissions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("extraction_window_audits", "potential_omissions")
    op.drop_column("extraction_window_audits", "coverage_status")
