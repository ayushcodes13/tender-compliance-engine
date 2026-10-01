"""CP46 — Add audit_logs.correlation_id and document_versions.retention_deadline.

Adds a correlation_id column to audit_logs so every event can be traced
to its request or background job.  Adds a retention_deadline column to
document_versions so the retention cleanup job knows when an object is
eligible for deletion.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_observability_retention"
down_revision: str = "0017_export_artifacts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"]
    )

    op.add_column(
        "document_versions",
        sa.Column(
            "retention_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp after which this version's originals "
            "are eligible for hard deletion per the retention policy "
            "(CP46)",
        ),
    )
    op.create_index(
        "ix_document_versions_retention",
        "document_versions",
        ["retention_deadline"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_versions_retention", table_name="document_versions")
    op.drop_column("document_versions", "retention_deadline")
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs")
    op.drop_column("audit_logs", "correlation_id")
