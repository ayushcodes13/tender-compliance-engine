"""Record strict source-quote fallback outcomes on extraction candidates."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030_candidate_verbatim_validation"
down_revision = "0029_oem_compliance_sheet_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extraction_candidates",
        sa.Column("verbatim_validation", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extraction_candidates", "verbatim_validation")
