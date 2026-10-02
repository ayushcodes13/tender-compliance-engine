"""OEM document upload and listing API route (CP49).

Receives a multipart file upload for an OEM/source document, validates it
(same hostile-file controls as tender uploads), scans for malware, stores
the bytes in the object store, persists a :class:`StoredObject` metadata row,
creates an :class:`OemDocument` + immutable :class:`OemDocumentVersion`,
and enqueues for background processing — reusing every adapter the tender
upload path uses (storage, scanner, queue, validation).

Tender and OEM sources are kept in **separate** tables so they are always
distinguishable in queries (AGENTS.md guardrail for CP49).  OEM documents
carry vendor/product metadata for downstream evidence retrieval (CP50+).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    OemDocument,
    OemDocumentType,
    OemDocumentVersion,
    ProcessingStage,
    StoredObject,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import DocumentService
from tender_compliance_api.project import ProjectNotFoundError, ProjectService
from tender_compliance_api.queue import DEFAULT_QUEUE, QueueAdapter, QueueMessage

# Reuse the same storage/scanner/queue dependencies as tender uploads.
from tender_compliance_api.routes.uploads import (
    get_queue_adapter,
    get_scanner,
    get_storage_adapter,
)
from tender_compliance_api.scan.adapter import MalwareScanner, ScanResult
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.validation.models import ValidationResult
from tender_compliance_api.validation.service import ValidationService

router = APIRouter(
    prefix="/projects/{project_id}/oem-documents",
    tags=["oem-documents"],
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OemUploadResponse(BaseModel):
    """Serialized OEM upload result returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    stored_object_id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    storage_key: str
    filename: str
    content_type: str
    content_length: int
    checksum_sha256: str
    processing_status: str
    uploaded_at: datetime


class OemDocumentVersionResponse(BaseModel):
    """A single immutable OEM document version."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    display_name: str
    document_type: str
    vendor_name: str | None
    product_name: str | None
    product_sku: str | None
    version_number: int
    sha256: str
    mime_type: str
    size_bytes: int
    processing_status: str
    parser_name: str | None = None
    parser_version: str | None = None
    ocr_name: str | None = None
    ocr_version: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=OemUploadResponse,
    status_code=201,
)
async def upload_oem_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),  # noqa: B008
    document_type: str = Form("datasheet"),
    vendor_name: str | None = Form(None),  # noqa: B008
    product_name: str | None = Form(None),  # noqa: B008
    product_sku: str | None = Form(None),  # noqa: B008
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),  # noqa: B008
    scanner: MalwareScanner = Depends(get_scanner),  # noqa: B008
    queue: QueueAdapter = Depends(get_queue_adapter),  # noqa: B008
) -> OemUploadResponse:
    """Validate, scan, and store a single OEM document.

    The project must belong to the authenticated organization.  The file is
    validated (extension, signature, size, format integrity), scanned for
    malware, and stored in object storage.  An :class:`OemDocument` is created
    (or reused if one with the same name exists for the project), and a new
    immutable :class:`OemDocumentVersion` is persisted.

    The same hostile-file controls, storage, scanning, and queueing
    infrastructure used for tender uploads is reused — no separate
    code paths for security.
    """
    # --- Verify project ownership ---
    project_svc = ProjectService(session)
    try:
        await project_svc.get_or_raise(auth, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None

    # --- Read file data ---
    data = await file.read()
    if not data:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="oem_document.upload_rejected",
            entity_type="project",
            entity_id=project_id,
            project_id=project_id,
            metadata={"reason": "empty file", "filename": file.filename},
        )
        await session.commit()
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    filename = file.filename or "unnamed"
    # Sanitize: strip path traversal components (../../etc/passwd.pdf → passwd.pdf)
    filename = re.sub(r"^.*[/\\]", "", filename)
    filename = filename.replace("..", "")

    # --- Validate ---
    validator = ValidationService()
    result: ValidationResult = validator.validate(filename, file.content_type, data)
    if not result.valid:
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="oem_document.upload_rejected",
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
            action="oem_document.upload_rejected",
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
    bytes_reused: bool = existing_stored is not None

    # --- Validate document_type ---
    try:
        oem_doc_type = OemDocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown document_type: {document_type}. "
            f"Valid types: {[e.value for e in OemDocumentType]}",
        ) from None

    # ------------------------------------------------------------------
    # Branch: determine stored object
    # ------------------------------------------------------------------

    if existing_stored is not None:
        stored_obj = existing_stored
        storage_key = stored_obj.storage_key
    else:
        # First upload of these bytes — store in object storage.
        # Key format: oem/{org_id}/{project_id}/{object_uuid}{ext}
        # (mirrors build_key but with an "oem" namespace prefix so OEM
        # and tender keys never collide).
        ext = Path(filename).suffix.lower()
        storage_key = (
            f"oem/{auth.organization_id}/{project_id}"
            f"/{uuid.uuid4()}{ext}"
        )
        object_info = await storage.put(
            storage_key,
            data,
            result.detected_content_type or "application/octet-stream",
        )
        stored_obj = StoredObject(
            organization_id=auth.organization_id,
            project_id=project_id,
            document_id=None,
            storage_key=storage_key,
            filename=filename,
            content_type=object_info.content_type,
            content_length=object_info.content_length,
            checksum_sha256=object_info.checksum_sha256,
            etag=object_info.etag,
        )
        session.add(stored_obj)
        await session.flush()

    # --- Create or reuse OemDocument ---
    existing_doc_result = await session.execute(
        select(OemDocument).where(
            and_(
                OemDocument.project_id == project_id,
                OemDocument.display_name == filename,
            )
        )
    )
    existing_doc = existing_doc_result.scalar_one_or_none()

    if existing_doc is not None:
        doc_id = existing_doc.id
        # Update vendor/product metadata if provided (idempotent).
        if vendor_name:
            existing_doc.vendor_name = vendor_name
        if product_name:
            existing_doc.product_name = product_name
        if product_sku:
            existing_doc.product_sku = product_sku
    else:
        oem_doc = OemDocument(
            project_id=project_id,
            display_name=filename,
            document_type=oem_doc_type,
            vendor_name=vendor_name,
            product_name=product_name,
            product_sku=product_sku,
        )
        session.add(oem_doc)
        await session.flush()
        doc_id = oem_doc.id

    # --- Compute next version number ---
    max_result = await session.execute(
        select(func.max(OemDocumentVersion.version_number)).where(
            OemDocumentVersion.document_id == doc_id
        )
    )
    next_version = (max_result.scalar_one() or 0) + 1

    # --- Create immutable OemDocumentVersion ---
    oem_version = OemDocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_number=next_version,
        stored_object_id=stored_obj.id,
        sha256=stored_obj.checksum_sha256,
        mime_type=stored_obj.content_type,
        size_bytes=stored_obj.content_length,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    session.add(oem_version)
    await session.flush()

    # --- Audit ---
    audit = AuditService(session)
    await audit.log(
        organization_id=auth.organization_id,
        actor_id=auth.actor_id,
        action="oem_document.upload",
        entity_type="oem_document_version",
        entity_id=oem_version.id,
        project_id=project_id,
        metadata={
            "filename": filename,
            "storage_key": storage_key,
            "document_id": str(doc_id),
            "version_number": next_version,
            "bytes_reused": bytes_reused,
            "content_length": stored_obj.content_length,
            "checksum_sha256": checksum,
            "oem_document_type": oem_doc_type.value,
            "vendor_name": vendor_name,
            "product_name": product_name,
            "product_sku": product_sku,
        },
    )

    # Capture the processing status before enqueue (the route returns the
    # initial status to the client; the worker will advance it asynchronously).
    processing_status_before_enqueue = oem_version.processing_status.value

    await session.commit()
    await session.refresh(stored_obj)
    await session.refresh(oem_version)

    # --- Enqueue for background processing (CP18 pattern) ---
    doc_svc = DocumentService(session)
    run_id = await doc_svc.enqueue_oem_processing(auth, doc_id, next_version)
    await queue.enqueue(
        DEFAULT_QUEUE,
        str(run_id),
        QueueMessage(
            document_version_id=str(oem_version.id),
            document_id=str(doc_id),
            organization_id=str(auth.organization_id),
            version_number=next_version,
            stage=ProcessingStage.PARSE.value,
            run_id=str(run_id),
            attempt=1,
        ),
    )
    await session.commit()

    return OemUploadResponse(
        stored_object_id=stored_obj.id,
        document_id=doc_id,
        version_number=next_version,
        storage_key=stored_obj.storage_key,
        filename=filename,
        content_type=stored_obj.content_type,
        content_length=stored_obj.content_length,
        checksum_sha256=stored_obj.checksum_sha256,
        processing_status=processing_status_before_enqueue,
        uploaded_at=stored_obj.created_at,
    )


@router.get(
    "",
    response_model=list[OemDocumentVersionResponse],
)
async def list_oem_documents(
    project_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[OemDocumentVersionResponse]:
    """List all OEM document versions for a project (tenant-scoped).

    Returns the latest version of each logical OEM document, joined with
    the parent document's display_name, type, and vendor/product metadata.
    """
    project_svc = ProjectService(session)
    try:
        await project_svc.get_or_raise(auth, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None

    # Subquery: latest version number per OEM document for this project.
    latest_subq = (
        select(
            OemDocumentVersion.document_id.label("doc_id"),
            func.max(OemDocumentVersion.version_number).label("max_v"),
        )
        .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
        .where(OemDocument.project_id == project_id)
        .group_by(OemDocumentVersion.document_id)
        .subquery()
    )

    stmt = (
        select(OemDocumentVersion, OemDocument)
        .join(
            OemDocument,
            OemDocumentVersion.document_id == OemDocument.id,
        )
        .join(
            latest_subq,
            and_(
                OemDocumentVersion.document_id == latest_subq.c.doc_id,
                OemDocumentVersion.version_number == latest_subq.c.max_v,
            ),
        )
        .where(OemDocument.project_id == project_id)
        .order_by(OemDocument.created_at.desc())
    )

    result = await session.execute(stmt)
    rows = result.all()
    return [
        OemDocumentVersionResponse(
            document_id=row.OemDocument.id,
            display_name=row.OemDocument.display_name,
            document_type=row.OemDocument.document_type.value,
            vendor_name=row.OemDocument.vendor_name,
            product_name=row.OemDocument.product_name,
            product_sku=row.OemDocument.product_sku,
            version_number=row.OemDocumentVersion.version_number,
            sha256=row.OemDocumentVersion.sha256,
            mime_type=row.OemDocumentVersion.mime_type,
            size_bytes=row.OemDocumentVersion.size_bytes,
            processing_status=row.OemDocumentVersion.processing_status.value,
            parser_name=row.OemDocumentVersion.parser_name,
            parser_version=row.OemDocumentVersion.parser_version,
            ocr_name=row.OemDocumentVersion.ocr_name,
            ocr_version=row.OemDocumentVersion.ocr_version,
            created_at=row.OemDocumentVersion.created_at,
        )
        for row in rows
    ]
