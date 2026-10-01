"""Add tender_documents and document_versions tables (CP14).

Tables:

* ``tender_documents`` — logical document container for a project.
  ``display_name`` is display metadata, not identity.
* ``document_versions`` — immutable, append-only uploaded versions.
  ``(document_id, version_number)`` is unique so later versions always
  create new rows.  ``stored_object_id`` has ``ON DELETE RESTRICT`` so
  a StoredObject backing a version cannot be removed while the version
  exists.

Revision ID: 0005_document_version
Revises: 0004_stored_object
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_document_version"
down_revision: str | None = "0004_stored_object"
branch_labels: str | None = None
depends_on: str | None = None

_DOC_PROCESSING_STATUS_ENUM = sa.Enum(
    "uploaded",
    "processing",
    "parsed",
    "failed",
    name="doc_processing_status",
)

_TENDER_DOCUMENT_TYPE_ENUM = sa.Enum(
    "tender",
    "amendment",
    "specification",
    "other",
    name="tender_document_type",
)


def upgrade() -> None:
    """Create tender_documents and document_versions tables."""
    _TENDER_DOCUMENT_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    _DOC_PROCESSING_STATUS_ENUM.create(op.get_bind(), checkfirst=True)

    # --- tender_documents ---
    op.create_table(
        "tender_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column(
            "document_type",
            _TENDER_DOCUMENT_TYPE_ENUM,
            server_default="tender",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tender_documents_project", "tender_documents",
        ["project_id"], unique=False,
    )

    # --- document_versions ---
    op.create_table(
        "document_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("stored_object_id", sa.UUID(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "processing_status",
            _DOC_PROCESSING_STATUS_ENUM,
            server_default="uploaded",
            nullable=False,
        ),
        sa.Column("parser_name", sa.String(length=128), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("ocr_name", sa.String(length=128), nullable=True),
        sa.Column("ocr_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["tender_documents.id"], ondelete="CASCADE",
        ),
        # RESTRICT so a StoredObject backing a version cannot be deleted
        # while the version still references it.
        sa.ForeignKeyConstraint(
            ["stored_object_id"], ["stored_objects.id"], ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_doc_versions_doc_ver"
        ),
    )
    op.create_index(
        "ix_doc_versions_document", "document_versions",
        ["document_id"], unique=False,
    )
    op.create_index(
        "ix_doc_versions_stored_object", "document_versions",
        ["stored_object_id"], unique=False,
    )


def downgrade() -> None:
    """Drop document_versions and tender_documents tables."""
    op.drop_index(
        "ix_doc_versions_stored_object", table_name="document_versions"
    )
    op.drop_index(
        "ix_doc_versions_document", table_name="document_versions"
    )
    op.drop_table("document_versions")

    op.drop_index(
        "ix_tender_documents_project", table_name="tender_documents"
    )
    op.drop_table("tender_documents")

    _DOC_PROCESSING_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    _TENDER_DOCUMENT_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
