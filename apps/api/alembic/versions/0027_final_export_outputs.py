"""CP60 — Final XLSX, DOCX, and PDF outputs.

Adds ``export_format`` column to ``export_artifacts`` so that the export
metadata table can distinguish between final-compliance-matrix formats
(XLSX, DOCX, PDF) alongside the existing Phase 1 XLSX export.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_final_export_outputs"
down_revision = "0026_human_review_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite (test DB) doesn't support ALTER TABLE with constraints in
    # a single op.  Use batch mode (copy-and-move) which works on all
    # backends including SQLite.
    with op.batch_alter_table("export_artifacts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "export_format",
                sa.String(16),
                nullable=False,
                server_default="xlsx",
            ),
        )
        batch_op.create_check_constraint(
            "ck_export_artifacts_format",
            "export_format IN ('xlsx', 'docx', 'pdf')",
        )


def downgrade() -> None:
    with op.batch_alter_table("export_artifacts") as batch_op:
        batch_op.drop_constraint(
            "ck_export_artifacts_format",
            type_="check",
        )
        batch_op.drop_column("export_format")
