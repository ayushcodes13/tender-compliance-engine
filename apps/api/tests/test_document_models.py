"""Tests for the TenderDocument and DocumentVersion models (CP14).

Covers:
- TenderDocument creation linked to a project.
- DocumentVersion creation with version_number 1.
- Later version creates a new row, old version stays queryable.
- Duplicate (document_id, version_number) violates unique constraint.
- Default processing_status is UPLOADED.
- Default document_type is TENDER.
- stored_object_id FK RESTRICT prevents deleting a referenced StoredObject.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    StoredObject,
    TenderDocument,
    TenderDocumentType,
    User,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_org_project(session) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a minimal org → user → membership → project chain."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session.add(Organization(id=org_id, name="Test Org"))
    session.add(
        User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id))
    )
    session.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
    project = Project(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Tender Project",
        status=ProjectStatus.DRAFT,
    )
    session.add(project)
    await session.flush()
    return org_id, project.id


async def _create_stored_object(session, org_id: uuid.UUID, project_id: uuid.UUID) -> uuid.UUID:
    """Create a StoredObject and return its id."""
    obj_id = uuid.uuid4()
    session.add(
        StoredObject(
            id=obj_id,
            organization_id=org_id,
            project_id=project_id,
            storage_key=f"{org_id}/{project_id}/{obj_id}.pdf",
            filename="tender.pdf",
            content_type="application/pdf",
            content_length=1024,
            checksum_sha256="a" * 64,
        )
    )
    await session.flush()
    return obj_id


async def _create_document(session, project_id: uuid.UUID) -> uuid.UUID:
    """Create a TenderDocument and return its id."""
    doc_id = uuid.uuid4()
    session.add(
        TenderDocument(
            id=doc_id,
            project_id=project_id,
            display_name="Tender Document",
        )
    )
    await session.flush()
    return doc_id


async def _create_version(
    session, doc_id: uuid.UUID, version_number: int,
    stored_obj_id: uuid.UUID, sha: str = "a" * 64,
    size: int = 1024,
) -> uuid.UUID:
    """Create a DocumentVersion and return its id."""
    v_id = uuid.uuid4()
    session.add(
        DocumentVersion(
            id=v_id,
            document_id=doc_id,
            version_number=version_number,
            stored_object_id=stored_obj_id,
            sha256=sha,
            mime_type="application/pdf",
            size_bytes=size,
        )
    )
    await session.flush()
    return v_id


# ---------------------------------------------------------------------------
# TenderDocument
# ---------------------------------------------------------------------------


def test_create_tender_document(session_cm) -> None:
    """A TenderDocument links to a project and gets sensible defaults."""

    async def _run() -> None:
        async with session_cm() as session:
            _, project_id = await _create_org_project(session)
            doc_id = await _create_document(session, project_id)
            await session.commit()

            result = await session.execute(
                select(TenderDocument).where(TenderDocument.id == doc_id)
            )
            doc = result.scalar_one()
            assert doc.project_id == project_id
            assert doc.display_name == "Tender Document"
            assert doc.document_type == TenderDocumentType.TENDER
            assert doc.created_at is not None

    asyncio.run(_run())


def test_tender_document_type_other(session_cm) -> None:
    """document_type can be set to a non-default value."""

    async def _run() -> None:
        async with session_cm() as session:
            _, project_id = await _create_org_project(session)
            doc = TenderDocument(
                project_id=project_id,
                display_name="Amendment #1",
                document_type=TenderDocumentType.AMENDMENT,
            )
            session.add(doc)
            await session.commit()

            result = await session.execute(
                select(TenderDocument).where(TenderDocument.id == doc.id)
            )
            loaded = result.scalar_one()
            assert loaded.document_type == TenderDocumentType.AMENDMENT

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# DocumentVersion
# ---------------------------------------------------------------------------


def test_create_document_version_v1(session_cm) -> None:
    """First DocumentVersion has processing_status UPLOADED by default."""

    async def _run() -> None:
        async with session_cm() as session:
            org_id, project_id = await _create_org_project(session)
            stored_id = await _create_stored_object(session, org_id, project_id)
            doc_id = await _create_document(session, project_id)

            v_id = await _create_version(session, doc_id, 1, stored_id)
            await session.commit()

            result = await session.execute(
                select(DocumentVersion).where(DocumentVersion.id == v_id)
            )
            loaded = result.scalar_one()
            assert loaded.version_number == 1
            assert loaded.processing_status == DocumentProcessingStatus.UPLOADED
            assert loaded.sha256 == "a" * 64
            assert loaded.mime_type == "application/pdf"
            assert loaded.size_bytes == 1024

    asyncio.run(_run())


def test_later_version_creates_new_row(session_cm) -> None:
    """Creating v2 does not modify v1 — old version stays queryable."""

    async def _run() -> None:
        async with session_cm() as session:
            org_id, project_id = await _create_org_project(session)
            stored_1 = await _create_stored_object(session, org_id, project_id)
            doc_id = await _create_document(session, project_id)

            v1_id = await _create_version(session, doc_id, 1, stored_1)

            stored_2 = await _create_stored_object(session, org_id, project_id)
            await _create_version(
                session, doc_id, 2, stored_2, sha="b" * 64, size=2048
            )
            await session.commit()

            result = await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc_id)
                .order_by(DocumentVersion.version_number)
            )
            versions = result.scalars().all()
            assert len(versions) == 2
            assert versions[0].sha256 == "a" * 64
            assert versions[1].sha256 == "b" * 64
            assert versions[0].size_bytes == 1024
            assert versions[1].size_bytes == 2048

            # v1 should still be queryable by its own id
            v1_result = await session.execute(
                select(DocumentVersion).where(DocumentVersion.id == v1_id)
            )
            assert v1_result.scalar_one().version_number == 1

    asyncio.run(_run())


def test_duplicate_version_number_violates_unique(session_cm) -> None:
    """Two rows with the same (document_id, version_number) are rejected."""

    async def _run() -> None:
        async with session_cm() as session:
            org_id, project_id = await _create_org_project(session)
            stored_1 = await _create_stored_object(session, org_id, project_id)
            stored_2 = await _create_stored_object(session, org_id, project_id)
            doc_id = await _create_document(session, project_id)

            await _create_version(
                session, doc_id, 1, stored_1, sha="1" * 64
            )
            with pytest.raises(IntegrityError):
                await _create_version(
                    session, doc_id, 1, stored_2, sha="2" * 64
                )

    asyncio.run(_run())


def test_stored_object_fkey_is_restrict() -> None:
    """DocumentVersion.stored_object_id FK uses ON DELETE RESTRICT.

    This prevents a StoredObject backing an existing version from being
    deleted while the version still references it.  We verify the
    constraint at the model-definition level rather than relying on
    SQLite's connection-scoped ``PRAGMA foreign_keys`` (unreliable under
    a pooled async engine).
    """
    fk = next(
        fk for fk in DocumentVersion.__table__.foreign_keys
        if fk.column.table.name == "stored_objects"
    )
    assert fk.ondelete == "RESTRICT"

    # The document_id FK uses CASCADE — deleting a document removes its
    # versions, which is the intended lifecycle.
    doc_fk = next(
        fk for fk in DocumentVersion.__table__.foreign_keys
        if fk.column.table.name == "tender_documents"
    )
    assert doc_fk.ondelete == "CASCADE"
