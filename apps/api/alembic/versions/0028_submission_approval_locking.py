"""CP61 — Approval, locking, submission versions.

Adds the ``submissions`` table for immutable submission snapshots (CP61).
Each submission captures a point-in-time final-matrix state for a document
version with approval/lock lifecycle.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_submission_approval_locking"
down_revision = "0027_final_export_outputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.UUID(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "approver_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assessment_snapshot", sa.JSON(), nullable=False),
        sa.Column("matrix_sha256", sa.String(64), nullable=False),
        sa.Column(
            "matrix_export_id",
            sa.UUID(),
            sa.ForeignKey("export_artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "version_number",
            name="uq_submissions_project_version",
        ),
    )
    op.create_index(
        "ix_submissions_project", "submissions", ["project_id"]
    )
    op.create_index(
        "ix_submissions_status", "submissions", ["status"]
    )
    op.create_index(
        "ix_submissions_matrix_export_id", "submissions", ["matrix_export_id"]
    )
    op.create_index(
        "ix_submissions_document_version_id",
        "submissions", ["document_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_document_version_id", table_name="submissions")
    op.drop_index("ix_submissions_matrix_export_id", table_name="submissions")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_project", table_name="submissions")
    op.drop_table("submissions")
