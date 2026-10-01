"""Document upload API route (CP13, upgraded by CP15).

Receives a multipart file upload, validates it (extension, magic-bytes,
size, PDF integrity), scans for malware, stores the bytes in the object
store, persists a :class:`StoredObject` metadata row, creates a
``TenderDocument`` + immutable ``DocumentVersion``, and transitions
the project status to ``TENDER_UPLOADED``.

Duplicate-content handling (CP15):

* If a :class:`StoredObject` with the same SHA-256 already exists for
  the organization, the bytes are **not** stored again — the existing
  row is reused.
* If a :class:`TenderDocument` already exists for the project, a new
  :class:`DocumentVersion` is created on that document with the next
  sequential version number.  Otherwise a new ``TenderDocument`` is
  created and the version starts at 1.

Rejected files never enter normal processing — they are audited and a
``422`` response with explicit failure reasons is returned.

Storage and scanning are injected as FastAPI dependencies so tests
can override them with fakes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    ProjectStatus,
    StoredObject,
    TenderDocument,
    TenderDocumentType,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.project import (
    ProjectArchivedError,
    ProjectNotFoundError,
    ProjectService,
    StateTransitionError,
)
from tender_compliance_api.scan.adapter import MalwareScanner, ScanResult
from tender_compliance_api.scan.fake import FakeScanner
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_api.validation.models import ValidationResult
from tender_compliance_api.validation.service import ValidationService

router = APIRouter(prefix="/projects", tags=["uploads"])


# ---------------------------------------------------------------------------
# Dependency providers (overridable in tests)
# ---------------------------------------------------------------------------


def get_storage_adapter() -> ObjectStorageAdapter:
    """Return an ObjectStorageAdapter based on configuration.

    Uses :class:`FakeStorageAdapter` when no endpoint is configured
    (development / CI).  In production this returns an
    :class:`S3StorageAdapter`.
    """
    settings = get_settings()
    if not settings.object_storage_endpoint:
        return FakeStorageAdapter()
    # Imported lazily so tests never need boto3 credentials configured.
    from tender_compliance_api.storage.s3 import S3StorageAdapter

    adapter = S3StorageAdapter(
        endpoint_url=settings.object_storage_endpoint,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=settings.object_storage_bucket,
        region=settings.object_storage_region,
    )
    return adapter


def get_scanner() -> MalwareScanner:
    """Return the configured malware scanner (FakeScanner by default)."""
    return FakeScanner()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Serialized upload result returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    stored_object_id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    storage_key: str
    filename: str
    content_type: str
    content_length: int
    checksum_sha256: str
    project_status: ProjectStatus
    uploaded_at: datetime


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/{project_id}/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),  # noqa: B008
    scanner: MalwareScanner = Depends(get_scanner),  # noqa: B008
) -> UploadResponse:
    """Validate, scan, and store a single uploaded document.

    The project must belong to the authenticated organization.  The file
    is validated (extension, signature, size, PDF integrity) and scanned
    for malware before being persisted to object storage.

    If the exact same bytes (same SHA-256) were already uploaded for this
    organization, the existing :class:`StoredObject` is reused — the bytes
    are not stored again.  A new :class:`DocumentVersion` is created on the
    project's :class:`TenderDocument` (creating the document if this is the
    first upload).

    Rejected files are audited and a ``422`` response is returned with
    explicit failure reasons.
    """
    # --- Verify project ownership ---
    project_svc = ProjectService(session)
    try:
        project = await project_svc.get_or_raise(auth, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None

    # --- Read file data ---
    data = await file.read()
    if not data:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.upload_rejected",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={"reason": "empty file", "filename": file.filename},
        )
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail="Uploaded file is empty",
        )

    filename = file.filename or "unnamed"

    # --- Validate ---
    validator = ValidationService()
    result: ValidationResult = validator.validate(
        filename, file.content_type, data
    )

    if not result.valid:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.upload_rejected",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={
                "reason": "validation_failed",
                "filename": filename,
                "errors": result.errors,
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail=f"File rejected: {'; '.join(result.errors)}",
        )

    # --- Scan for malware ---
    scan_result: ScanResult = await scanner.scan(filename, data)
    if not scan_result.clean:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.upload_rejected",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={
                "reason": "malware_detected",
                "filename": filename,
                "threat_name": scan_result.threat_name,
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail=f"Malware detected: {scan_result.threat_name}",
        )

    # --- Compute SHA-256 for duplicate detection ---
    checksum = hashlib.sha256(data).hexdigest()

    # --- Check for existing StoredObject with same checksum (reuse bytes) ---
    existing_stored_result = await session.execute(
        select(StoredObject).where(
            StoredObject.organization_id == auth.organization_id,
            StoredObject.checksum_sha256 == checksum,
        )
    )
    existing_stored = existing_stored_result.scalar_one_or_none()

    # --- Find existing TenderDocument for this project ---
    existing_doc_result = await session.execute(
        select(TenderDocument).where(
            TenderDocument.project_id == project_id
        )
    )
    existing_doc = existing_doc_result.scalar_one_or_none()

    bytes_reused: bool = existing_stored is not None

    # ------------------------------------------------------------------
    # Branch: determine stored object + document version
    # ------------------------------------------------------------------

    if existing_stored is not None and existing_doc is not None:
        # Same bytes already stored for this org, and a document exists.
        # Reuse the existing StoredObject and create a new version.
        stored_obj = existing_stored
        doc_id = existing_doc.id
        storage_key = stored_obj.storage_key
        max_result = await session.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == doc_id
            )
        )
        next_version = (max_result.scalar_one() or 0) + 1

    elif existing_doc is not None:
        # Different content but document exists — new version with new bytes.
        doc_id = existing_doc.id
        max_result = await session.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == doc_id
            )
        )
        next_version = (max_result.scalar_one() or 0) + 1

        storage_key = build_key(
            org_id=auth.organization_id,
            project_id=project_id,
            document_id=doc_id,
            version=next_version,
            original_filename=filename,
        )
        object_info = await storage.put(
            storage_key, data,
            result.detected_content_type or "application/octet-stream",
        )
        stored_obj = StoredObject(
            organization_id=auth.organization_id,
            project_id=project_id,
            document_id=doc_id,
            storage_key=storage_key,
            filename=filename,
            content_type=object_info.content_type,
            content_length=object_info.content_length,
            checksum_sha256=object_info.checksum_sha256,
            etag=object_info.etag,
        )
        session.add(stored_obj)
        await session.flush()

    else:
        # First upload to this project — new document + new bytes.
        tender_doc = TenderDocument(
            project_id=project_id,
            display_name=filename,
            document_type=TenderDocumentType.TENDER,
        )
        session.add(tender_doc)
        await session.flush()
        doc_id = tender_doc.id
        next_version = 1

        storage_key = build_key(
            org_id=auth.organization_id,
            project_id=project_id,
            document_id=doc_id,
            version=next_version,
            original_filename=filename,
        )
        object_info = await storage.put(
            storage_key, data,
            result.detected_content_type or "application/octet-stream",
        )
        stored_obj = StoredObject(
            organization_id=auth.organization_id,
            project_id=project_id,
            document_id=doc_id,
            storage_key=storage_key,
            filename=filename,
            content_type=object_info.content_type,
            content_length=object_info.content_length,
            checksum_sha256=object_info.checksum_sha256,
            etag=object_info.etag,
        )
        session.add(stored_obj)
        await session.flush()

    # --- Create immutable DocumentVersion ---
    doc_version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_number=next_version,
        stored_object_id=stored_obj.id,
        sha256=stored_obj.checksum_sha256,
        mime_type=stored_obj.content_type,
        size_bytes=stored_obj.content_length,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    session.add(doc_version)
    await session.flush()

    # --- Transition project status ---
    try:
        project = await project_svc.mark_uploaded(auth, project_id)
    except (ProjectArchivedError, StateTransitionError) as exc:
        # Already uploaded — not a hard failure, just log and continue.
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.upload",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={
                "filename": filename,
                "storage_key": storage_key,
                "document_id": str(doc_id),
                "version_number": next_version,
                "bytes_reused": bytes_reused,
                "reason": str(exc),
            },
        )
        await session.refresh(project)
    else:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.upload",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={
                "filename": filename,
                "storage_key": storage_key,
                "document_id": str(doc_id),
                "version_number": next_version,
                "bytes_reused": bytes_reused,
                "content_length": stored_obj.content_length,
                "checksum_sha256": checksum,
            },
        )

    await session.commit()
    await session.refresh(project)
    await session.refresh(stored_obj)
    await session.refresh(doc_version)

    return UploadResponse(
        stored_object_id=stored_obj.id,
        document_id=doc_id,
        version_number=next_version,
        storage_key=stored_obj.storage_key,
        filename=filename,
        content_type=stored_obj.content_type,
        content_length=stored_obj.content_length,
        checksum_sha256=stored_obj.checksum_sha256,
        project_status=project.status,
        uploaded_at=stored_obj.created_at,
    )
