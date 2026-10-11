"""Allow complete technical requirements and source text of any length.

Revision ID: 0038_unbounded_technical_text
Revises: 0037_coverage_finding_reviews
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0038_unbounded_technical_text"
down_revision: str | None = "0037_coverage_finding_reviews"
branch_labels: str | None = None
depends_on: str | None = None


_COLUMNS = {
    "extraction_candidates": ("normalized_text", "raw_source"),
    "requirements": ("normalized_text", "raw_source"),
    "requirement_revisions": ("previous_normalized_text",),
    "requirement_constraints": ("raw_fragment",),
}


def upgrade() -> None:
    """Keep full extracted wording instead of rejecting text over 2,048 chars."""
    for table_name, columns in _COLUMNS.items():
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in columns:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.String(length=2048),
                    type_=sa.Text(),
                    existing_nullable=False,
                )


def downgrade() -> None:
    """Restore the legacy bound; downgrade can fail if longer text is stored."""
    for table_name, columns in reversed(tuple(_COLUMNS.items())):
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in columns:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.Text(),
                    type_=sa.String(length=2048),
                    existing_nullable=False,
                )
