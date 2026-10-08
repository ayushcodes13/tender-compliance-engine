"""Persist post-render tender sheet integrity validation results."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_export_integrity_validation"
down_revision = "0030_candidate_verbatim_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "export_artifacts",
        sa.Column(
            "validation_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_run",
        ),
    )
    op.add_column(
        "export_artifacts",
        sa.Column("validation_report", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("export_artifacts", "validation_report")
    op.drop_column("export_artifacts", "validation_status")
