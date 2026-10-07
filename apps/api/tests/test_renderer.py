"""Tests for the page renderer adapters and rendered-page persistence (CP20).

Covers:
- PymupdfRendererAdapter renders real PDF pages to PNG (page count, order,
  PNG signature, DPI recorded, name/version).
- Fatal errors for encrypted PDFs and unsupported MIME types.
- FakeRendererAdapter deterministic output.
- DocumentService.store_rendered_pages persists image keys on
  DocumentPage with idempotent, org/project-scoped storage keys.
- Best-effort semantics: render failures are recorded per-page (warnings)
  and never abort the PARSE stage.
- Worker integration: JobProcessor renders pages when a renderer is wired.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    ProcessingStage,
    Project,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.document.service import (
    DocumentNotFoundError,
    DocumentService,
)
from tender_compliance_api.parser import FakeParserAdapter
from tender_compliance_api.parser.adapter import PageResult
from tender_compliance_api.queue import DEFAULT_QUEUE, QueuedJob
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.renderer import FakeRendererAdapter, PymupdfRendererAdapter
from tender_compliance_api.renderer.adapter import (
    RendererAdapter,
    RenderPageResult,
    RenderResult,
)
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import WORKER_ACTOR_ID, JobProcessor

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------


def _make_pdf(page_count: int = 2) -> bytes:
    """Create a multi-page blank PDF with pypdf (fits PyMuPDF rendering)."""
    buf = io.BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=792)
    writer.write(buf)
    return buf.getvalue()


def _make_encrypted_pdf() -> bytes:
    """Create a password-protected PDF (should yield a fatal render error)."""
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=792)
    writer.encrypt("secret")
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Renderer adapter unit tests
# ---------------------------------------------------------------------------


class TestPymupdfRendererAdapter:
    def test_name_and_version(self):
        r = PymupdfRendererAdapter()
        assert r.name == "pymupdf"
        assert r.version != "unknown"

    def test_render_dpi_recorded(self):
        assert PymupdfRendererAdapter(dpi=200).render_dpi == 200

    def test_render_multi_page_preserves_order_and_signature(self):
        r = PymupdfRendererAdapter(dpi=150)
        result = asyncio.run(r.render(_make_pdf(page_count=3), "application/pdf"))

        assert result.fatal_error is None
        assert result.page_count == 3
        assert len(result.pages) == 3
        assert [p.page_number for p in result.pages] == [1, 2, 3]
        assert result.render_dpi == 150
        for p in result.pages:
            assert p.image_bytes[:8] == PNG_SIGNATURE
            assert len(p.image_bytes) > 64
            assert p.content_type == "image/png"
            assert p.error is None

    def test_render_single_page(self):
        r = PymupdfRendererAdapter()
        result = asyncio.run(r.render(_make_pdf(page_count=1), "application/pdf"))
        assert result.page_count == 1
        assert result.pages[0].page_number == 1

    def test_encrypted_pdf_is_fatal_not_silently_processed(self):
        r = PymupdfRendererAdapter()
        result = asyncio.run(r.render(_make_encrypted_pdf(), "application/pdf"))
        assert result.fatal_error is not None
        assert "password-protected" in result.fatal_error
        assert result.pages == []

    def test_corrupt_bytes_is_fatal(self):
        r = PymupdfRendererAdapter()
        result = asyncio.run(r.render(b"not a pdf", "application/pdf"))
        assert result.fatal_error is not None
        assert result.pages == []

    def test_unsupported_mime_is_fatal(self):
        r = PymupdfRendererAdapter()
        result = asyncio.run(r.render(b"hello", "image/jpeg"))
        assert result.fatal_error is not None
        assert "unsupported MIME type" in result.fatal_error


class TestFakeRendererAdapter:
    def test_render_returns_page_count_pages(self):
        r = FakeRendererAdapter(dpi=150, page_count=2)
        result = asyncio.run(r.render(b"\x00" * 10, "application/pdf"))
        assert result.fatal_error is None
        assert result.page_count == 2
        assert [p.page_number for p in result.pages] == [1, 2]
        for p in result.pages:
            assert p.image_bytes[:8] == PNG_SIGNATURE
            assert p.content_type == "image/png"
            assert "fake render" in p.warnings[0]

    def test_render_is_deterministic(self):
        a = asyncio.run(FakeRendererAdapter(dpi=150, page_count=1)
                        .render(b"x", "application/pdf"))
        b = asyncio.run(FakeRendererAdapter(dpi=150, page_count=1)
                        .render(b"x", "application/pdf"))
        assert a.pages[0].image_bytes == b.pages[0].image_bytes

    def test_unsupported_mime(self):
        r = FakeRendererAdapter(page_count=1)
        result = asyncio.run(r.render(b"x", "application/xyz"))
        assert result.fatal_error is not None
        assert "unsupported MIME type" in result.fatal_error

    def test_adapter_is_subclass(self):
        assert issubclass(FakeRendererAdapter, RendererAdapter)
        assert issubclass(PymupdfRendererAdapter, RendererAdapter)


# ---------------------------------------------------------------------------
# Helpers: set up a document version with stored PDF bytes + pages
# ---------------------------------------------------------------------------


def _worker_auth(org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=WORKER_ACTOR_ID,
        organization_id=org_id,
        roles=frozenset({"worker"}),
    )


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


async def _create_org_project(session_cm) -> dict[str, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    async with session_cm() as session:
        session.add(Organization(id=org_id, name="CP20 Org"))
        session.add(User(
            id=user_id,
            auth_provider="dev",
            auth_provider_user_id=str(user_id),
        ))
        session.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
        session.add(Project(
            id=project_id,
            organization_id=org_id,
            name="CP20 Project",
            status="documents_processing",
        ))
        await session.commit()
    return {"org_id": org_id, "user_id": user_id, "project_id": project_id}


async def _create_version(
    session_cm, org_id: uuid.UUID, project_id: uuid.UUID,
    *, pdf_bytes: bytes | None = None, page_count: int = 1,
) -> dict:
    """Create org+project doc+version+stored-object + pre-seeded DocumentPage
    rows.  Returns IDs and the source storage_key / pdf_bytes."""
    if pdf_bytes is None:
        pdf_bytes = _make_pdf(page_count=page_count)

    storage_key = build_key(
        org_id=org_id, project_id=project_id, document_id=uuid.uuid4(), version=1,
    )
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()
    checksum = hashlib.sha256(pdf_bytes).hexdigest()

    async with session_cm() as session:
        session.add(StoredObject(
            id=stored_object_id, organization_id=org_id, project_id=project_id,
            storage_key=storage_key, filename="tender.pdf",
            content_type="application/pdf", content_length=len(pdf_bytes),
            checksum_sha256=checksum,
        ))
        doc = TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf")
        session.add(doc)
        await session.flush()
        version = DocumentVersion(
            id=version_id, document_id=doc_id, version_number=1,
            stored_object_id=stored_object_id, sha256=checksum,
            mime_type="application/pdf", size_bytes=len(pdf_bytes),
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        session.add(version)
        for n in range(1, page_count + 1):
            session.add(DocumentPage(
                document_version_id=version.id,
                page_number=n, extracted_text="", ocr_needed=0,
            ))
        await session.commit()
    return {
        "doc_id": doc_id, "version_id": version_id, "version_number": 1,
        "storage_key": storage_key, "pdf_bytes": pdf_bytes,
    }


def _seed_storage(ver: dict, storage: FakeStorageAdapter) -> None:
    storage._store[ver["storage_key"]] = ver["pdf_bytes"]
    storage._meta[ver["storage_key"]] = {
        "content_type": "application/pdf",
        "content_length": len(ver["pdf_bytes"]),
        "etag": "t",
        "stored_at": 0.0,
    }


def _make_job(ver: dict, org_id: uuid.UUID) -> QueuedJob:
    run_id = make_job_id(str(ver["version_id"]), ProcessingStage.PARSE.value)
    return QueuedJob(
        job_id=str(run_id),
        payload={
            "document_version_id": str(ver["version_id"]),
            "document_id": str(ver["doc_id"]),
            "organization_id": str(org_id),
            "version_number": ver["version_number"],
            "stage": "parse",
            "run_id": str(run_id),
            "attempt": 1,
        },
        attempt=1,
        queue=DEFAULT_QUEUE,
    )


# ---------------------------------------------------------------------------
# DocumentService.store_rendered_pages tests
# ---------------------------------------------------------------------------


class TestStoreRenderedPages:
    def test_sets_rendered_image_keys_on_pages(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=2)
            storage = FakeStorageAdapter()

            renderer = FakeRendererAdapter(dpi=150, page_count=2)
            render_result = await renderer.render(ver["pdf_bytes"], "application/pdf")

            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.store_rendered_pages(
                    _worker_auth(org_id), ver["doc_id"], ver["version_number"],
                    render_result, storage,
                )

            keys = {p.page_number: p.rendered_image_object_key for p in pages}
            assert keys[1] is not None and keys[2] is not None
            assert keys[1] != keys[2]
            # Every persisted key is retrievable from storage.
            for n in (1, 2):
                obj = await storage.get(keys[n])
                assert obj[:8] == PNG_SIGNATURE

        asyncio.run(_run())

    def test_keys_are_idempotent_under_re_render(self, session_cm) -> None:
        """Re-rendering writes the same deterministic key (no duplicates)."""

        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=1)
            storage = FakeStorageAdapter()
            renderer = FakeRendererAdapter(dpi=150, page_count=1)
            render_result = await renderer.render(ver["pdf_bytes"], "application/pdf")

            sf = _get_session_factory()
            key1 = None
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.store_rendered_pages(
                    _worker_auth(org_id), ver["doc_id"], ver["version_number"],
                    render_result, storage,
                )
                key1 = pages[0].rendered_image_object_key
                await session.commit()

            # Re-render with a fresh session.
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.store_rendered_pages(
                    _worker_auth(org_id), ver["doc_id"], ver["version_number"],
                    render_result, storage,
                )
                key2 = pages[0].rendered_image_object_key

            assert key1 is not None and key2 == key1
            # Same key → storage holds one image, not two.
            assert sum(1 for k in storage._store if k == key1) == 1

        asyncio.run(_run())

    def test_fatal_render_annotates_pages_without_images(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=1)
            storage = FakeStorageAdapter()

            fatal_result = RenderResult(
                renderer_name="pymupdf", renderer_version="0.0.0",
                render_dpi=150, page_count=0, pages=[],
                fatal_error="document is encrypted",
            )

            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.store_rendered_pages(
                    _worker_auth(org_id), ver["doc_id"], ver["version_number"],
                    fatal_result, storage,
                )

            assert all(p.rendered_image_object_key is None for p in pages)
            meta = pages[0].structural_metadata or {}
            assert any("rendering failed" in w for w in (meta.get("warnings") or []))
            assert len(storage._store) == 0

        asyncio.run(_run())

    def test_per_page_render_error_is_best_effort(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=2)
            storage = FakeStorageAdapter()

            result = RenderResult(
                renderer_name="fake", renderer_version="0.0.0",
                render_dpi=150, page_count=2, pages=[
                    RenderPageResult(
                        page_number=1, image_bytes=b"",
                        content_type="image/png", render_dpi=150,
                        warnings=[], error="page render failed: boom",
                    ),
                    RenderPageResult(
                        page_number=2, image_bytes=PNG_SIGNATURE + b"\x00",
                        content_type="image/png", render_dpi=150,
                        warnings=[], error=None,
                    ),
                ],
            )

            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.store_rendered_pages(
                    _worker_auth(org_id), ver["doc_id"], ver["version_number"],
                    result, storage,
                )

            by_num = {p.page_number: p for p in pages}
            assert by_num[1].rendered_image_object_key is None
            assert "Page preview rendering failed" in (
                (by_num[1].structural_metadata or {}).get("warnings", [])[-1]
            )
            assert "boom" not in str(by_num[1].structural_metadata)
            assert by_num[2].rendered_image_object_key is not None
            img = await storage.get(by_num[2].rendered_image_object_key)
            assert img[:8] == PNG_SIGNATURE

        asyncio.run(_run())

    def test_cross_tenant_denied(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            ver = await _create_version(
                session_cm, info["org_id"], info["project_id"], page_count=1
            )
            storage = FakeStorageAdapter()
            renderer = FakeRendererAdapter(dpi=150, page_count=1)
            render_result = await renderer.render(ver["pdf_bytes"], "application/pdf")

            sf = _get_session_factory()
            other_org = uuid.uuid4()
            async with sf() as session:
                svc = DocumentService(session)
                with pytest.raises(DocumentNotFoundError):
                    await svc.store_rendered_pages(
                        _worker_auth(other_org), ver["doc_id"],
                        ver["version_number"], render_result, storage,
                    )

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Worker integration: rendering wired into the PARSE stage
# ---------------------------------------------------------------------------


class TestWorkerRendering:
    def test_worker_persists_rendered_pages(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=1)
            storage = FakeStorageAdapter()
            _seed_storage(ver, storage)

            processor = JobProcessor(
                _get_session_factory(),
                parser=FakeParserAdapter(pages=[
                    PageResult(page_number=1, text="t", text_length=1,
                               ocr_needed=False, warnings=[], error=None),
                ]),
                renderer=FakeRendererAdapter(dpi=150, page_count=1),
                storage=storage,
            )
            await processor.process(_make_job(ver, org_id))

            sf = _get_session_factory()
            async with sf() as session:
                row = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == ver["version_id"]
                    )
                )
            page = row.scalar_one()
            assert page.rendered_image_object_key is not None
            img = await storage.get(page.rendered_image_object_key)
            assert img[:8] == PNG_SIGNATURE

        asyncio.run(_run())

    def test_worker_without_renderer_skips_rendering(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            ver = await _create_version(session_cm, org_id, project_id, page_count=1)
            storage = FakeStorageAdapter()
            _seed_storage(ver, storage)

            processor = JobProcessor(
                _get_session_factory(),
                parser=FakeParserAdapter(pages=[
                    PageResult(page_number=1, text="t", text_length=1,
                               ocr_needed=False, warnings=[], error=None),
                ]),
                # renderer deliberately omitted → None → no-op rendering.
                storage=storage,
            )
            await processor.process(_make_job(ver, org_id))

            sf = _get_session_factory()
            async with sf() as session:
                row = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == ver["version_id"]
                    )
                )
            page = row.scalar_one()
            assert page.rendered_image_object_key is None
            # Only the source PDF is in storage, no rendered images.
            assert len(storage._store) == 1

        asyncio.run(_run())
