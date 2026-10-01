"""Add extraction_runs table for LLM call audit (CP26).

One row per LLM extraction call, anchored to the ProcessingRun of the
EXTRACT stage that made it. Records provider/model/prompt+schema version,
latency, provider-reported token usage, best-effort cost, and finish reason.

Token counts and cost are nullable: ``NULL`` means "unknown", never a
fabricated zero (per the LLM logging SOP). This table contains no document
bodies and no vendor/OEM-compliance verdicts — it is Phase 1 audit only.

Revision ID: 0009_extraction_runs
Revises: 0008_document_page_cleaned_text
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_extraction_runs"
down_revision: str | None = "0008_document_page_cleaned_text"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create extraction_runs table."""
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("processing_run_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("call_site", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("finish_reason", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id"],
            ["processing_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_extraction_runs_run", "extraction_runs",
        ["processing_run_id", "created_at"], unique=False,
    )


def downgrade() -> None:
    """Drop extraction_runs table."""
    op.drop_index(
        "ix_extraction_runs_run", table_name="extraction_runs"
    )
    op.drop_table("extraction_runs")
