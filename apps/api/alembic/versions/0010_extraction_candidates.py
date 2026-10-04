"""Add extraction_candidates table for validated extraction output (CP28).

One row per model-proposed requirement candidate that the EXTRACT stage
produced for a version's windows.  Candidates that failed source validation
(``is_valid=False``) are kept for audit so the invented-requirement rate is
measurable, but they are never promoted to a persisted requirement by CP30
(CP30 requires ``persistable=True``).

Fields mirror :class:`tender_compliance_api.db.models.ExtractionCandidate`.
``sources_json`` stores the window's contributing source fragments (JSON dump
of :class:`TrustedSourceContext`) so a multi-page candidate is never detached
from its locations.  Token counts / cost live on the sibling ``extraction_runs``
audit table (CP26), not here.

Revision ID: 0010_extraction_candidates
Revises: 0009_extraction_runs
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_extraction_candidates"
down_revision: str | None = "0009_extraction_runs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create extraction_candidates table."""
    op.create_table(
        "extraction_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_version_id", sa.UUID(), nullable=False
        ),
        sa.Column(
            "processing_run_id", sa.UUID(), nullable=True
        ),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("window_text", sa.String(length=8192), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.Column("normalized_text", sa.String(length=2048), nullable=False),
        sa.Column("raw_source", sa.String(length=2048), nullable=False),
        sa.Column("requirement_type", sa.String(length=32), nullable=False),
        sa.Column("uncertainty", sa.String(length=16), nullable=False),
        sa.Column("clause_number", sa.String(length=64), nullable=True),
        sa.Column("group_hint", sa.String(length=64), nullable=True),
        sa.Column(
            "ocr_warning", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_valid", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "persistable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("rejection_reason", sa.String(length=1024), nullable=True),
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
        "ix_extraction_candidates_version",
        "extraction_candidates",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_candidates_run",
        "extraction_candidates",
        ["processing_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_extraction_candidates_chunk",
        "extraction_candidates",
        ["chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop extraction_candidates table."""
    op.drop_index("ix_extraction_candidates_chunk", table_name="extraction_candidates")
    op.drop_index(
        "ix_extraction_candidates_run", table_name="extraction_candidates"
    )
    op.drop_index(
        "ix_extraction_candidates_version", table_name="extraction_candidates"
    )
    op.drop_table("extraction_candidates")
