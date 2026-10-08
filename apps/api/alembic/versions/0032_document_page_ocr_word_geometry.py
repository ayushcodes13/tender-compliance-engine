"""Persist OCR word geometry for page citation highlights."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_document_page_ocr_word_geometry"
down_revision = "0031_export_integrity_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_pages",
        sa.Column("ocr_words", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_pages", "ocr_words")
