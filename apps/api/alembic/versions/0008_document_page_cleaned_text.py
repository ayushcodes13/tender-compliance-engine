"""Add cleaned_text to document_pages (CP23).

Adds a ``cleaned_text`` column to :table:`document_pages`.  This holds the
derived page text with deterministic header/footer noise removed by the
CP23 cleanup pass.  It is nullable and is a *derived* view over
``extracted_text`` (the raw, authoritative source) — cleanup never
destroys provenance.

Revision ID: 0008_document_page_cleaned_text
Revises: 0007_document_page
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_document_page_cleaned_text"
down_revision: str | None = "0007_document_page"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Add nullable cleaned_text column to document_pages."""
    op.add_column(
        "document_pages",
        sa.Column("cleaned_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the cleaned_text column from document_pages."""
    op.drop_column("document_pages", "cleaned_text")
