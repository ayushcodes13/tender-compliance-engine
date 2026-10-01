"""Add ExtractionDiagnostics audit table (CP31).

One row per EXTRACT processing run capturing aggregate counts
(accepted/rejected/deduped/promoted/ocr-warning), the provider/model/prompt/schema
versions, a rejection-breakdown, and the last reconciliation summary — so an
operator can debug "why did this document produce its requirement set" without
re-running the stage. No document bodies (rejection keys are short reason codes).

Revision ID: 0013_extraction_diagnostics
Revises: 0012_requirements
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_extraction_diagnostics"
down_revision: str | None = "0012_requirements"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_diagnostics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_version_id", sa.UUID(), nullable=False
        ),
        sa.Column(
            "processing_run_id", sa.UUID(), nullable=True
        ),
        sa.Column(
            "total_windows",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_llm_calls",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_candidates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "accepted_candidates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "rejected_candidates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "deduped_candidates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "promoted_requirements",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ocr_warning_candidates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=True),
        sa.Column(
            "rejection_breakdown", sa.JSON(), nullable=False
        ),
        sa.Column(
            "reconciliation_summary", sa.JSON(), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id"],
            ["processing_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "processing_run_id", name="uq_extraction_diagnostics_run"
        ),
    )
    op.create_index(
        "ix_extraction_diagnostics_version",
        "extraction_diagnostics",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_diagnostics_created",
        "extraction_diagnostics",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extraction_diagnostics_created", table_name="extraction_diagnostics"
    )
    op.drop_index(
        "ix_extraction_diagnostics_version", table_name="extraction_diagnostics"
    )
    op.drop_table("extraction_diagnostics")
