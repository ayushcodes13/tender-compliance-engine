"""ORM models for tenant identity, project, and audit entities (CP08–CP09).

All models register onto the shared ``Base`` (db/base.py) so that Alembic
autogenerate keeps migrations in sync.

Phase 1 scope — identity, project, audit.  No vendor-compliance or
OEM-evidence tables (those are Phase 2).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy import UUID as SaUUID
from sqlalchemy import Enum as _SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tender_compliance_api.db.base import Base


def _enum_values_callable(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum values, not Python member names.

    PostgreSQL native ENUM migrations use lowercase StrEnum values such as
    "draft". SQLAlchemy otherwise serializes member names such as "DRAFT".
    """
    return [str(member.value) for member in enum_cls]


class Enum(_SAEnum):
    """SQLAlchemy Enum configured to persist Enum.value consistently."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("values_callable", _enum_values_callable)
        super().__init__(*args, **kwargs)


class ProjectStatus(enum.StrEnum):
    """Workflow statuses for a project lifecycle (CP09).

    These describe **processing / review progress only** — never vendor/OEM
    compliance.  Compliance assessment is a Phase 2 concern.
    """

    DRAFT = "draft"
    TENDER_UPLOADED = "tender_uploaded"
    DOCUMENTS_PROCESSING = "documents_processing"
    REQUIREMENTS_EXTRACTED = "requirements_extracted"
    REVIEW_IN_PROGRESS = "review_in_progress"
    MATRIX_READY = "matrix_ready"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class Organization(Base):
    """Tenant boundary for projects and documents."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"Organization(id={self.id!r}, name={self.name!r})"


class User(Base):
    """Product-relevant identity metadata backed by an external provider.

    ``auth_provider`` identifies the issuer (e.g. ``"dev"``, ``"oidc"``).
    ``auth_provider_user_id`` is the stable identifier from that provider.
    Only fields needed for authorization are stored — never document bodies.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    auth_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"User(id={self.id!r}, auth_provider={self.auth_provider!r})"


class Membership(Base):
    """Explicit link between a User and an Organization with a constrained role.

    Roles accepted by the service layer: ``owner``, ``admin``, ``member``,
    ``viewer``.  Uniqueness on (organization_id, user_id) prevents
    duplicate memberships.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_memberships_org_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Membership(org={self.organization_id!r}, "
            f"user={self.user_id!r}, role={self.role!r})"
        )


class AuditLog(Base):
    """Cross-cutting, organization-scoped audit event.

    Stores identifiers and action metadata — never confidential document
    bodies (per SECURITY.md).  ``project_id`` is nullable so org-level
    events (e.g. membership changes) can still be recorded.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True
    )
    # Minimal structured metadata as JSON.  Never store confidential bodies.
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Correlation ID linking this event to a request or background job (CP46).
    correlation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"AuditLog(org={self.organization_id!r}, action={self.action!r})"
        )


class Project(Base):
    """A tender-response workspace owned by a single organization.

    ``status`` tracks the processing / review workflow, **not** vendor
    compliance.  Phase 2 compliance assessment does not exist yet.
    """

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_tender_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        nullable=False,
        default=ProjectStatus.DRAFT,
        server_default=ProjectStatus.DRAFT.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Project(id={self.id!r}, org={self.organization_id!r}, "
            f"status={self.status!r})"
        )


class StoredObject(Base):
    """Metadata for a file persisted in object storage (S3/MinIO).

    The raw file bytes live in the object store; this table records the
    *key* (location handle), original filename, content-type, size, and
    a SHA-256 checksum computed by the application — never trusting
    the provider-supplied ETag as a content hash.

    ``document_id`` is nullable and unconstrained (no FK yet) because the
    Document model does not exist in Phase 1.  It will be linked when
    documents are introduced.
    """

    __tablename__ = "stored_objects"
    __table_args__ = (
        Index("ix_stored_objects_org", "organization_id"),
        Index("ix_stored_objects_project", "project_id"),
        UniqueConstraint("storage_key", name="uq_stored_objects_storage_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        nullable=True,
    )
    storage_key: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_length: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"StoredObject(id={self.id!r}, org={self.organization_id!r}, "
            f"key={self.storage_key!r})"
        )


class DocumentProcessingStatus(enum.StrEnum):
    """Lifecycle stage for a DocumentVersion's parsing/OCR pipeline.

    States (CP17 state machine):

    * ``UPLOADED`` — bytes stored, queued for processing.
    * ``QUEUED`` — waiting in the background job queue.
    * ``PROCESSING`` — a worker is actively parsing/OCR-ing this version.
    * ``PARSED`` — all pages processed successfully (ready for extraction).
    * ``PARTIAL`` — processing completed but some pages failed; review needed.
    * ``FAILED`` — all retries exhausted; no usable output.

    ``UPLOADED`` is the initial state after upload (CP15).  The worker
    transitions through ``QUEUED`` → ``PROCESSING`` → ``PARSED`` /
    ``PARTIAL`` / ``FAILED``.  ``PARTIAL`` and ``FAILED`` versions may
    be retried back to ``QUEUED``.
    """

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PARSED = "parsed"
    PARTIAL = "partial"
    FAILED = "failed"


class TenderDocumentType(enum.StrEnum):
    """Logical classification of a tender document within a project."""

    TENDER = "tender"
    AMENDMENT = "amendment"
    SPECIFICATION = "specification"
    OTHER = "other"


class TenderDocument(Base):
    """Logical tender document — a named container for immutable versions.

    A single logical document can receive multiple ``DocumentVersion``
    rows over time, but the *versions* themselves are append-only and
    immutable.
    """

    __tablename__ = "tender_documents"
    __table_args__ = (
        Index("ix_tender_documents_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[TenderDocumentType] = mapped_column(
        Enum(TenderDocumentType, name="tender_document_type"),
        nullable=False,
        default=TenderDocumentType.TENDER,
        server_default=TenderDocumentType.TENDER.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"TenderDocument(id={self.id!r}, project={self.project_id!r}, "
            f"name={self.display_name!r})"
        )


class DocumentVersion(Base):
    """Immutable uploaded version of a ``TenderDocument``.

    Each row is append-only: the source ``StoredObject``, checksum, MIME,
    and size are written once and never updated.  Only ``processing_status``
    and ``updated_at`` are expected to change as the parsing pipeline
    progresses — the *bits on disk* referenced by ``stored_object_id`` are
    never mutated.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_doc_versions_doc_ver"
        ),
        Index("ix_doc_versions_document", "document_id"),
        Index("ix_doc_versions_stored_object", "stored_object_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    stored_object_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("stored_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Denormalized copy of the stored-object metadata for deterministic
    # comparisons without joining stored_objects every time.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus, name="doc_processing_status"),
        nullable=False,
        default=DocumentProcessingStatus.UPLOADED,
        server_default=DocumentProcessingStatus.UPLOADED.value,
    )
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # UTC timestamp after which this version's stored originals are eligible
    # for hard deletion per the retention policy (CP46).  NULL = no deadline.
    retention_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"DocumentVersion(id={self.id!r}, document={self.document_id!r}, "
            f"v={self.version_number!r})"
        )


# ---------------------------------------------------------------------------
# Phase 2 — OEM document ingestion and provenance (CP49)
# ---------------------------------------------------------------------------


class OemDocumentType(enum.StrEnum):
    """Logical classification of an OEM/source document.

    These are vendor-supplied materials (datasheets, brochures, manuals,
    certificates, test reports, quotations, proposals, compliance sheets) that later serve
    as evidence for compliance assessment.  They are kept strictly separate
    from tender documents (AGENTS.md: "Tender and OEM sources must remain
    distinguishable").
    """

    DATASHEET = "datasheet"
    BROCHURE = "brochure"
    MANUAL = "manual"
    CERTIFICATE = "certificate"
    TEST_REPORT = "test_report"
    QUOTATION = "quotation"
    PROPOSAL = "proposal"
    COMPLIANCE_SHEET = "compliance_sheet"
    OTHER = "other"


class OemDocument(Base):
    """Logical OEM document — a named container for immutable OEM versions.

    Mirrors :class:`TenderDocument` but lives in its own table so that
    tender sources and OEM sources are always distinguishable in queries
    (AGENTS.md guardrail for CP49).

    Carries vendor/product metadata so that downstream evidence retrieval
    (CP50) can filter by vendor or product without joining arbitrary
    JSON.
    """

    __tablename__ = "oem_documents"
    __table_args__ = (
        Index("ix_oem_documents_project", "project_id"),
        Index("ix_oem_documents_vendor", "vendor_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[OemDocumentType] = mapped_column(
        Enum(OemDocumentType, name="oem_document_type"),
        nullable=False,
        default=OemDocumentType.DATASHEET,
        server_default=OemDocumentType.DATASHEET.value,
    )
    # Vendor / product metadata for downstream evidence filtering.
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Flexible, auditable metadata (revision, issue date, language, etc.).
    # Never stores document bodies.
    document_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"OemDocument(id={self.id!r}, project={self.project_id!r}, "
            f"vendor={self.vendor_name!r}, name={self.display_name!r})"
        )


class OemDocumentVersion(Base):
    """Immutable uploaded version of an :class:`OemDocument`.

    Structurally mirrors :class:`DocumentVersion` but references
    ``oem_documents`` instead of ``tender_documents``.  The source
    ``StoredObject``, checksum, MIME, and size are written once and never
    updated — only ``processing_status`` and ``updated_at`` advance through
    the pipeline.
    """

    __tablename__ = "oem_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_oem_versions_doc_ver"
        ),
        Index("ix_oem_versions_document", "document_id"),
        Index("ix_oem_versions_stored_object", "stored_object_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("oem_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    stored_object_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("stored_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Denormalized copy of stored-object metadata for deterministic
    # comparisons without joining stored_objects every time.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus, name="oem_doc_processing_status"),
        nullable=False,
        default=DocumentProcessingStatus.UPLOADED,
        server_default=DocumentProcessingStatus.UPLOADED.value,
    )
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"OemDocumentVersion(id={self.id!r}, document={self.document_id!r}, "
            f"v={self.version_number!r})"
        )


class ProcessingStage(enum.StrEnum):
    """Ordered sub-stages within a single processing run."""

    PARSE = "parse"
    OCR = "ocr"
    CLEANUP = "cleanup"
    EXTRACT = "extract"


class RunStatus(enum.StrEnum):
    """Status of an individual :class:`ProcessingRun`."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class ProcessingRun(Base):
    """Record of a single attempt to process a :class:`DocumentVersion`.

    A version may have multiple runs over its lifetime (retries).  Each run
    tracks which *stage* failed, how many attempts were made, and the
    error reason — but the immutable source bytes referenced by
    ``DocumentVersion.stored_object_id`` are never mutated.
    """

    __tablename__ = "processing_runs"
    __table_args__ = (
        Index("ix_processing_runs_version", "document_version_id"),
        Index("ix_processing_runs_stage", "document_version_id", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    stage: Mapped[ProcessingStage] = mapped_column(
        Enum(ProcessingStage, name="processing_stage"),
        nullable=False,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"),
        nullable=False,
    )
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ProcessingRun(id={self.id!r}, version={self.document_version_id!r}, "
            f"stage={self.stage!r}, status={self.status!r})"
        )


class DocumentPage(Base):
    """A single page extracted from a :class:`DocumentVersion` during parsing.

    One row per page, ordered by ``page_number``.  ``extracted_text`` is
    the native text layer from the document parser; when the parser
    determines the text is untrustworthy (e.g. a scanned raster page),
    ``extracted_text`` is NULL and ``ocr_needed`` is set so a later OCR
    stage can fill in the gap.

    ``cleaned_text`` (CP23) is the same page text with deterministic
    header/footer noise removed.  It is a *derived* view — the raw
    ``extracted_text`` is always preserved as the authoritative source so
    cleanup never destroys provenance.  Structural metadata
    (header/footer lines, warnings, bounding boxes, font info) is stored
    as nullable JSON so non-critical signals don't block downstream
    processing.
    """

    __tablename__ = "document_pages"
    __table_args__ = (
        Index("ix_document_pages_version", "document_version_id"),
        UniqueConstraint(
            "document_version_id", "page_number", name="uq_pages_version_page"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(
        String(), nullable=True
    )
    cleaned_text: Mapped[str | None] = mapped_column(
        String(), nullable=True,
        comment="derived page text with deterministic header/footer noise "
                "removed (CP23); raw extracted_text is the source of truth",
    )
    ocr_needed: Mapped[bool] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0"
    )
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
    rendered_image_object_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    structural_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"DocumentPage(id={self.id!r}, version={self.document_version_id!r}, "
            f"page={self.page_number!r}, ocr_needed={self.ocr_needed!r})"
        )


class ExtractionRunStatus(enum.StrEnum):
    """Status of a single LLM extraction call (CP26 audit)."""

    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionRun(Base):
    """Auditable record of a single LLM extraction call (CP26).

    One row per call, anchored to the :class:`ProcessingRun` of the EXTRACT
    stage that made it.  Token counts and cost come from the provider when
    available; ``NULL`` means "unknown", never a fabricated zero (per the LLM
    logging SOP).  ``provider``/``model``/``prompt_version``/``schema_version``
    identify the exact configuration the call was made under, so operators can
    explain which extraction produced which candidates.
    """

    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_extraction_runs_run", "processing_run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    call_site: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # null = unknown pricing; never a fabricated zero.
    cost_usd: Mapped[float | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    finish_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    status: Mapped[ExtractionRunStatus] = mapped_column(
        Enum(ExtractionRunStatus, name="extraction_run_status"),
        nullable=False,
        default=ExtractionRunStatus.COMPLETED,
        server_default=ExtractionRunStatus.COMPLETED.value,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ExtractionRun(id={self.id!r}, run={self.processing_run_id!r}, "
            f"provider={self.provider!r}, model={self.model!r}, "
            f"status={self.status!r})"
        )


class ExtractionCandidate(Base):
    """A model-proposed requirement candidate that survived source validation (CP28).

    Persisted during the EXTRACT stage so CP29 (reconciliation), CP30
    (refined Requirement persistence), and CP35 (human review) can read
    deterministic extraction results.  One row per candidate the LLM emitted
    for a version's windows; ``is_valid`` is False when the candidate's
    ``raw_source`` was not found in its trusted window text (a possible
    fabrication) — such rows are kept for audit (so the invented-requirement
    rate is measurable) but are never promoted to a persisted requirement by
    CP30 (``persistable`` must be True).

    Phase 1 only: this table holds no vendor/OEM-compliance verdicts and no
    evidence — only the candidate text, its trusted source anchors, and audit
    flags (per AGENTS.md Phase 1 domain states: human review is an intentional
    state, not a compliance status).
    """

    __tablename__ = "extraction_candidates"
    __table_args__ = (
        Index("ix_extraction_candidates_version", "document_version_id"),
        Index("ix_extraction_candidates_run", "processing_run_id", "created_at"),
        Index("ix_extraction_candidates_chunk", "chunk_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # FK to the EXTRACT-stage processing run that produced the candidate.
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # The window text the candidate was cited against (trusted).
    window_text: Mapped[str] = mapped_column(String(8192), nullable=False)
    # All contributing source fragments (TrustedSourceContext dumps), so a
    # multi-page candidate is never detached from its locations.
    sources_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON, nullable=True
    )
    normalized_text: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_source: Mapped[str] = mapped_column(String(2048), nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    uncertainty: Mapped[str] = mapped_column(String(16), nullable=False)
    clause_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_warning: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    is_valid: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    persistable: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # CP29 reconciliation of these candidates against this version.
    reconciliation_group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    deduped: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    reconciliation_decision: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ExtractionCandidate(chunk={self.chunk_id!r}, "
            f"type={self.requirement_type!r}, uncertainty={self.uncertainty!r}, "
            f"persistable={self.persistable!r})"
        )


class ExtractionReconciliation(Base):
    """Audit record of a single candidate-reconciliation pass for a version (CP29).

    One row is written when :meth:`DocumentService.reconcile_version_candidates`
    runs for a version.  ``summary`` captures the deterministic counts
    (deduped / flagged_review / singleton) so duplicate rate and reconciliation
    decisions are auditable without re-deriving them.  Per-candidate decisions
    live on :class:`ExtractionCandidate` (``reconciliation_group_id`` /
    ``deduped`` / ``reconciliation_decision``).

    Phase 1 only: no vendor-compliance verdicts and no evidence columns.
    """

    __tablename__ = "extraction_reconciliations"
    __table_args__ = (
        Index(
            "ix_extraction_reconciliations_version", "document_version_id"
        ),
        Index(
            "ix_extraction_reconciliations_run",
            "processing_run_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ExtractionReconciliation(version={self.document_version_id!r}, "
            f"groups={len(self.summary)} entries)"
        )


class ExtractionDiagnostics(Base):
    """Developer-facing diagnostics for one version's EXTRACT pass (CP31).

    A single row written when the EXTRACT stage completes (one per
    :class:`ProcessingRun`, anchored via ``processing_run_id``).  Captures the
    aggregate counts (windows/calls/candidates, accepted/rejected/deduped/
    promoted/ocr-warning) plus the provider/model/prompt/schema versions and a
    rejection-breakdown + reconciliation-summary, so an operator can answer
    "why did this document produce its requirement set" from one row — without
    re-deriving the counts or re-running the stage.

    Phase 1 only: no vendor-compliance verdicts, no evidence, and **no document
    bodies** — ``rejection_breakdown`` is keyed by short reason codes.
    """

    __tablename__ = "extraction_diagnostics"
    __table_args__ = (
        Index(
            "ix_extraction_diagnostics_version", "document_version_id"
        ),
        Index(
            "ix_extraction_diagnostics_created", "created_at"
        ),
        UniqueConstraint(
            "processing_run_id", name="uq_extraction_diagnostics_run"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    total_windows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_llm_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    accepted_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rejected_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    deduped_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    promoted_requirements: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    ocr_warning_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # Extraction configuration the pass ran under (from the audited LLM calls).
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # reason-code -> count (short codes, never document bodies).
    rejection_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    # Copy of the reconciliation pass summary (the last one, if any).
    reconciliation_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ExtractionDiagnostics(version={self.document_version_id!r}, "
            f"accepted={self.accepted_candidates}, rejected="
            f"{self.rejected_candidates}, promoted="
            f"{self.promoted_requirements})"
        )


class RequirementReviewState(enum.StrEnum):
    """Phase 1 human-review states for a persisted :class:`Requirement`.

    These are *review* states only — never vendor/OEM compliance verdicts
    (Phase 2).  ``OCR_WARNING`` is set when the requirement's strongest
    source anchor is OCR-derived; otherwise a freshly promoted requirement
    starts ``UNREVIEWED`` and awaits human review (CP35).
    """

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    NEEDS_CLARIFICATION = "needs_clarification"
    OCR_WARNING = "ocr_warning"


class Requirement(Base):
    """A persisted, source-anchored technical requirement (CP30).

    Promoted from reconciled/extracted candidates (CP29/CP28).  One row per
    distinct obligation for a :class:`DocumentVersion`; reprocessing a version
    must not duplicate an unchanged requirement, so the row carries a stable
    ``promotion_key`` (content-addressed from the candidate's normalized text,
    type, clause, and contributing pages) and is upserted on reprocess.

    Phase 1 only: no vendor-compliance statuses and no evidence columns — the
    ``review_state`` is a human-review state.
    """

    __tablename__ = "requirements"
    __table_args__ = (
        Index("ix_requirements_version", "document_version_id"),
        Index("ix_requirements_group", "reconciliation_group_id"),
        UniqueConstraint(
            "document_version_id",
            "promotion_key",
            name="uq_requirements_version_promotion_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Stable identity for reprocess idempotency (CP30.9): re-running extraction
    # on an unchanged version does not duplicate rows.
    promotion_key: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    reconciliation_group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_source: Mapped[str] = mapped_column(String(2048), nullable=False)
    uncertainty: Mapped[str] = mapped_column(String(16), nullable=False)
    clause_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_warning: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    review_state: Mapped[RequirementReviewState] = mapped_column(
        Enum(RequirementReviewState, name="requirement_review_state"),
        nullable=False,
        default=RequirementReviewState.UNREVIEWED,
        server_default=RequirementReviewState.UNREVIEWED.value,
    )
    # Human-edited stable sort order for the matrix (CP39).
    # When NULL the requirement falls back to ``created_at`` ordering so the
    # initial order from extraction is always meaningful.
    display_order: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # Tri-state mandatory flag (CP39): True / False / None (unknown).
    # Kept nullable — never fabricated from a best-guess of the source text.
    mandatory: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    # Soft-delete: superseded requirements stay auditable but are excluded
    # from the default list/query surface (CP39).
    superseded: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sources: Mapped[list[RequirementSource]] = relationship(
        "RequirementSource",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    constraints: Mapped[list[RequirementConstraint]] = relationship(
        "RequirementConstraint",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Revision history: immutable rows created on every material edit.
    revisions: Mapped[list[RequirementRevision]] = relationship(
        "RequirementRevision",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Structural relations (split/merge/supersede lineage, CP39).
    relations: Mapped[list[RequirementRelation]] = relationship(  # noqa: UP037
        "RequirementRelation",
        primaryjoin="Requirement.id==RequirementRelation.source_requirement_id",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Reviewer notes persisted separately from normalized text (CP39).
    notes: Mapped[list[RequirementNote]] = relationship(
        "RequirementNote",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Categories assigned by the reviewer (CP39).
    categories: Mapped[list[Category]] = relationship(
        "Category",
        secondary="requirement_categories",
        back_populates="requirements",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Requirement(id={self.id!r}, type={self.requirement_type!r}, "
            f"state={self.review_state!r}, promoted from "
            f"group={self.reconciliation_group_id!r})"
        )


class RequirementRevision(Base):
    """Immutable history row for a :class:`Requirement` (CP38).

    One row is created on every material edit to ``normalized_text``.
    The row captures the *old* value (before the edit), the actor, a
    reason/note, and the application's view of ``updated_at`` at the time
    of the edit (for optimistic concurrency).  Raw source is never stored
    here — it lives only on the parent :class:`Requirement` and is never
    overwritten by a normalized-text edit.
    """

    __tablename__ = "requirement_revisions"
    __table_args__ = (
        Index("ix_req_revisions_requirement", "requirement_id"),
        Index("ix_req_revisions_actor", "actor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The normalized text BEFORE the edit (never the new value).
    previous_normalized_text: Mapped[str] = mapped_column(
        String(2048), nullable=False
    )
    # The updated_at value that was current at the time of the edit.
    # Used for optimistic-concurrency validation: if the caller passes
    # an ``expected_updated_at`` that does not match this, the edit is
    # rejected (ConcurrentEditError).
    updated_at_at_edit: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    # Free-form reason/note from the reviewer (e.g. "clarified unit").
    note: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    requirement: Mapped[Requirement] = relationship(
        "Requirement", back_populates="revisions", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"RequirementRevision(req={self.requirement_id!r}, "
            f"actor={self.actor_id!r}, at={self.created_at!r})"
        )


class RequirementSource(Base):
    """A trusted source anchor for a :class:`Requirement` (CP30).

    One row per contributing source fragment (usually one page; multi-page
    windows carry several).  ``location_type`` records the *strongest precision
    actually known*: ``exact`` when deterministic char offsets into the page's
    cleaned text locate ``raw_source`` verbatim, ``approximate`` otherwise
    (page/clause only).  Precision is never upgraded to EXACT on a fuzzy
    match (Bynd reuse note #4).
    """

    __tablename__ = "requirement_sources"
    __table_args__ = (
        Index("ix_requirement_sources_requirement", "requirement_id"),
        Index("ix_requirement_sources_version", "document_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    clause_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    # JSON-encoded bounding box of the raw_source on the page, when the
    # chunker/renderer produced one (never fabricated).
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    # Literal "exact"/"approximate" (LocationType values live in
    # extraction.schema; models never import extraction to avoid a circular
    # import through the package __init__ -> chunking -> models).
    location_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="approximate",
        server_default="approximate",
    )
    # The page's trusted cleaned_text (or the verbatim raw_source snippet) the
    # anchor was resolved against — preserved so the citation is source-linked.
    source_text: Mapped[str | None] = mapped_column(String(8192), nullable=True)

    requirement: Mapped[Requirement] = relationship(
        "Requirement", back_populates="sources", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"RequirementSource(req={self.requirement_id!r}, page="
            f"{self.page_number!r}, location={self.location_type!r})"
        )


class ConstraintNormalizationState(enum.StrEnum):
    """Normalization progress for a structured constraint value (CP32+).

    ``UNNORMALIZED`` is the starting point before any deterministic parser runs
    (CP33).  ``SAFE`` means the value was parsed unambiguously and matches the
    source verbatim; ``PARTIAL`` means a value was extracted but some aspect
    (operator / unit / OCR) is ambiguous; ``NEEDS_REVIEW`` means the source is
    too unreliable to normalize without risking a meaning change.  These are
    *normalization* states, not requirement review states (CP35) and not
    vendor-compliance verdicts (Phase 2).
    """

    UNNORMALIZED = "unnormalized"
    SAFE = "safe"
    PARTIAL = "partial"
    NEEDS_REVIEW = "needs_review"


class RequirementConstraint(Base):
    """A structured value extracted from a requirement (CP32).

    One row per normalized value (numeric bound, unit, tolerance, or
    qualitative condition) carried by a :class:`Requirement`.  Multiple
    constraints may attach to one requirement.  Every structured value is kept
    alongside its verbatim ``raw_fragment`` so it can be audited against the
    source (Bynd reuse note: never normalize without preserving the raw text).

    CP32 adds the model + states only; deterministic numeric/operator/unit
    parsing (CP33) and qualitative normalization (CP34) populate the parsed
    fields and transition ``normalization_state``.
    """

    __tablename__ = "requirement_constraints"
    __table_args__ = (
        Index("ix_requirement_constraints_requirement", "requirement_id"),
        Index("ix_requirement_constraints_version", "document_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # What is being constrained (e.g. "weight", "operating_temperature").
    parameter: Mapped[str] = mapped_column(String(128), nullable=False)
    # Operator symbol as parsed from the source (``=``, ``<``, ``<=``, ``>``,
    # ``>=``, ``between``, ``!=``); kept as a string so OCR-derived/ambiguous
    # operators can be recorded without fabrication (CP33 narrows these).
    operator: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # A single numeric value (``operator`` is one of = / < / > / <= / >= / !=).
    numeric_value: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    # Inclusive bounds for ranges / between operators.
    lower_bound: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    upper_bound: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tolerance: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    # Free-form qualitative condition when no numeric value exists
    # (e.g. "operational in cold rooms"). Never inferred from non-matching text.
    qualitative_condition: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    # Always start unormalized; CP33/CP34 transition to SAFE/PARTIAL/NEEDS_REVIEW.
    normalization_state: Mapped[ConstraintNormalizationState] = mapped_column(
        Enum(
            ConstraintNormalizationState,
            name="constraint_normalization_state",
        ),
        nullable=False,
        default=ConstraintNormalizationState.UNNORMALIZED,
        server_default=ConstraintNormalizationState.UNNORMALIZED.value,
    )
    # Verbatim source fragment this constraint was parsed from — never mutated,
    # never fabricated. The audit anchor for "every structured value audited
    # against its source fragment".
    raw_fragment: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    requirement: Mapped[Requirement] = relationship(
        "Requirement", back_populates="constraints", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"RequirementConstraint(requirement={self.requirement_id!r}, "
            f"parameter={self.parameter!r}, op={self.operator!r}, "
            f"state={self.normalization_state!r})"
        )


class RequirementRelationType(enum.StrEnum):
    """Structural lineage between requirements (CP39).

    These are *structural* relationships, not compliance verdicts or
    review states.  They let the matrix show the *current* active
    requirement while preserving the full split/merge/supersede history
    for audit.
    """

    SPLIT_INTO = "split_into"       # one source split into multiple targets
    MERGED_INTO = "merged_into"      # multiple sources merged into one target
    SUPERSEDES = "supersedes"        # one source supersedes another target


# Association table: many-to-many Requirement <-> Category (CP39).
requirement_categories = Table(
    "requirement_categories",
    Base.metadata,
    Column(
        "requirement_id",
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        SaUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_requirement_categories_category", "category_id"),
)


class RequirementRelation(Base):
    """A directed structural relation between two requirements (CP39).

    ``source`` → ``target`` with a :class:`RequirementRelationType`.
    For example, a SPLIT creates one row per child: (original → child, SPLIT_INTO).
    A supersede creates: (mistaken → replacement, SUPERSEDES).
    """

    __tablename__ = "requirement_relations"
    __table_args__ = (
        Index("ix_req_relations_source", "source_requirement_id"),
        Index("ix_req_relations_target", "target_requirement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type: Mapped[RequirementRelationType] = mapped_column(
        Enum(
            RequirementRelationType,
            name="requirement_relation_type",
            native_enum=False,
        ),
        nullable=False,
    )
    # The document_version_id is carried (not inferred) so a relation row
    # can be audited without a join to the source requirement.  It is set
    # from the source requirement at creation time.
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[Requirement] = relationship(
        "Requirement",
        foreign_keys=[source_requirement_id],
        back_populates="relations",
        lazy="selectin",
    )
    target: Mapped[Requirement] = relationship(
        "Requirement",
        foreign_keys=[target_requirement_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"RequirementRelation(src={self.source_requirement_id!r}, "
            f"tgt={self.target_requirement_id!r}, "
            f"typ={self.relation_type!r})"
        )


class RequirementNote(Base):
    """A reviewer note attached to a requirement (CP39).

    Notes are persisted separately from ``normalized_text`` so that the
    verbatim extraction remains a clean audit anchor while human
    commentary is still source-linked and attributable.
    """

    __tablename__ = "requirement_notes"
    __table_args__ = (
        Index("ix_req_notes_requirement", "requirement_id"),
        Index("ix_req_notes_actor", "actor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    requirement: Mapped[Requirement] = relationship(
        "Requirement", back_populates="notes", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"RequirementNote(req={self.requirement_id!r}, "
            f"actor={self.actor_id!r}, at={self.created_at!r})"
        )


class Category(Base):
    """A hierarchical requirement category scoped to a project (CP39).

    Categories let reviewers organize requirements into a stable, project-
    local taxonomy (e.g. \"Electrical\", \"Mechanical\").  The hierarchy is
    a simple parent/self FK.  Categories are *not* shared across projects.
    """

    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_project", "project_id"),
        Index("ix_categories_parent", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    parent: Mapped[Category | None] = relationship(
        "Category",
        remote_side=[id],
        backref="children",
        lazy="selectin",
    )
    requirements: Mapped[list[Requirement]] = relationship(
        "Requirement",
        secondary="requirement_categories",
        back_populates="categories",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Category(project={self.project_id!r}, name={self.name!r})"
        )


class ExportStatus(enum.StrEnum):
    """Status of a matrix export job (CP42)."""

    COMPLETED = "completed"
    FAILED = "failed"


class ExportFormat(enum.StrEnum):
    """Format of a generated export artifact (CP42, extended in CP60)."""

    XLSX = "xlsx"
    DOCX = "docx"
    PDF = "pdf"


class ExportArtifact(Base):
    """Record of a matrix XLSX export for a document version (CP42).

    Each row represents one export attempt.  Multiple historical exports
    are retained so reviewers can see what was exported when.  The actual
    workbook bytes live in object storage (``stored_object_id``); this row
    is the metadata pointer.

    ``status`` captures success or failure.  When ``FAILED``,
    ``error_message`` holds the failure reason so the UI can surface it
    without retrying blindly.
    """

    __tablename__ = "export_artifacts"
    __table_args__ = (
        Index("ix_export_artifacts_version", "document_version_id"),
        Index("ix_export_artifacts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stored_object_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("stored_objects.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, name="export_status", native_enum=False),
        nullable=False,
        default=ExportStatus.COMPLETED,
        server_default=ExportStatus.COMPLETED.value,
    )
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    requirement_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    workbook_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    export_format: Mapped[ExportFormat] = mapped_column(
        Enum(
            ExportFormat,
            name="export_format",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=ExportFormat.XLSX,
        server_default=ExportFormat.XLSX.value,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ExportArtifact(version={self.document_version_id!r}, "
            f"status={self.status!r}, count={self.requirement_count})"
        )


# ---------------------------------------------------------------------------
# Phase 2 — Evidence retrieval and curation (CP50)
# ---------------------------------------------------------------------------


class EvidenceReviewState(enum.StrEnum):
    """Curation state of a proposed evidence candidate (CP50).

    ``PROPOSED`` means the retrieval engine surfaced this candidate but no
    human has accepted or rejected it yet.  ``ACCEPTED`` and ``REJECTED``
    are the two possible human decisions.  This is a *curation* state, not a
    compliance verdict — compliance assessment is Phase 2.
    """

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OemTextSegment(Base):
    """A searchable text segment extracted from an OEM document version.

    Segments are produced by the parsing/cleanup pipeline (CP21/CP23) and
    enable deterministic keyword retrieval against OEM source material.
    Each segment is tied to a specific OEM document version's immutable
    bytes — never to a tender document.

    The ``text`` column holds the cleaned, searchable text.  ``start_char``
    and ``end_char`` are offsets into the page's full text, allowing exact
    reconstruction of the source excerpt (requirement: "Every candidate opens
    its actual OEM source").
    """

    __tablename__ = "oem_text_segments"
    __table_args__ = (
        Index("ix_oem_segments_version", "oem_document_version_id"),
        Index("ix_oem_segments_page", "oem_document_version_id", "page_number"),
        UniqueConstraint(
            "oem_document_version_id",
            "page_number",
            "segment_index",
            name="uq_oem_segments_lookup",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    oem_document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    start_char: Mapped[int] = mapped_column(Integer(), nullable=False)
    end_char: Mapped[int] = mapped_column(Integer(), nullable=False)
    text: Mapped[str] = mapped_column(String(), nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Evidence(Base):
    """A proposed evidence candidate linking an OEM source to a requirement.

    One row per (requirement, oem_document_version) pair returned by the
    retrieval engine.  The actual source location is recorded via
    :class:`EvidenceLocation` children — a single evidence row can have
    multiple locations (the requirement may span multiple pages or segments).

    ``review_state`` tracks whether a human has curated the candidate.
    ``score`` and ``retrieval_config`` are recorded so the retrieval
    query/config/version/ranking signals are auditable (CP50.6).
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_requirement", "requirement_id"),
        Index("ix_evidence_oem_version", "oem_document_version_id"),
        Index("ix_evidence_review_state", "review_state"),
        Index(
            "ix_evidence_requirement_score",
            "requirement_id",
            "score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    oem_document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Rank score from the retrieval engine (0.0–1.0). Always recorded —
    # never fabricated; NULL only if the retrieval method did not produce
    # a score (rare, but supported for future retrieval methods).
    score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    retrieval_method: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="keyword"
    )
    # JSON config/version/ranking signals for auditability (CP50.6).
    retrieval_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    review_state: Mapped[EvidenceReviewState] = mapped_column(
        Enum(EvidenceReviewState, name="evidence_review_state"),
        nullable=False,
        default=EvidenceReviewState.PROPOSED,
        server_default=EvidenceReviewState.PROPOSED.value,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    locations: Mapped[list[EvidenceLocation]] = relationship(
        "EvidenceLocation",
        back_populates="evidence",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Evidence(req={self.requirement_id!r}, "
            f"oem_version={self.oem_document_version_id!r}, "
            f"state={self.review_state!r})"
        )


class EvidenceLocation(Base):
    """A source location within an OEM document that supports an :class:`Evidence` row.

    Mirrors :class:`RequirementSource`'s precision-preserving fields:
    ``location_type`` records the strongest precision actually known,
    ``source_text`` is the verbatim excerpt, and ``ocr_confidence`` is NULL
    unless the segment was OCR-derived.
    """

    __tablename__ = "evidence_locations"
    __table_args__ = (
        Index("ix_evidence_locations_evidence", "evidence_id"),
        Index("ix_evidence_locations_segment", "oem_text_segment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    oem_text_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    oem_document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    clause_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    location_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="approximate",
        server_default="approximate",
    )
    source_text: Mapped[str | None] = mapped_column(String(8192), nullable=True)

    evidence: Mapped[Evidence] = relationship(
        "Evidence", back_populates="locations", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"EvidenceLocation(evidence={self.evidence_id!r}, "
            f"page={self.page_number!r}, loc={self.location_type!r})"
        )


class VendorSpecExtractionMethod(enum.StrEnum):
    """How a :class:`VendorSpec` was produced (CP52)."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class VendorSpec(Base):
    """A structured vendor specification extracted from OEM evidence (CP52).

    One row per structured fact (e.g. "accuracy ±0.5 %", "resolution 0.01 mm")
    parsed deterministically from an accepted :class:`Evidence` row's source
    text.  Every vendor fact MUST point to its supporting evidence — the
    foreign key is non-nullable and cascades on delete.

    Source linkage is preserved at the same precision as
    :class:`EvidenceLocation` (page, char offsets, source_text, ocr_confidence,
    location_type) so "a structured vendor fact can always be traced back to
    OEM source material" (checkpoint completion criterion).

    The ``parameter`` field captures the conceptual quantity (e.g.
    ``accuracy``, ``resolution``, ``mass``, ``temperature``) — never collapsing
    distinct technical concepts that happen to share a unit (e.g. accuracy vs
    resolution).  ``entity`` captures a product/model designation when present
    in the source text.  ``conditions`` holds operating-condition context
    (temperature, humidity, etc.) as structured JSON.

    ``normalization_state`` reuses :class:`ConstraintNormalizationState` so
    that ambiguous/OCR-derived specs are escalated to PARTIAL / NEEDS_REVIEW
    rather than silently corrected.
    """

    __tablename__ = "vendor_specs"
    __table_args__ = (
        Index("ix_vendor_specs_evidence", "evidence_id"),
        Index("ix_vendor_specs_requirement", "requirement_id"),
        Index("ix_vendor_specs_parameter", "parameter"),
        Index(
            "ix_vendor_specs_evidence_parameter",
            "evidence_id",
            "parameter",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Every vendor fact must point to its supporting evidence.
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Link back to the tender requirement this spec helps assess.
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    oem_document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("oem_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    oem_text_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    # The conceptual quantity being specified (e.g. "accuracy", "resolution",
    # "mass", "temperature").  Never collapsed with the unit.
    parameter: Mapped[str] = mapped_column(String(128), nullable=False)
    # Optional product/model designation extracted from the source text
    # (e.g. "Model XYZ-123").
    entity: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Single numeric value (operator = / <= / >= etc.).
    value: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    # Inclusive bounds for ranges / between operators.
    lower_bound: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    upper_bound: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tolerance: Mapped[float | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    # Free-form qualitative statement for non-numeric specs
    # (e.g. "CE marked", "IP65 rated").  Never inferred from vague prose.
    qualitative_statement: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    # Operating conditions context (e.g. {"ambient_temperature": "25°C"}).
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Verbatim source fragment this spec was parsed from — never fabricated.
    source_text: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_page_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    location_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="approximate",
        server_default="approximate",
    )
    extraction_method: Mapped[VendorSpecExtractionMethod] = mapped_column(
        Enum(
            VendorSpecExtractionMethod,
            name="vendor_spec_extraction_method",
        ),
        nullable=False,
        default=VendorSpecExtractionMethod.DETERMINISTIC,
        server_default=VendorSpecExtractionMethod.DETERMINISTIC.value,
    )
    extraction_version: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    normalization_state: Mapped[ConstraintNormalizationState] = mapped_column(
        Enum(
            ConstraintNormalizationState,
            name="constraint_normalization_state",
        ),
        nullable=False,
        default=ConstraintNormalizationState.UNNORMALIZED,
        server_default=ConstraintNormalizationState.UNNORMALIZED.value,
    )
    issues: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"VendorSpec(evidence={self.evidence_id!r}, "
            f"parameter={self.parameter!r}, "
            f"value={self.value!r}, unit={self.unit!r})"
        )


class ComplianceStatus(enum.StrEnum):
    """System-assessed compliance status for a tender requirement (CP54).

    These are the product-defined statuses.  Each assessment is paired with
    a ``reason_code`` and ``reason_text`` for traceability.

    - ``COMPLIANT``: Evidence demonstrates the requirement is met.
    - ``NON_COMPLIANT``: Evidence demonstrates the requirement is violated
      (same dimension, value outside constraint).
    - ``PARTIAL``: Some evidence supports the requirement but gaps remain.
    - ``NOT_DEMONSTRATED``: No evidence was found for this requirement.
    - ``CONFLICT``: Multiple accepted evidence items conflict.
    - ``HUMAN_REVIEW_REQUIRED``: Engine cannot evaluate deterministically.
    """

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_DEMONSTRATED = "not_demonstrated"
    CONFLICT = "conflict"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class ComplianceAssessment(Base):
    """A deterministic system assessment of one tender requirement vs vendor evidence (CP54).

    Each row represents the **system suggestion** for a requirement.  A
    reviewer can later confirm or override it.  Assessments are versioned:
    when evidence or vendor specs change, a new assessment row is created
    (the previous row is never modified — append-only history).

    The assessment is derived from the deterministic comparison engine (CP53)
    — the ``comparison_result_json`` column stores the full
    :class:`~tender_compliance_api.extraction.spec_comparison.ComparisonResult`
    for auditability.
    """

    __tablename__ = "compliance_assessments"
    __table_args__ = (
        Index("ix_compliance_assessments_project", "project_id"),
        Index("ix_compliance_assessments_requirement", "requirement_id"),
        Index("ix_compliance_assessments_status", "status"),
        UniqueConstraint(
            "requirement_id",
            "assessment_version",
            name="uq_compliance_assessments_requirement_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vendor_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("vendor_specs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # System suggestion (before human confirmation).
    suggested_status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, name="compliance_status"),
        nullable=False,
    )
    # Final status — equals suggested_status until a human confirms/overrides.
    status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, name="compliance_status"),
        nullable=False,
    )
    # Machine-readable reason for the status (e.g. "range_containment",
    # "parameter_mismatch", "no_evidence_found").
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    # Human-readable explanation of the verdict and its inputs.
    reason_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Full ComparisonResult details (verdict, conversion, reasons, values).
    comparison_result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    # Assessment version number — increments when a new assessment is
    # generated for the same requirement (evidence/specs changed).
    assessment_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    # System suggested status is confirmed by a human (never fabricated).
    is_confirmed_by_human: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    vendor_spec: Mapped[VendorSpec | None] = relationship(
        "VendorSpec", backref="compliance_assessments", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ComplianceAssessment(req={self.requirement_id!r}, "
            f"status={self.status.value!r}, "
            f"version={self.assessment_version})"
        )


class AssessmentCommentType(enum.StrEnum):
    """Category of a reviewer comment on a compliance assessment (CP58)."""

    COMMENT = "comment"
    """Free-form reviewer note."""

    NOTE = "note"
    """Reviewer note that is not a structured override/reopen reason."""

    OVERRIDE_REASON = "override_reason"
    """Recorded as the structured rationale for a status override."""

    REOPEN_REASON = "reopen_reason"
    """Recorded as the structured rationale for reopening an assessment."""


class AssessmentComment(Base):
    """Append-only reviewer comment on a compliance assessment version (CP58).

    Comments are always tied to a specific ``assessment_id`` (and its
    ``assessment_version``), so they survive re-assessment: a new assessment
    version creates a fresh context, and old comments remain attached to the
    version they pertain to.  The comment text is stored verbatim.
    """

    __tablename__ = "assessment_comments"
    __table_args__ = (
        Index("ix_assessment_comments_assessment", "assessment_id"),
        Index("ix_assessment_comments_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("compliance_assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment_type: Mapped[AssessmentCommentType] = mapped_column(
        Enum(AssessmentCommentType, name="assessment_comment_type"),
        nullable=False,
        server_default=AssessmentCommentType.COMMENT.value,
    )
    comment: Mapped[str] = mapped_column(String(4096), nullable=False)
    assessment_version: Mapped[int] = mapped_column(
        Integer(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"AssessmentComment(assessment={self.assessment_id!r}, "
            f"type={self.comment_type.value!r}, "
            f"version={self.assessment_version})"
        )


class QualitativeVerdict(enum.StrEnum):
    """Source-bounded qualitative reasoning outcomes (CP55).

    These describe whether cited *language* evidence supports, contradicts,
    or fails to address a requirement.  They are deliberately separate from
    the numeric ``ComparisonVerdict`` (CP53) — deterministic numeric results
    remain authoritative and are never overridden by qualitative reasoning.

    - ``SUPPORT`` — cited evidence text explicitly addresses the
      requirement in a supporting way.
    - ``MISMATCH`` — cited evidence text explicitly contradicts the
      requirement.
    - ``UNSUPPORTED`` — cited evidence does not address the requirement
      (the requirement is silent on the evidence's scope).
    - ``CONFLICT`` — multiple cited sources contradict each other for the
      same conceptual parameter.
    - ``INSUFFICIENT_EVIDENCE`` — no accepted evidence exists or the
      evidence is too narrow to judge.
    - ``UNCERTAIN`` — reasoning is uncertain (OCR, ambiguity) — never
      silently downgraded to a confident verdict.
    """

    SUPPORT = "support"
    MISMATCH = "mismatch"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNCERTAIN = "uncertain"


class QualitativeAssessment(Base):
    """Source-bounded qualitative reasoning result for a tender requirement (CP55).

    Produced by :class:`~tender_compliance_api.compliance.reasoning.
    QualitativeReasoningService`.  Unlike the deterministic numeric
    comparison (CP53/CP54), qualitative reasoning interprets *language* —
    but only the cited, accepted evidence text is ever consulted.  The
    model/adapter NEVER receives the full OEM document body; it receives
    only the per-segment source texts that have been accepted as evidence.

    ``evidence_ids`` records the exact list of evidence UUIDs the reasoning
    consulted, so "the model cannot cite a source not supplied" (checkpoint
    verification criterion) is enforceable by test.

    Deterministic numeric results (``ComparisonResult`` /
    ``ComplianceAssessment``) remain authoritative: when a numeric verdict
    of MATCH/MISMATCH/CLOSE/PARTIAL already exists, the qualitative verdict
    mirrors it rather than re-evaluating the numbers.
    """

    __tablename__ = "qualitative_assessments"
    __table_args__ = (
        Index("ix_qualitative_assessments_project", "project_id"),
        Index("ix_qualitative_assessments_requirement", "requirement_id"),
        Index("ix_qualitative_assessments_verdict", "verdict"),
        Index(
            "ix_qualitative_assessments_compliance",
            "compliance_assessment_id",
        ),
        UniqueConstraint(
            "requirement_id",
            "assessment_version",
            name="uq_qualitative_assessments_requirement_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    compliance_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("compliance_assessments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verdict: Mapped[QualitativeVerdict] = mapped_column(
        Enum(QualitativeVerdict, name="qualitative_verdict"),
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_text: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    # Structured list of attribution/scope mismatches, e.g.
    # [{"field": "entity", "requirement": "Model X", "evidence": "Model Y"}].
    attribution_mismatches: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    # Exact list of evidence UUID strings the reasoning consulted.  The
    # model is never allowed to cite a source not in this list.
    # Stored as JSON array of UUID strings (JSON has no native UUID type).
    evidence_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    source_contradiction: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reasoning_version: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    assessment_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    is_confirmed_by_human: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="0"
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"QualitativeAssessment(req={self.requirement_id!r}, "
            f"verdict={self.verdict.value!r}, "
            f"version={self.assessment_version})"
        )


class ConflictResolution(enum.StrEnum):
    """Resolution state for a detected conflict (CP56).

    ``UNRESOLVED`` means the conflict has not yet been reviewed.  ``ACCEPTED``
    and ``REJECTED`` are the two possible human decisions — but the system
    never silently picks by priority, set union, or arrival order.  Both
    conflicting sources are always preserved.
    """

    UNRESOLVED = "unresolved"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Conflict(Base):
    """A detected contradiction between vendor claims for a requirement (CP56).

    Conflicts are persistent and auditable.  EVERY conflicting source is
    preserved in the ``sources`` JSON array — the system never discards
    inconvenient evidence to silently resolve a conflict.

    ``conflict_type`` classifies the contradiction:
    - ``parameter_value`` — same parameter, different numeric values across
      accepted evidence items (e.g. one datasheet says 25 °C, another says 30 °C).
    - ``concept_mismatch`` — same unit but different conceptual parameter
      (e.g. accuracy vs resolution).
    - ``tender_vendor`` — the requirement text and evidence text directly
      contradict (e.g. "shall be CE marked" vs "not CE marked").

    Conflict is NOT automatically non-compliance — a reviewer must
    investigate and resolve.
    """

    __tablename__ = "conflicts"
    __table_args__ = (
        Index("ix_conflicts_requirement", "requirement_id"),
        Index("ix_conflicts_type", "conflict_type"),
        Index("ix_conflicts_resolution", "resolution"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Classifies the contradiction.
    conflict_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # The conceptual parameter in conflict (e.g. "temperature", "accuracy").
    parameter: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Product/model entity in conflict (optional).
    entity: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # JSON array of source descriptors — preserves ALL conflicting sources.
    # Each entry: {"evidence_id", "vendor_spec_id", "source_text", "value",
    # "unit", "oem_document_version_id", "source_page_number"}
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    # The relevant requirement text — preserved for side-by-side review.
    tender_claim: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    # Optional link to the vendor spec that originated the conflict detection.
    tender_vendor_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("vendor_specs.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution: Mapped[ConflictResolution] = mapped_column(
        Enum(ConflictResolution, name="conflict_resolution"),
        nullable=False,
        default=ConflictResolution.UNRESOLVED,
        server_default=ConflictResolution.UNRESOLVED.value,
    )
    resolution_notes: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Conflict(req={self.requirement_id!r}, type={self.conflict_type!r}, "
            f"resolution={self.resolution.value!r})"
        )


# ---------------------------------------------------------------------------
# CP57 — Clarification requests and deviations
# ---------------------------------------------------------------------------


class ClarificationStatus(enum.StrEnum):
    """Lifecycle state of a clarification request (CP57).

    ``PENDING`` means the question has been asked but not yet answered.
    ``ANSWERED`` means a human has provided an answer.  ``EXPIRED`` means
    the request was not answered within the project's response window
    (if one is configured) — the requirement remains unresolved.
    """

    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"


class DeviationType(enum.StrEnum):
    """Category of a vendor deviation from the original requirement (CP57)."""

    SCOPE = "scope"
    """Vendor proposes to exclude or narrow the scope of the requirement."""

    VALUE = "value"
    """Vendor proposes a different numeric value / range than required."""

    CAPABILITY = "capability"
    """Vendor lacks the required capability altogether."""

    OTHER = "other"
    """Other type of deviation."""


class DeviationStatus(enum.StrEnum):
    """Review state of a deviation (CP57)."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ClarificationRequest(Base):
    """A question posed when evidence is insufficient or ambiguous (CP57).

    Clarification requests are **not** the same as conflicts (CP56).  A
    conflict means two sources say different things.  A clarification
    request means we don't have enough information to make any determination.

    The ``context`` JSON carries structured metadata about *why* the
    question is being asked (e.g. ``{"reason": "missing_evidence",
    "parameter": "accuracy"}`` or ``{"reason": "conflict",
    "conflict_id": "..."}``).  This is audit information, not
    machine-processable evidence.
    """

    __tablename__ = "clarification_requests"
    __table_args__ = (
        Index(
            "ix_clarification_requests_project", "project_id"
        ),
        Index(
            "ix_clarification_requests_requirement", "requirement_id"
        ),
        Index(
            "ix_clarification_requests_status", "status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # The question text — verbatim, never synthesized.
    question: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Structured metadata about why the question is being asked.
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[ClarificationStatus] = mapped_column(
        Enum(ClarificationStatus, name="clarification_status"),
        nullable=False,
        default=ClarificationStatus.PENDING,
        server_default=ClarificationStatus.PENDING.value,
    )
    # Evidence IDs that were examined but found insufficient.
    related_evidence_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    # Conflict IDs that triggered the clarification request.
    related_conflict_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    asked_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # The answer provided by a human / OEM.
    answer: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"ClarificationRequest(req={self.requirement_id!r}, "
            f"status={self.status.value!r}, "
            f"asked_at={self.asked_at!r})"
        )


class Deviation(Base):
    """A vendor deviation from the original tender requirement (CP57).

    A deviation is a proposal to change the rule — different scope, value,
    or capability.  It must be explicitly ACCEPTED or REJECTED by a human
    reviewer.  The ``original_requirement`` field preserves the verbatim
    source text of the requirement being deviated from.
    """

    __tablename__ = "deviations"
    __table_args__ = (
        Index(
            "ix_deviations_project", "project_id"
        ),
        Index(
            "ix_deviations_requirement", "requirement_id"
        ),
        Index(
            "ix_deviations_status", "status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deviation_type: Mapped[DeviationType] = mapped_column(
        Enum(DeviationType, name="deviation_type"),
        nullable=False,
    )
    # Verbatim text of the original requirement — preserved for review.
    original_requirement: Mapped[str] = mapped_column(
        String(2048), nullable=False
    )
    # What the vendor proposes instead.
    proposed_alternative: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    # Rationale for the deviation (e.g. technical impossibility, cost).
    rationale: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    status: Mapped[DeviationStatus] = mapped_column(
        Enum(DeviationStatus, name="deviation_status"),
        nullable=False,
        default=DeviationStatus.PROPOSED,
        server_default=DeviationStatus.PROPOSED.value,
    )
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Deviation(req={self.requirement_id!r}, type={self.deviation_type.value!r}, "
            f"status={self.status.value!r})"
        )


class SubmissionStatus(enum.StrEnum):
    """Lifecycle states for a submission (CP61).

    DRAFT → LOCKED → APPROVED → REVOKED
    After LOCKED or APPROVED, later changes create a new submission with an
    incremented version_number rather than mutating the existing one.
    """

    DRAFT = "draft"
    LOCKED = "locked"
    APPROVED = "approved"
    REVOKED = "revoked"


class Submission(Base):
    """Immutable snapshot of the final compliance matrix at a milestone (CP61).

    A submission captures the approved state of the final matrix for a
    document version.  Once locked or approved, the snapshot is immutable —
    later changes create a new submission version.

    ``assessment_snapshot`` stores a JSON array of requirement-level
    assessment IDs and their versions so a signed-off submission can be
    reproduced exactly even as assessments evolve.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_project", "project_id"),
        Index("ix_submissions_status", "status"),
        UniqueConstraint(
            "project_id", "version_number", name="uq_submissions_project_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(
            SubmissionStatus,
            name="submission_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=SubmissionStatus.DRAFT,
        server_default=SubmissionStatus.DRAFT.value,
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    assessment_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON(), nullable=False,
    )
    matrix_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    matrix_export_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True),
        ForeignKey("export_artifacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Submission(project={self.project_id!r}, v={self.version_number}, "
            f"status={self.status.value!r})"
        )

