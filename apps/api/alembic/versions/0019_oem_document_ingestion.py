"""CP49 — OEM document ingestion and provenance.

Adds oem_documents and oem_document_versions tables mirroring the
tender document structure.  Tender and OEM sources remain in separate
tables so they are always distinguishable in queries.

OEM documents carry vendor/product metadata (vendor_name, product_name,
product_sku, document_metadata) for downstream evidence filtering (CP50+).
All OEM document versions are immutable: source StoredObject, checksum,
MIME, and size are written once and never updated.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_oem_document_ingestion"
down_revision: str = "0018_observability_retention"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- OEM document type enum ---
    oem_doc_type = sa.Enum(
        "datasheet",
        "brochure",
        "manual",
        "certificate",
        "test_report",
        "quotation",
        "proposal",
        "other",
        name="oem_document_type",
    )
    # Reuse the existing doc_processing_status enum
    # (document versions table already created it in 0005).

    # --- oem_documents table ---
    oem_doc_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "oem_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "project_id", sa.UUID(), nullable=False
        ),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column(
            "document_type",
            oem_doc_type,
            nullable=False,
            server_default="datasheet",
        ),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("product_sku", sa.String(length=255), nullable=True),
        sa.Column("document_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oem_documents_project", "oem_documents", ["project_id"]
    )
    op.create_index(
        "ix_oem_documents_vendor", "oem_documents", ["vendor_name"]
    )

    # --- oem_document_versions table ---
    # Reuse the doc_processing_status enum (created in 0005 for
    # document_versions; SQLite shares enum-like types as strings).
    oem_processing_status = sa.Enum(
        "uploaded", "queued", "processing", "parsed", "partial", "failed",
        name="oem_doc_processing_status",
    )
    oem_processing_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "oem_document_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_id", sa.UUID(), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "stored_object_id", sa.UUID(), nullable=False
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "processing_status",
            oem_processing_status,
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("parser_name", sa.String(length=128), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("ocr_name", sa.String(length=128), nullable=True),
        sa.Column("ocr_version", sa.String(length=64), nullable=True),
        sa.Column(
            "retention_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["oem_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stored_object_id"], ["stored_objects.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "version_number",
            name="uq_oem_versions_doc_ver",
        ),
    )
    op.create_index(
        "ix_oem_versions_document", "oem_document_versions", ["document_id"]
    )
    op.create_index(
        "ix_oem_versions_stored_object",
        "oem_document_versions",
        ["stored_object_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oem_versions_stored_object", table_name="oem_document_versions"
    )
    op.drop_index(
        "ix_oem_versions_document", table_name="oem_document_versions"
    )
    op.drop_table("oem_document_versions")

    op.drop_index("ix_oem_documents_vendor", table_name="oem_documents")
    op.drop_index("ix_oem_documents_project", table_name="oem_documents")
    op.drop_table("oem_documents")

    oem_processing_status = sa.Enum(
        "uploaded", "queued", "processing", "parsed", "partial", "failed",
        name="oem_doc_processing_status",
    )
    oem_processing_status.drop(op.get_bind(), checkfirst=True)

    oem_doc_type = sa.Enum(
        "datasheet",
        "brochure",
        "manual",
        "certificate",
        "test_report",
        "quotation",
        "proposal",
        "other",
        name="oem_document_type",
    )
    oem_doc_type.drop(op.get_bind(), checkfirst=True)
