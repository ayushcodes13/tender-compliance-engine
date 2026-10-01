"""Tests for OCR (CP21): adapter port, Tesseract/Fake adapters,
DocumentService.apply_ocr, and the worker OCR stage.

Coverage:
- FakeOcrAdapter deterministic recognition incl. the adversarial
  character set (≥, ≤, µ, decimals, units, common confusions).
- TesseractOcrAdapter: name/version; real OCR skipped unless the
  ``tesseract`` binary is present.
- DocumentService.apply_ocr: scan pages filled, native pages skipped,
  missing rendered image skipped, OCR failure keeps ocr_needed, mixed
  documents, idempotent re-OCR, cross-tenant denial.
- Worker: scan fixture + OCR adapter -> PARSED with text filled; scan
  fixture without an OCR adapter -> OCR no-op -> PARTIAL.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid

import pytest
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    RunStatus,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.document import DocumentService
from tender_compliance_api.document.service import DocumentNotFoundError
from tender_compliance_api.ocr import (
    FakeOcrAdapter,
    OcrAdapter,
    OcrResult,
    OcrWord,
    TesseractOcrAdapter,
)
from tender_compliance_api.parser import FakeParserAdapter
from tender_compliance_api.parser.adapter import PageResult
from tender_compliance_api.queue import DEFAULT_QUEUE, QueuedJob
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.renderer import FakeRendererAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import WORKER_ACTOR_ID, JobProcessor

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256))


# ---------------------------------------------------------------------------
# Helpers
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
        session.add(Organization(id=org_id, name="CP21 Org"))
        session.add(
            User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id))
        )
        session.add(
            Membership(organization_id=org_id, user_id=user_id, role="owner")
        )
        session.add(
            Project(
                id=project_id,
                organization_id=org_id,
                name="CP21 Project",
                status="documents_processing",
            )
        )
        await session.commit()
    return {"org_id": org_id, "user_id": user_id, "project_id": project_id}


async def _create_version_with_pages(
    session_cm,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    storage: FakeStorageAdapter,
    *,
    page_count: int = 1,
    ocr_needed: bool = False,
    rendered: bool = True,
) -> dict:
    """Create a version with pre-seeded DocumentPage rows.

    Pages are created with the requested ``ocr_needed`` flag; when
    ``rendered`` is true each page's ``rendered_image_object_key`` is set
    and a placeholder image is seeded in *storage* so apply_ocr can
    retrieve it.
    """
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()
    storage_key = build_key(
        org_id=org_id,
        project_id=project_id,
        document_id=doc_id,
        version=1,
    )
    async with session_cm() as session:
        session.add(
            StoredObject(
                id=stored_object_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=storage_key,
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=1024,
                checksum_sha256="abc123",
            )
        )
        session.add(TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf"))
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256="abc123",
            mime_type="application/pdf",
            size_bytes=1024,
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        session.add(version)
        await session.flush()
        for n in range(1, page_count + 1):
            key = f"render:{version_id}:{n}" if rendered else None
            session.add(
                DocumentPage(
                    document_version_id=version.id,
                    page_number=n,
                    extracted_text=None if ocr_needed else "native text",
                    ocr_needed=1 if ocr_needed else 0,
                    rendered_image_object_key=key,
                )
            )
            if key:
                storage._store[key] = PNG_BYTES
                storage._meta[key] = {
                    "content_type": "image/png",
                    "content_length": len(PNG_BYTES),
                    "etag": "t",
                    "stored_at": 0.0,
                }
        await session.commit()
    return {
        "doc_id": doc_id,
        "version_id": version_id,
        "version_number": 1,
        "storage_key": storage_key,
    }


async def _create_version_for_worker(
    session_cm, org_id: uuid.UUID, project_id: uuid.UUID, storage: FakeStorageAdapter
) -> dict:
    """Create org+doc+version+stored-object for an end-to-end worker test.

    Unlike :func:`_create_version_with_pages`, no DocumentPage rows are
    pre-created — the worker's PARSE stage will create them from the
    injected FakeParserAdapter.
    """
    info = await _create_org_project(session_cm)
    org_id = info["org_id"]
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()
    storage_key = build_key(
        org_id=org_id,
        project_id=project_id,
        document_id=doc_id,
        version=1,
    )
    async with session_cm() as session:
        session.add(
            StoredObject(
                id=stored_object_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=storage_key,
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=1024,
                checksum_sha256="abc123",
            )
        )
        session.add(TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf"))
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256="abc123",
            mime_type="application/pdf",
            size_bytes=1024,
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        session.add(version)
        await session.commit()
    storage._store[storage_key] = b"fake-pdf-bytes"
    storage._meta[storage_key] = {
        "content_type": "application/pdf",
        "content_length": len(b"fake-pdf-bytes"),
        "etag": "t",
        "stored_at": 0.0,
    }
    return {
        "doc_id": doc_id,
        "version_id": version_id,
        "version_number": 1,
        "storage_key": storage_key,
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
# Adapter unit tests
# ---------------------------------------------------------------------------


class TestFakeOcrAdapter:
    def test_adheres_to_port(self) -> None:
        assert issubclass(FakeOcrAdapter, OcrAdapter)

    def test_returns_configured_text_and_confidence(self) -> None:
        a = FakeOcrAdapter(text="hello", confidence=90.0)
        result = asyncio.run(a.ocr(b"\x89PNG" + b"\x00" * 10))
        assert isinstance(result, OcrResult)
        assert result.text == "hello"
        assert result.confidence == 90.0
        assert result.words == []

    def test_special_characters(self) -> None:
        """OCR must preserve ≥, ≤, µ, decimals, units, and confusions."""
        text = "10 ≥ 9.5 ≤ 12.3 µm 3.14 mm 1,000 5.0×2"
        a = FakeOcrAdapter(text=text, confidence=42.0)
        result = asyncio.run(a.ocr(b"\x89PNG" + b"\x00" * 10))
        assert result.text == text
        assert result.confidence == 42.0

    def test_confidence_none_preserved(self) -> None:
        a = FakeOcrAdapter(text="x", confidence=None)
        result = asyncio.run(a.ocr(b"x"))
        assert result.confidence is None

    def test_words_and_geometry(self) -> None:
        words = [
            OcrWord(text="a", confidence=99.0, bbox=(1, 2, 3, 4)),
            OcrWord(text="b", confidence=None, bbox=(5, 6, 7, 8)),
        ]
        a = FakeOcrAdapter(text="ab", confidence=97.0, words=words)
        result = asyncio.run(a.ocr(b"\x89PNG" + b"\x00" * 10))
        assert result.words == words


class TestTesseractOcrAdapter:
    def test_name_and_version_are_strings(self) -> None:
        a = TesseractOcrAdapter()
        assert a.name == "tesseract"
        assert isinstance(a.version, str)

    def test_real_ocr_or_skip(self) -> None:
        """If the tesseract binary is present, OCR a simple image; else skip."""
        if shutil.which("tesseract") is None:
            pytest.skip("tesseract binary not installed")
        # Build an image of a few words using pymupdf so we don't depend on
        # a font rasterizer in the test itself.
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((10, 50), "OCR test 123")
        pix = page.get_pixmap(dpi=150)
        png = pix.tobytes("png")
        doc.close()

        a = TesseractOcrAdapter()
        result = asyncio.run(a.ocr(png))
        assert isinstance(result, OcrResult)
        assert "123" in result.text
        # pytesseract reports per-word confidence; an all-present run gives a
        # finite mean confidence.
        assert result.confidence is None or result.confidence >= 0.0


# ---------------------------------------------------------------------------
# DocumentService.apply_ocr tests
# ---------------------------------------------------------------------------


class TestApplyOcr:
    def test_scan_pages_are_filled(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=2, ocr_needed=True, rendered=True,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="scanned text", confidence=88.0),
                    storage,
                )

                assert len(pages) == 2
                for p in pages:
                    assert p.extracted_text == "scanned text"
                    assert p.ocr_confidence == 88.0
                    assert p.ocr_needed == 0

                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.ocr_name == "fake"
                assert v.ocr_version == "0.0.0-test"

        asyncio.run(_run())

    def test_native_pages_are_skipped(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=False, rendered=True,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="ignored", confidence=90.0),
                    storage,
                )

            # No page needed OCR -> provider was never invoked.
            assert pages[0].extracted_text == "native text"
            assert pages[0].ocr_needed == 0
            assert pages[0].ocr_confidence is None

            async with sf() as session:
                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.ocr_name is None
                assert v.ocr_version is None

        asyncio.run(_run())

    def test_missing_rendered_image_keeps_ocr_needed(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=True, rendered=False,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="should not be used", confidence=90.0),
                    storage,
                )

            p = pages[0]
            assert p.ocr_needed == 1
            assert p.extracted_text is None
            # Provider never invoked -> no provider recorded.
            async with sf() as session:
                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.ocr_name is None

        asyncio.run(_run())

    def test_ocr_failure_leaves_page_flagged(self, session_cm) -> None:
        class _BoomOcr(OcrAdapter):
            @property
            def name(self) -> str:
                return "boom"

            @property
            def version(self) -> str:
                return "1"

            async def ocr(self, image_bytes: bytes, mime_type: str = "image/png") -> OcrResult:
                raise RuntimeError("tesseract on fire")

        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=True, rendered=True,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1, _BoomOcr(), storage,
                )

                p = pages[0]
                assert p.ocr_needed == 1
                assert p.extracted_text is None
                # The provider was attempted, so its identity is recorded.
                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.ocr_name == "boom"

        asyncio.run(_run())

    def test_empty_text_keeps_page_flagged(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=True, rendered=True,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="", confidence=10.0), storage,
                )

            p = pages[0]
            assert p.ocr_needed == 1
            assert p.extracted_text is None
            assert p.ocr_confidence == 10.0

        asyncio.run(_run())

    def test_mixed_document(self, session_cm) -> None:
        """One native page + one scan page: only the scan page is OCR'd."""
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            doc_id = uuid.uuid4()
            version_id = uuid.uuid4()
            stored_object_id = uuid.uuid4()
            storage_key = build_key(
                org_id=org_id, project_id=project_id, document_id=doc_id, version=1,
            )
            scan_key = f"render:{version_id}:2"
            sf = _get_session_factory()
            async with sf() as session:
                session.add(
                    StoredObject(
                        id=stored_object_id, organization_id=org_id,
                        project_id=project_id, storage_key=storage_key,
                        filename="tender.pdf", content_type="application/pdf",
                        content_length=1024, checksum_sha256="abc123",
                    )
                )
                session.add(
                    TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf")
                )
                await session.flush()
                version = DocumentVersion(
                    id=version_id, document_id=doc_id, version_number=1,
                    stored_object_id=stored_object_id, sha256="abc123",
                    mime_type="application/pdf", size_bytes=1024,
                    processing_status=DocumentProcessingStatus.QUEUED,
                )
                session.add(version)
                await session.flush()
                # Page 1: native (no OCR needed). Page 2: scanned (needs OCR, has image).
                session.add(
                    DocumentPage(
                        document_version_id=version.id, page_number=1,
                        extracted_text="native text", ocr_needed=0,
                        rendered_image_object_key=None,
                    )
                )
                session.add(
                    DocumentPage(
                        document_version_id=version.id, page_number=2,
                        extracted_text=None, ocr_needed=1,
                        rendered_image_object_key=scan_key,
                    )
                )
                await session.commit()
            storage._store[scan_key] = PNG_BYTES
            storage._meta[scan_key] = {
                "content_type": "image/png", "content_length": len(PNG_BYTES),
                "etag": "t", "stored_at": 0.0,
            }

            async with sf() as session:
                svc = DocumentService(session)
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), doc_id, 1,
                    FakeOcrAdapter(text="scanned text", confidence=77.0), storage,
                )

            by_num = {p.page_number: p for p in pages}
            assert by_num[1].extracted_text == "native text"
            assert by_num[1].ocr_needed == 0
            assert by_num[2].extracted_text == "scanned text"
            assert by_num[2].ocr_needed == 0
            assert by_num[2].ocr_confidence == 77.0

        asyncio.run(_run())

    def test_idempotent_re_ocr(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=True, rendered=True,
            )
            sf = _get_session_factory()
            async with sf() as session:
                svc = DocumentService(session)
                await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="scanned text", confidence=88.0),
                    storage,
                )
                # Second pass: no pages need OCR anymore -> no-op.
                pages = await svc.apply_ocr(
                    _worker_auth(org_id), ver["doc_id"], 1,
                    FakeOcrAdapter(text="SHOULD NOT OVERWRITE", confidence=0.0),
                    storage,
                )
            assert pages[0].extracted_text == "scanned text"
            assert pages[0].ocr_needed == 0
            assert pages[0].ocr_confidence == 88.0

        asyncio.run(_run())

    def test_cross_tenant_denied(self, session_cm) -> None:
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_with_pages(
                session_cm, org_id, project_id, storage,
                page_count=1, ocr_needed=True, rendered=True,
            )
            sf = _get_session_factory()
            other_org = uuid.uuid4()
            async with sf() as session:
                svc = DocumentService(session)
                with pytest.raises(DocumentNotFoundError):
                    await svc.apply_ocr(
                        _worker_auth(other_org), ver["doc_id"], 1,
                        FakeOcrAdapter(text="x", confidence=90.0), storage,
                    )

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Worker OCR-stage integration tests
# ---------------------------------------------------------------------------


class TestWorkerOcr:
    def test_scan_fixture_ocr_to_parsed(self, session_cm) -> None:
        """Scan fixture + OCR adapter end-to-end -> PARSED with text filled."""
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_for_worker(session_cm, org_id, project_id, storage)

            parser = FakeParserAdapter(pages=[
                PageResult(
                    page_number=1, text="", text_length=0,
                    ocr_needed=True, warnings=["no native text"], error=None,
                ),
            ])
            renderer = FakeRendererAdapter(page_count=1)
            ocr = FakeOcrAdapter(text="scanned page text", confidence=91.5)
            processor = JobProcessor(
                _get_session_factory(),
                parser=parser, renderer=renderer, storage=storage, ocr=ocr,
            )
            await processor.process(_make_job(ver, org_id))

            sf = _get_session_factory()
            async with sf() as session:
                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.processing_status == DocumentProcessingStatus.PARSED
                assert v.parser_name == "fake"
                assert v.parser_version == "test"
                assert v.ocr_name == "fake"
                assert v.ocr_version == "0.0.0-test"

                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == v.id
                        )
                    )
                ).scalar_one()
                assert page.extracted_text == "scanned page text"
                assert page.ocr_needed == 0
                assert page.ocr_confidence == 91.5
                assert page.rendered_image_object_key is not None

                runs = (
                    await session.execute(
                        select(ProcessingRun).where(
                            ProcessingRun.document_version_id == v.id
                        )
                    )
                ).scalars().all()
                assert len(runs) == 4
                assert all(r.status == RunStatus.COMPLETED for r in runs)
                ocr_run = next(r for r in runs if r.stage == ProcessingStage.OCR)
                assert ocr_run.status == RunStatus.COMPLETED

        asyncio.run(_run())

    def test_scan_fixture_without_ocr_adapter_stays_partial(self, session_cm) -> None:
        """Scan fixture, no OCR adapter -> OCR stage no-op -> PARTIAL."""
        async def _run():
            info = await _create_org_project(session_cm)
            org_id, project_id = info["org_id"], info["project_id"]
            storage = FakeStorageAdapter()
            ver = await _create_version_for_worker(session_cm, org_id, project_id, storage)

            parser = FakeParserAdapter(pages=[
                PageResult(
                    page_number=1, text="", text_length=0,
                    ocr_needed=True, warnings=["no native text"], error=None,
                ),
            ])
            processor = JobProcessor(
                _get_session_factory(),
                parser=parser, storage=storage,
            )
            await processor.process(_make_job(ver, org_id))

            sf = _get_session_factory()
            async with sf() as session:
                v = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == ver["version_id"]
                        )
                    )
                ).scalar_one()
                assert v.processing_status == DocumentProcessingStatus.PARTIAL
                assert v.ocr_name is None

                page = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == v.id
                        )
                    )
                ).scalar_one()
                assert page.ocr_needed == 1
                assert page.extracted_text is None

                runs = (
                    await session.execute(
                        select(ProcessingRun).where(
                            ProcessingRun.document_version_id == v.id
                        )
                    )
                ).scalars().all()
                assert len(runs) == 4
                assert all(r.status == RunStatus.COMPLETED for r in runs)

        asyncio.run(_run())
