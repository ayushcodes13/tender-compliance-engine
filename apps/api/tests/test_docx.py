"""Tests for the DOCX parser and MIME-type dispatch (CP22).

Covers:
- :class:`DocxParserAdapter` extracts paragraphs, headings, and table
  cells in source order, with format-appropriate provenance (no
  fabricated page numbers; native text so ``ocr_needed=False``).
- Corrupt / unsupported-MIME inputs are fatal ParseResults, never raised.
- :class:`CompositeParserAdapter` dispatches to the right sub-adapter by
  MIME type and records a fatal error for unknown formats.
- End-to-end: a DOCX version processed through ``JobProcessor`` is routed
  to the DOCX adapter and the version records ``parser_name="python-docx"``
  (provenance is the *sub-parser* identity, not a generic "composite").
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import uuid

from docx import Document
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
from tender_compliance_api.parser import (
    CompositeParserAdapter,
    DocxParserAdapter,
    FakeParserAdapter,
    PypdfParserAdapter,
)
from tender_compliance_api.parser.adapter import PageResult
from tender_compliance_api.parser.docx import DOCX_MIME_TYPE
from tender_compliance_api.queue import DEFAULT_QUEUE, QueuedJob
from tender_compliance_api.queue.adapter import make_job_id
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import JobProcessor

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_docx() -> bytes:
    """Build a small, deterministic .docx with headings, paragraphs, a table."""
    buf = io.BytesIO()
    doc = Document()
    doc.add_heading("Tender Title", level=1)
    doc.add_paragraph(
        "The operating temperature shall be between 5 and 40 \u00b0C."
    )
    doc.add_paragraph("Accuracy of measurements shall be 0.1 mm.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Param"
    table.cell(0, 1).text = "Limit"
    doc.add_paragraph("Environmental ingress protection: IP65.")
    doc.save(buf)
    return buf.getvalue()


async def _create_docx_version(
    session_cm,
    status: DocumentProcessingStatus,
    *,
    docx_bytes: bytes | None = None,
) -> dict:
    """Create org/user/project/document/version/stored-object for a .docx."""
    if docx_bytes is None:
        docx_bytes = _make_docx()

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
        session.add(Organization(id=org_id, name="CP22 Org"))
        session.add(
            User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id))
        )
        session.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
        session.add(Project(id=project_id, organization_id=org_id, name="CP22 Project"))
        session.add(
            StoredObject(
                id=stored_object_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=storage_key,
                filename="tender.docx",
                content_type=DOCX_MIME_TYPE,
                content_length=len(docx_bytes),
                checksum_sha256=hashlib.sha256(docx_bytes).hexdigest(),
            )
        )
        session.add(
            TenderDocument(id=doc_id, project_id=project_id, display_name="tender.docx")
        )
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256=hashlib.sha256(docx_bytes).hexdigest(),
            mime_type=DOCX_MIME_TYPE,
            size_bytes=len(docx_bytes),
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
        "docx_bytes": docx_bytes,
    }


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


# ---------------------------------------------------------------------------
# DocxParserAdapter unit tests
# ---------------------------------------------------------------------------


class TestDocxParserAdapter:
    """Unit tests for the python-docx parser (CP22)."""

    def test_parse_preserves_paragraphs_and_table(self) -> None:
        adapter = DocxParserAdapter()
        result = asyncio.run(adapter.parse(_make_docx(), DOCX_MIME_TYPE))

        assert result.fatal_error is None
        assert result.parser_name == "python-docx"
        # Version is the installed python-docx package version (or "unknown").
        assert result.parser_version
        assert result.page_count == 1
        assert len(result.pages) == 1

        page = result.pages[0]
        assert page.page_number == 1
        assert page.ocr_needed is False
        assert page.error is None

        text = page.text
        # Heading + paragraphs preserved in source order.
        assert "Tender Title" in text
        assert "operating temperature" in text
        assert "0.1 mm" in text
        assert "IP65" in text
        # Table cells are surfaced.
        assert "Param" in text
        assert "Limit" in text

        # Provenance guardrail: a warning makes the single-segment limitation
        # explicit (no fabricated page numbers).
        assert any("no inherent page count" in w for w in page.warnings)

    def test_unsupported_mime_is_fatal(self) -> None:
        adapter = DocxParserAdapter()
        result = asyncio.run(adapter.parse(b"hello", "application/pdf"))
        assert result.fatal_error is not None
        assert "unsupported MIME type" in result.fatal_error
        assert result.pages == []
        assert result.page_count == 0
        # Sub-parser identity is still recorded even on the fatal path.
        assert result.parser_name == "python-docx"

    def test_corrupt_data_is_fatal_not_raised(self) -> None:
        adapter = DocxParserAdapter()
        result = asyncio.run(adapter.parse(b"not a real docx", DOCX_MIME_TYPE))
        assert result.fatal_error is not None
        assert "processing stage" in result.fatal_error.lower()
        assert "not a real docx" not in result.fatal_error
        assert result.pages == []

    def test_empty_document_is_single_empty_page(self) -> None:
        buf = io.BytesIO()
        Document().save(buf)
        adapter = DocxParserAdapter()
        result = asyncio.run(adapter.parse(buf.getvalue(), DOCX_MIME_TYPE))
        assert result.fatal_error is None
        assert result.page_count == 1
        assert result.pages[0].text == ""
        assert result.pages[0].ocr_needed is False
        assert any("no inherent page count" in w for w in result.pages[0].warnings)


# ---------------------------------------------------------------------------
# CompositeParserAdapter dispatch tests
# ---------------------------------------------------------------------------


class TestCompositeParserAdapter:
    """Unit tests for MIME-type dispatch (CP22)."""

    def _fakes(self) -> tuple[FakeParserAdapter, FakeParserAdapter]:
        pdf = FakeParserAdapter(
            pages=[
                PageResult(
                    page_number=1, text="pdf-body", text_length=7,
                    ocr_needed=False, warnings=[], error=None,
                )
            ]
        )
        docx = FakeParserAdapter(
            pages=[
                PageResult(
                    page_number=1, text="docx-body", text_length=8,
                    ocr_needed=False, warnings=[], error=None,
                )
            ]
        )
        return pdf, docx

    def test_dispatches_pdf_to_pdf_adapter(self) -> None:
        pdf_adapter, docx_adapter = self._fakes()
        comp = CompositeParserAdapter(
            {"application/pdf": pdf_adapter, DOCX_MIME_TYPE: docx_adapter}
        )

        result = asyncio.run(comp.parse(b"%pdf-1.4", "application/pdf"))

        assert result.fatal_error is None
        assert result.pages[0].text == "pdf-body"
        assert pdf_adapter.parse_calls and not docx_adapter.parse_calls
        # The sub-parser identity (not "composite") is preserved.
        assert result.parser_name == "fake"

    def test_dispatches_docx_to_docx_adapter(self) -> None:
        pdf_adapter, docx_adapter = self._fakes()
        comp = CompositeParserAdapter(
            {"application/pdf": pdf_adapter, DOCX_MIME_TYPE: docx_adapter}
        )

        result = asyncio.run(comp.parse(_make_docx(), DOCX_MIME_TYPE))

        assert result.fatal_error is None
        assert result.pages[0].text == "docx-body"
        assert docx_adapter.parse_calls and not pdf_adapter.parse_calls
        assert result.parser_name == "fake"

    def test_unsupported_mime_is_fatal(self) -> None:
        comp = CompositeParserAdapter(
            {"application/pdf": FakeParserAdapter(), DOCX_MIME_TYPE: FakeParserAdapter()}
        )
        result = asyncio.run(comp.parse(b"x", "image/png"))
        assert result.fatal_error is not None
        assert "unsupported MIME type" in result.fatal_error
        assert result.page_count == 0
        # On the dispatch-fatal path the composite records its own identity.
        assert result.parser_name == "composite"

    def test_supported_mime_types_property(self) -> None:
        comp = CompositeParserAdapter(
            {"application/pdf": PypdfParserAdapter(), DOCX_MIME_TYPE: DocxParserAdapter()}
        )
        assert comp.supported_mime_types == frozenset(
            {"application/pdf", DOCX_MIME_TYPE}
        )


# ---------------------------------------------------------------------------
# Worker integration: DOCX routes through the composite
# ---------------------------------------------------------------------------


class TestWorkerDocxRouting:
    """End-to-end: a DOCX version is parsed by the DOCX adapter via composite."""

    def test_docx_version_uses_docx_parser_identity(self, session_cm) -> None:
        async def _run():
            docx = _make_docx()
            info = await _create_docx_version(
                session_cm, DocumentProcessingStatus.QUEUED, docx_bytes=docx
            )
            sf = _get_session_factory()

            storage = FakeStorageAdapter()
            storage._store[info["storage_key"]] = docx
            storage._meta[info["storage_key"]] = {
                "content_type": DOCX_MIME_TYPE,
                "content_length": len(docx),
                "etag": "test-etag",
                "stored_at": time.time(),
            }

            # Mirror create_worker's production composite (PDF + DOCX).
            parser = CompositeParserAdapter(
                {
                    "application/pdf": PypdfParserAdapter(),
                    DOCX_MIME_TYPE: DocxParserAdapter(),
                }
            )
            # renderer=None (no page rasterisation), ocr=None (native text).
            processor = JobProcessor(sf, parser=parser, storage=storage)

            run_id = make_job_id(str(info["version_id"]), ProcessingStage.PARSE.value)
            job = QueuedJob(
                job_id=str(run_id),
                payload={
                    "document_version_id": str(info["version_id"]),
                    "document_id": str(info["doc_id"]),
                    "organization_id": str(info["org_id"]),
                    "version_number": info["version_number"],
                    "stage": "parse",
                    "run_id": str(run_id),
                    "attempt": 1,
                },
                attempt=1,
                queue=DEFAULT_QUEUE,
            )
            await processor.process(job)

            async with sf() as session:
                version_row = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.id == info["version_id"]
                        )
                    )
                ).scalar_one()
                assert version_row.processing_status == DocumentProcessingStatus.PARSED
                # The *sub-parser* identity is recorded, not "composite".
                assert version_row.parser_name == "python-docx"
                assert version_row.parser_version

                pages = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(pages) == 1
                page = pages[0]
                assert page.page_number == 1
                assert page.ocr_needed == 0  # native text, OCR not needed
                extracted = page.extracted_text or ""
                assert "operating temperature" in extracted
                assert "IP65" in extracted
                # Provenance warning persisted on the page.
                meta = page.structural_metadata or {}
                assert any(
                    "no inherent page count" in w for w in meta.get("warnings", [])
                )

                # All four stage runs completed.
                runs = (
                    await session.execute(
                        select(ProcessingRun).where(
                            ProcessingRun.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(runs) == 4
                assert all(r.status == RunStatus.COMPLETED for r in runs)

        asyncio.run(_run())
