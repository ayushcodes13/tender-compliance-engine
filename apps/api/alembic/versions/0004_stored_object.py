"""Add stored_objects table for object-storage metadata (CP12).

This table records *metadata only* — the raw file bytes live in the
object store (S3/MinIO).  Each row carries a SHA-256 checksum computed
by the application, not a value trusted from the provider.

Key format: ``{org_id}/{project_id}[/{document_id}[/{version}]]/{uuid}{ext}``

Revision ID: 0004_stored_object
Revises: 0003_project_model
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_stored_object"
down_revision: str | None = "0003_project_model"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create stored_objects table."""
    op.create_table(
        "stored_objects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("content_length", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("etag", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key", name="uq_stored_objects_storage_key"
        ),
    )
    op.create_index(
        "ix_stored_objects_org", "stored_objects", ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_stored_objects_project", "stored_objects", ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stored_objects_storage_key"), "stored_objects",
        ["storage_key"], unique=False,
    )
    op.create_index(
        "ix_stored_objects_document_id", "stored_objects", ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop stored_objects table."""
    op.drop_index(
        op.f("ix_stored_objects_storage_key"), table_name="stored_objects"
    )
    op.drop_index(
        "ix_stored_objects_document_id", table_name="stored_objects"
    )
    op.drop_index(
        "ix_stored_objects_project", table_name="stored_objects"
    )
    op.drop_index(
        "ix_stored_objects_org", table_name="stored_objects"
    )
    op.drop_table("stored_objects")
