"""Record whether each source window was processed during extraction."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033_extraction_window_audits"
down_revision = "0032_document_page_ocr_word_geometry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_window_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("window_index", sa.Integer(), nullable=False),
        sa.Column("call_status", sa.String(length=24), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("ocr_warning", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_spans", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("processing_run_id", "chunk_id", name="uq_extraction_window_run_chunk"),
    )
    op.create_index(
        "ix_extraction_window_version",
        "extraction_window_audits",
        ["document_version_id"],
    )
    op.create_index(
        "ix_extraction_window_run",
        "extraction_window_audits",
        ["processing_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_window_run", table_name="extraction_window_audits")
    op.drop_index("ix_extraction_window_version", table_name="extraction_window_audits")
    op.drop_table("extraction_window_audits")
