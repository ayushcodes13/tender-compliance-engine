"""CP50 — Evidence model, retrieval/indexing, and retrieval evaluation.

Adds three tables:

* ``oem_text_segments`` — searchable text chunks extracted from OEM
  documents during parsing (CP21/CP23).  Segments are tied to an immutable
  ``oem_document_version_id`` and carry ``start_char``/``end_char`` offsets
  so the exact source excerpt can be reconstructed.
* ``evidence`` — one row per proposed evidence candidate returned by the
  retrieval engine for a requirement.  Carries ``score``,
  ``retrieval_method``, ``retrieval_config`` (query/config/version/ranking
  signals), and a curation ``review_state`` (proposed/accepted/rejected).
* ``evidence_locations`` — source anchors for an evidence row, mirroring
  ``requirement_sources`` precision fields (page, clause, char offsets,
  bbox, ocr_confidence, source_text, location_type).  Multiple locations
  per evidence row are supported.

Phase 1 safety: ``review_state`` is a curation state, not a compliance
verdict.  Compliance assessment is Phase 2.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_evidence_model_retrieval"
down_revision: str | None = "0019_oem_document_ingestion"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- Evidence review state enum ---
    evidence_review_state = sa.Enum(
        "proposed", "accepted", "rejected",
        name="evidence_review_state",
    )
    evidence_review_state.create(op.get_bind(), checkfirst=True)

    # --- oem_text_segments ---
    op.create_table(
        "oem_text_segments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "oem_document_version_id",
            sa.UUID(),
            sa.ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "oem_document_version_id", "page_number", "segment_index",
            name="uq_oem_segments_lookup",
        ),
        sa.Index(
            "ix_oem_segments_page",
            "oem_document_version_id", "page_number",
        ),
    )

    # --- evidence ---
    op.create_table(
        "evidence",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "requirement_id",
            sa.UUID(),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "oem_document_version_id",
            sa.UUID(),
            sa.ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("score", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "retrieval_method",
            sa.String(64),
            nullable=False,
            server_default="keyword",
        ),
        sa.Column("retrieval_config", sa.JSON(), nullable=True),
        sa.Column(
            "review_state",
            sa.String(16),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Index("ix_evidence_review_state", "review_state"),
        sa.Index("ix_evidence_requirement_score", "requirement_id", "score"),
    )

    # --- evidence_locations ---
    op.create_table(
        "evidence_locations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "evidence_id",
            sa.UUID(),
            sa.ForeignKey("evidence.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "oem_text_segment_id",
            sa.UUID(),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "oem_document_version_id",
            sa.UUID(),
            sa.ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("clause_number", sa.String(64), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "location_type",
            sa.String(16),
            nullable=False,
            server_default="approximate",
        ),
        sa.Column("source_text", sa.String(8192), nullable=True),
        sa.Index(
            "ix_evidence_locations_segment",
            "oem_text_segment_id",
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_locations_segment", table_name="evidence_locations"
    )
    op.drop_table("evidence_locations")

    op.drop_index(
        "ix_evidence_requirement_score", table_name="evidence"
    )
    op.drop_index("ix_evidence_review_state", table_name="evidence")
    op.drop_table("evidence")

    op.drop_index("ix_oem_segments_page", table_name="oem_text_segments")
    op.drop_table("oem_text_segments")

    evidence_review_state = sa.Enum(name="evidence_review_state")
    evidence_review_state.drop(op.get_bind(), checkfirst=True)
