"""CP52 — Vendor specification extraction.

Adds the ``vendor_specs`` table for structured vendor facts extracted
deterministically from accepted OEM evidence.

Design:
* Every ``VendorSpec`` row MUST point to its supporting ``evidence`` row
  (non-nullable FK, CASCADE on delete).  Unsupported values cannot persist
  without evidence (checkpoint guardrail).
* Source linkage mirrors ``EvidenceLocation`` precision fields (page, char
  offsets, source_text, ocr_confidence, location_type) so every fact can
  be traced back to OEM source material.
* ``parameter`` captures the conceptual quantity (e.g. ``accuracy``,
  ``resolution`` — never collapsed with the unit or with each other).
* ``normalization_state`` reuses ``ConstraintNormalizationState`` so OCR-ambiguous
  specs are escalated to PARTIAL / NEEDS_REVIEW.
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_vendor_spec_extraction"
down_revision: str | None = "0020_evidence_model_retrieval"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_specs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evidence_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "requirement_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "oem_document_version_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "oem_text_segment_id",
            pg.UUID(as_uuid=True),
            nullable=True,
            index=True,
        ),
        sa.Column("parameter", sa.String(128), nullable=False),
        sa.Column("entity", sa.String(256), nullable=True),
        sa.Column("value", sa.Numeric(18, 6), nullable=True),
        sa.Column("lower_bound", sa.Numeric(18, 6), nullable=True),
        sa.Column("upper_bound", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit", sa.String(64), nullable=True),
        sa.Column("tolerance", sa.Numeric(18, 6), nullable=True),
        sa.Column("qualitative_statement", sa.String(1024), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=True),
        sa.Column("source_text", sa.String(2048), nullable=False),
        sa.Column("source_page_number", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "location_type",
            sa.String(16),
            nullable=False,
            server_default="approximate",
        ),
        sa.Column(
            "extraction_method",
            sa.String(32),
            nullable=False,
            server_default="deterministic",
        ),
        sa.Column("extraction_version", sa.String(64), nullable=False),
        sa.Column(
            "normalization_state",
            sa.String(32),
            nullable=False,
            server_default="unnormalized",
        ),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Index("ix_vendor_specs_evidence", "evidence_id"),
        sa.Index("ix_vendor_specs_requirement", "requirement_id"),
        sa.Index("ix_vendor_specs_parameter", "parameter"),
        sa.Index(
            "ix_vendor_specs_evidence_parameter",
            "evidence_id",
            "parameter",
        ),
    )


def downgrade() -> None:
    op.drop_table("vendor_specs")
