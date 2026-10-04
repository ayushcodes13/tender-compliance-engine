"""Add reconciliation columns to extraction_candidates + audit table (CP29).

Records per-candidate reconciliation decisions (CP29: deterministic dedup of
extracted candidates) without aggressive semantic merging, plus a single
audit row per reconciliation pass capturing aggregate counts.

Columns mirror :class:`tender_compliance_api.db.models.ExtractionCandidate`
(``reconciliation_group_id`` / ``deduped`` / ``reconciliation_decision``) and
the new
:class:`tender_compliance_api.db.models.ExtractionReconciliation` audit table.

Phase 1 only: no vendor-compliance or evidence columns.

Revision ID: 0011_extraction_reconciliation
Revises: 0010_extraction_candidates
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_extraction_reconciliation"
down_revision: str | None = "0010_extraction_candidates"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add reconciliation columns and audit table."""
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "reconciliation_group_id",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_extraction_candidates_reconciliation_group",
        "extraction_candidates",
        ["reconciliation_group_id"],
        unique=False,
    )
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "deduped", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "extraction_candidates",
        sa.Column("reconciliation_decision", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "extraction_reconciliations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_version_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column("processing_run_id", sa.UUID(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
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
    )
    op.create_index(
        "ix_extraction_reconciliations_version",
        "extraction_reconciliations",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_reconciliations_run",
        "extraction_reconciliations",
        ["processing_run_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop reconciliation columns and audit table."""
    op.drop_index(
        "ix_extraction_reconciliations_run",
        table_name="extraction_reconciliations",
    )
    op.drop_index(
        "ix_extraction_reconciliations_version",
        table_name="extraction_reconciliations",
    )
    op.drop_table("extraction_reconciliations")

    op.drop_index(
        "ix_extraction_candidates_reconciliation_group",
        table_name="extraction_candidates",
    )
    op.drop_column("extraction_candidates", "reconciliation_decision")
    op.drop_column("extraction_candidates", "deduped")
    op.drop_column("extraction_candidates", "reconciliation_group_id")
