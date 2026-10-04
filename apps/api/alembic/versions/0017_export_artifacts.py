"""CP42 — Add ExportArtifact and ExportStatus tables.

Records XLSX export attempts for a document version, with metadata
(actor, requirement count, status, checksum, generated timestamp) and
a foreign key to the stored object holding the workbook bytes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_export_artifacts"
down_revision: str = "0016_requirement_structure"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Use native_enum=False for SQLite CI compatibility (matches 0006, 0016).
    export_status_enum = sa.Enum(
        "completed", "failed", name="export_status", native_enum=False
    )

    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_version_id", sa.UUID(), nullable=False
        ),
        sa.Column(
            "stored_object_id", sa.UUID(), nullable=True
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            export_status_enum,
            nullable=False,
            server_default="completed",
        ),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column(
            "requirement_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("workbook_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stored_object_id"],
            ["stored_objects.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_export_artifacts_version",
        "export_artifacts",
        ["document_version_id"],
    )
    op.create_index(
        "ix_export_artifacts_status",
        "export_artifacts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_artifacts_status", table_name="export_artifacts")
    op.drop_index(
        "ix_export_artifacts_version", table_name="export_artifacts"
    )
    op.drop_table("export_artifacts")
    export_status_enum = sa.Enum(name="export_status", native_enum=False)
    export_status_enum.drop(op.get_bind(), checkfirst=True)
