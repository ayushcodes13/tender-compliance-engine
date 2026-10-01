"""Add processing_runs table and extend DocumentProcessingStatus (CP17).

State-machine extension:

* ``doc_processing_status`` enum gains ``queued`` and ``partial``.
* New ``processing_stage`` enum: parse / ocr / cleanup / extract.
* New ``run_status`` enum: started / running / completed / failed / retry.
* New ``processing_runs`` table: one row per processing attempt per
  document version, tracking stage, status, attempt count, and error info.

Revision ID: 0006_processing_run
Revises: 0005_document_version
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_processing_run"
down_revision: str | None = "0005_document_version"
branch_labels: str | None = None
depends_on: str | None = None

_PROCESSING_STAGE_ENUM = sa.Enum(
    "parse",
    "ocr",
    "cleanup",
    "extract",
    name="processing_stage",
)

_RUN_STATUS_ENUM = sa.Enum(
    "started",
    "running",
    "completed",
    "failed",
    "retry",
    name="run_status",
)


def upgrade() -> None:
    """Add new enum values and create the processing_runs table."""
    # --- Extend doc_processing_status enum (PostgreSQL only) ---
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # SQLite stores enums as VARCHAR — no schema change needed there.
        op.execute("ALTER TYPE doc_processing_status ADD VALUE 'queued'")
        op.execute("ALTER TYPE doc_processing_status ADD VALUE 'partial'")

    # --- Create new enums ---
    _PROCESSING_STAGE_ENUM.create(op.get_bind(), checkfirst=True)
    _RUN_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    # --- Create processing_runs table ---
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "stage",
            _PROCESSING_STAGE_ENUM,
            nullable=False,
        ),
        sa.Column(
            "status",
            _RUN_STATUS_ENUM,
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_runs_version",
        "processing_runs",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_processing_runs_stage",
        "processing_runs",
        ["document_version_id", "stage"],
        unique=False,
    )
    op.create_index(
        "ix_processing_runs_run_id",
        "processing_runs",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop processing_runs table and new enums."""
    op.drop_index("ix_processing_runs_run_id", table_name="processing_runs")
    op.drop_index("ix_processing_runs_stage", table_name="processing_runs")
    op.drop_index("ix_processing_runs_version", table_name="processing_runs")
    op.drop_table("processing_runs")

    _RUN_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    _PROCESSING_STAGE_ENUM.drop(op.get_bind(), checkfirst=True)

    # NOTE: PostgreSQL ALTER TYPE cannot drop enum values. The extended
    # 'queued' / 'partial' labels on doc_processing_status are intentionally
    # left in place on downgrade; they are harmless leftover enum members that
    # the application code no longer writes.
