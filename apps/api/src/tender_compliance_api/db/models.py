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
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import UUID as SaUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tender_compliance_api.db.base import Base


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sources: Mapped[list[RequirementSource]] = relationship(
        "RequirementSource",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return (
            f"Requirement(id={self.id!r}, type={self.requirement_type!r}, "
            f"state={self.review_state!r}, promoted from "
            f"group={self.reconciliation_group_id!r})"
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
