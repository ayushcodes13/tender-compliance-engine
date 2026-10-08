"""Persist bounded image-audit error categories."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0035_coverage_error_category"
down_revision = "0034_obligation_coverage_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extraction_window_audits",
        sa.Column("coverage_error_category", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extraction_window_audits", "coverage_error_category")
