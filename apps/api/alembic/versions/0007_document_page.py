"""Add document_pages table for page-level parse results (CP19).

Tables:

* ``document_pages`` — one row per page extracted from a
  ``DocumentVersion`` during the PARSE stage.  ``extracted_text``
  holds the native PDF text layer; when the parser determines the
  text is untrustworthy (e.g. a scanned raster page),
  ``extracted_text`` is NULL and ``ocr_needed`` is set so the OCR
  stage (CP21) can fill in the gap.  Structural metadata is stored
  as nullable JSONB.

Revision ID: 0007_document_page
Revises: 0006_processing_run
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_document_page"
down_revision: str | None = "0006_processing_run"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create document_pages table."""
    op.create_table(
        "document_pages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("ocr_needed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("rendered_image_object_key", sa.String(length=512), nullable=True),
        sa.Column("structural_metadata", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id", "page_number",
            name="uq_pages_version_page",
        ),
    )
    op.create_index(
        "ix_document_pages_version", "document_pages",
        ["document_version_id"], unique=False,
    )


def downgrade() -> None:
    """Drop document_pages table."""
    op.drop_index(
        "ix_document_pages_version", table_name="document_pages"
    )
    op.drop_table("document_pages")
