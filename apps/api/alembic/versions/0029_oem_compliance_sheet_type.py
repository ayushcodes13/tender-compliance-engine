"""Add vendor compliance sheet as a first-class OEM document type.

A compliance sheet supplied by a vendor is still evidence to verify; this
classification only makes the source type explicit in the product.
"""

from __future__ import annotations

from alembic import op

revision = "0029_oem_compliance_sheet_type"
down_revision = "0028_submission_approval_locking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE oem_document_type "
            "ADD VALUE IF NOT EXISTS 'compliance_sheet'"
        )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding the
    # enum and every dependent column. Keeping the value is backward-compatible.
    pass
