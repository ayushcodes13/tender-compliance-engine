"""Tests for the PDF parser adapter (CP19).

Covers:
- Digital fixtures return correct page counts, order, and text.
- Malformed/partial PDFs produce explicit failure information.
- Encrypted PDFs produce a fatal_error.
- Scanned/raster pages (no text) are flagged ``ocr_needed=True``.
- FakeParserAdapter returns predetermined results.
- Worker integration: DocumentPage rows stored from real pypdf output.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import uuid

from fastapi.testclient import TestClient  # noqa: F401 — for app import
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from sqlalchemy import select

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
from tender_compliance_api.main import app  # noqa: F401
from tender_compliance_api.parser import FakeParserAdapter, PypdfParserAdapter
from tender_compliance_api.parser.adapter import PageResult
from tender_compliance_api.queue import DEFAULT_QUEUE, QueuedJob
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import JobProcessor

# ---------------------------------------------------------------------------
# Test fixtures: PDF builders
# ---------------------------------------------------------------------------


def _make_text_pdf(pages: list[str]) -> bytes:
    """Create a multi-page PDF where each page has the given text."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=200, height=792)
        content = DecodedStreamObject()
        content.set_data(
            f"BT /F1 12 Tf 36 700 Td ({text}) Tj ET".encode()
        )
        resources = DictionaryObject()
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        font_dict = DictionaryObject({NameObject("/F1"): font})
        resources[NameObject("/Font")] = font_dict
        resources[NameObject("/ProcSet")] = ArrayObject(
            [NameObject("/PDF"), NameObject("/Text")]
        )
        page[NameObject("/Contents")] = content
        page[NameObject("/Resources")] = resources
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_blank_pdf(num_pages: int) -> bytes:
    """Create a PDF with blank pages (no text)."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_protected_pdf(password: str = "secret") -> bytes:
    """Create a password-protected (encrypted) PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=792)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _parse(parser: PypdfParserAdapter, data: bytes, mime: str):
    """Helper to call the async parse method."""
    return await parser.parse(data, mime)


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_worker.py — no shared test package)
# ---------------------------------------------------------------------------


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


async def _make_version(
    session_cm, pdf_bytes: bytes, status: DocumentProcessingStatus
) -> dict:
    """Create org + project + document + version + stored object."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
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
        session.add(Organization(id=org_id, name="Test Org"))
        session.add(
            User(
                id=user_id,
                auth_provider="dev",
                auth_provider_user_id=str(user_id),
            )
        )
        session.add(
            Membership(organization_id=org_id, user_id=user_id, role="owner")
        )
        session.add(
            Project(
                id=project_id,
                organization_id=org_id,
                name="Test Project",
                status="documents_processing",
            )
        )
        stored = StoredObject(
            id=stored_object_id,
            organization_id=org_id,
            project_id=project_id,
            storage_key=storage_key,
            filename="tender.pdf",
            content_type="application/pdf",
            content_length=len(pdf_bytes),
            checksum_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        )
        session.add(stored)

        doc = TenderDocument(
            id=doc_id,
            project_id=project_id,
            display_name="tender.pdf",
        )
        session.add(doc)
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            processing_status=status,
        )
        session.add(version)
        await session.commit()
    return {
        "org_id": org_id,
        "user_id": user_id,
        "project_id": project_id,
        "doc_id": doc_id,
        "version_id": version_id,
        "version_number": 1,
        "stored_object_id": stored_object_id,
        "storage_key": storage_key,
        "pdf_bytes": pdf_bytes,
    }


def _storage_with_key(storage_key: str, data: bytes) -> FakeStorageAdapter:
    """Create a FakeStorageAdapter pre-populated with ``data`` at ``storage_key``."""
    storage = FakeStorageAdapter()
    storage._store[storage_key] = data
    storage._meta[storage_key] = {
        "content_type": "application/pdf",
        "content_length": len(data),
        "etag": "test-etag",
        "stored_at": time.time(),
    }
    return storage


def _make_job(version_id: uuid.UUID, org_id: uuid.UUID, run_id: uuid.UUID) -> QueuedJob:
    return QueuedJob(
        job_id=str(run_id),
        payload={
            "document_version_id": str(version_id),
            "document_id": str(uuid.uuid4()),
            "organization_id": str(org_id),
            "version_number": 1,
            "stage": "parse",
            "run_id": str(run_id),
            "attempt": 1,
        },
        attempt=1,
        queue=DEFAULT_QUEUE,
    )


# ---------------------------------------------------------------------------
# PypdfParserAdapter unit tests
# ---------------------------------------------------------------------------


class TestPypdfParserAdapter:
    """Unit tests for the pypdf-based parser."""

    def test_multi_page_text_pdf(self) -> None:
        """Multi-page digital PDF returns correct page count, order, text."""
        pdf_bytes = _make_text_pdf(
            ["Hello Page 1", "Hello Page 2", "Hello Page 3"]
        )
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert result.page_count == 3
        assert len(result.pages) == 3
        assert result.fatal_error is None
        for i, page_result in enumerate(result.pages):
            assert page_result.page_number == i + 1
            assert page_result.text == f"Hello Page {i + 1}"
            assert page_result.text_length == len(f"Hello Page {i + 1}")
            assert page_result.ocr_needed is False
            assert page_result.error is None

    def test_single_page_text_pdf(self) -> None:
        """Single-page text PDF returns correct single page."""
        pdf_bytes = _make_text_pdf(["Single page content"])
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert result.page_count == 1
        assert result.pages[0].text == "Single page content"
        assert result.pages[0].ocr_needed is False

    def test_suspicious_native_hyphen_spacing_requires_visual_verification(self) -> None:
        pdf_bytes = _make_text_pdf(["Chuck model III -V for vacuum table"])
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        page = result.pages[0]
        assert page.ocr_needed is False
        assert page.visual_verification_required is True
        assert "III -V" in page.text
        assert any("suspicious whitespace around a hyphen" in w for w in page.warnings)

    def test_blank_pages_flag_ocr_needed(self) -> None:
        """Blank pages (no text layer) are flagged as needing OCR."""
        pdf_bytes = _make_blank_pdf(2)
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert result.page_count == 2
        for page_result in result.pages:
            assert page_result.text == ""
            assert page_result.text_length == 0
            assert page_result.ocr_needed is True
            assert len(page_result.warnings) > 0
            assert "no text layer" in page_result.warnings[0]

    def test_encrypted_pdf_produces_fatal_error(self) -> None:
        """Password-protected PDFs produce a fatal_error, not an exception."""
        pdf_bytes = _make_protected_pdf()
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert result.fatal_error is not None
        assert "password" in result.fatal_error.lower()
        assert result.page_count == 0
        assert len(result.pages) == 0

    def test_malformed_pdf_produces_fatal_error(self) -> None:
        """Corrupted PDF bytes produce a fatal_error, not an exception."""
        pdf_bytes = b"not a real pdf"
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert result.fatal_error is not None
        assert result.page_count == 0
        assert len(result.pages) == 0

    def test_unsupported_mime_type(self) -> None:
        """Non-PDF MIME types produce a fatal_error."""
        result = asyncio.run(
            _parse(PypdfParserAdapter(), b"hello", "text/plain")
        )

        assert result.fatal_error is not None
        assert "unsupported" in result.fatal_error.lower()
        assert result.page_count == 0

    def test_parser_name_and_version(self) -> None:
        """Parser reports its name and version."""
        parser = PypdfParserAdapter()
        assert parser.name == "pypdf"
        assert parser.version != ""
        assert parser.version != "unknown"

    def test_page_order_preserved(self) -> None:
        """Pages are returned in correct 1-indexed order."""
        pdf_bytes = _make_text_pdf(
            ["first page text", "second page text", "third page text"]
        )
        result = asyncio.run(
            _parse(PypdfParserAdapter(), pdf_bytes, "application/pdf")
        )

        assert [p.page_number for p in result.pages] == [1, 2, 3]
        assert result.pages[0].text == "first page text"
        assert result.pages[1].text == "second page text"
        assert result.pages[2].text == "third page text"


# ---------------------------------------------------------------------------
# FakeParserAdapter unit tests
# ---------------------------------------------------------------------------


class TestFakeParserAdapter:
    """Unit tests for the fake parser used in worker tests."""

    def test_returns_predetermined_pages(self) -> None:
        """FakeParserAdapter returns the pages configured at construction."""

        async def _run():
            pages = [
                PageResult(
                    page_number=1,
                    text="fake text one",
                    text_length=13,
                    ocr_needed=False,
                    warnings=[],
                    error=None,
                ),
                PageResult(
                    page_number=2,
                    text="fake text two",
                    text_length=13,
                    ocr_needed=True,
                    warnings=["needs ocr"],
                    error=None,
                ),
            ]
            parser = FakeParserAdapter(pages=pages)
            result = await parser.parse(b"dummy", "application/pdf")

            assert result.parser_name == "fake"
            assert result.parser_version == "test"
            assert result.page_count == 2
            assert result.pages[0].page_number == 1
            assert result.pages[1].page_number == 2
            assert result.pages[0].text == "fake text one"
            assert result.pages[1].ocr_needed is True
            assert result.fatal_error is None
            assert parser.parse_calls == [(b"dummy", "application/pdf")]

        asyncio.run(_run())

    def test_default_single_page(self) -> None:
        """Without configured pages, returns a single page with input text."""

        async def _run():
            parser = FakeParserAdapter()
            result = await parser.parse(b"hello world", "application/pdf")

            assert result.page_count == 1
            assert result.pages[0].page_number == 1
            assert result.pages[0].text == "hello world"
            assert result.pages[0].ocr_needed is False

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Integration: worker stores DocumentPage rows from parser output
# ---------------------------------------------------------------------------


class TestParserWorkerIntegration:
    """Verify the worker stores DocumentPage rows via real pypdf parsing."""

    def test_worker_stores_pages_for_text_pdf(self, session_cm) -> None:
        """Text PDF → pages stored with extracted text → version PARSED."""

        async def _run():
            pdf_bytes = _make_text_pdf(["Page with text content"])
            info = await _make_version(
                session_cm, pdf_bytes, DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            storage = _storage_with_key(info["storage_key"], info["pdf_bytes"])

            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = _make_job(info["version_id"], info["org_id"], run_id)

            processor = JobProcessor(
                sf,
                parser=PypdfParserAdapter(),
                storage=storage,
            )
            await processor.process(job)

            async with sf() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == info["version_id"]
                    )
                )
                updated = result.scalar_one()
                assert updated.processing_status == DocumentProcessingStatus.PARSED
                assert updated.parser_name == "pypdf"
                assert updated.parser_version is not None

                page_result = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == info["version_id"]
                    )
                )
                pages = list(page_result.scalars().all())
                assert len(pages) == 1
                assert pages[0].page_number == 1
                assert pages[0].extracted_text == "Page with text content"
                assert pages[0].ocr_needed == 0

        asyncio.run(_run())

    def test_worker_marks_scanned_pdf_as_partial(self, session_cm) -> None:
        """Blank PDF → pages need OCR → version PARTIAL (not PARSED)."""

        async def _run():
            pdf_bytes = _make_blank_pdf(2)
            info = await _make_version(
                session_cm, pdf_bytes, DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            storage = _storage_with_key(info["storage_key"], info["pdf_bytes"])

            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = _make_job(info["version_id"], info["org_id"], run_id)

            processor = JobProcessor(
                sf,
                parser=PypdfParserAdapter(),
                storage=storage,
            )
            await processor.process(job)

            async with sf() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == info["version_id"]
                    )
                )
                updated = result.scalar_one()
                # All stages completed, but pages need OCR → PARTIAL
                assert updated.processing_status == DocumentProcessingStatus.PARTIAL

                page_result = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == info["version_id"]
                    )
                )
                pages = list(page_result.scalars().all())
                assert len(pages) == 2
                assert pages[0].ocr_needed == 1
                assert pages[1].ocr_needed == 1

        asyncio.run(_run())

    def test_worker_handles_malformed_pdf(self, session_cm) -> None:
        """Malformed PDF → PARSE stage fails → version in retryable state."""

        async def _run():
            pdf_bytes = b"not a real pdf"
            info = await _make_version(
                session_cm, pdf_bytes, DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            storage = _storage_with_key(info["storage_key"], info["pdf_bytes"])

            run_id = make_job_id(
                str(info["version_id"]), ProcessingStage.PARSE.value
            )
            job = _make_job(info["version_id"], info["org_id"], run_id)

            processor = JobProcessor(
                sf,
                parser=PypdfParserAdapter(),
                storage=storage,
            )
            await processor.process(job)

            async with sf() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == info["version_id"]
                    )
                )
                updated = result.scalar_one()
                # PARSE failed → version is in a retryable state (QUEUED),
                # meaning the worker can retry the job.
                assert updated.processing_status == DocumentProcessingStatus.QUEUED
                assert updated.parser_name == "pypdf"

                # No pages should have been stored
                page_result = await session.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_version_id == info["version_id"]
                    )
                )
                pages = list(page_result.scalars().all())
                assert len(pages) == 0

                # PARSE run should be FAILED
                run_result = await session.execute(
                    select(ProcessingRun).where(
                        ProcessingRun.document_version_id == info["version_id"],
                        ProcessingRun.stage == ProcessingStage.PARSE,
                    )
                )
                runs = list(run_result.scalars().all())
                assert len(runs) == 1
                assert runs[0].status == RunStatus.FAILED
                assert runs[0].error_type == "ParseError"

        asyncio.run(_run())
