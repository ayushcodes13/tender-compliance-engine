"""Add Requirement + RequirementSource + review states (CP30).

Promotes reconciled, source-validated extraction candidates into persisted,
source-anchored :class:`~tender_compliance_api.db.models.Requirement` rows
with EXACT/APPROXIMATE source anchors (CP30).  Includes a stable
``promotion_key`` for reprocess idempotency (CP30.9) and the Phase 1 human-
review states only (no vendor-compliance statuses).

``review_state`` is stored as a plain ``VARCHAR`` (mirroring CP26's
``0009_extraction_runs`` status column) so the migration is SQLite-compatible
in CI while the ORM ``Enum(RequirementReviewState, name=...)`` maps the
Python enum to/from string values.  No native DB enum type is created.

Revision ID: 0012_requirements
Revises: 0011_extraction_reconciliation
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_requirements"
down_revision: str | None = "0011_extraction_reconciliation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create requirements + requirement_sources tables."""
    op.create_table(
        "requirements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("processing_run_id", sa.UUID(), nullable=True),
        sa.Column("promotion_key", sa.String(length=64), nullable=False),
        sa.Column(
            "reconciliation_group_id", sa.String(length=64), nullable=True
        ),
        sa.Column("requirement_type", sa.String(length=32), nullable=False),
        sa.Column(
            "normalized_text", sa.String(length=2048), nullable=False
        ),
        sa.Column("raw_source", sa.String(length=2048), nullable=False),
        sa.Column("uncertainty", sa.String(length=16), nullable=False),
        sa.Column("clause_number", sa.String(length=64), nullable=True),
        sa.Column(
            "ocr_warning", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        # Phase 1 review state (UNREVIEWED/REVIEWED/NEEDS_CLARIFICATION/
        # OCR_WARNING) — stored as VARCHAR for SQLite compatibility.
        sa.Column(
            "review_state",
            sa.String(length=32),
            nullable=False,
            server_default="unreviewed",
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
            "document_version_id",
            "promotion_key",
            name="uq_requirements_version_promotion_key",
        ),
    )
    op.create_index(
        "ix_requirements_version", "requirements", ["document_version_id"], unique=False
    )
    op.create_index(
        "ix_requirements_group", "requirements", ["reconciliation_group_id"], unique=False
    )
    op.create_index(
        "ix_requirements_promotion_key", "requirements", ["promotion_key"], unique=False
    )

    op.create_table(
        "requirement_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requirement_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("clause_number", sa.String(length=64), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "location_type",
            sa.String(length=16),
            nullable=False,
            server_default="approximate",
        ),
        sa.Column("source_text", sa.String(length=8192), nullable=True),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_requirement_sources_requirement",
        "requirement_sources",
        ["requirement_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_sources_version",
        "requirement_sources",
        ["document_version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop requirement_sources + requirements tables."""
    op.drop_index(
        "ix_requirement_sources_version", table_name="requirement_sources"
    )
    op.drop_index(
        "ix_requirement_sources_requirement", table_name="requirement_sources"
    )
    op.drop_table("requirement_sources")

    op.drop_index("ix_requirements_promotion_key", table_name="requirements")
    op.drop_index("ix_requirements_group", table_name="requirements")
    op.drop_index("ix_requirements_version", table_name="requirements")
    op.drop_table("requirements")
