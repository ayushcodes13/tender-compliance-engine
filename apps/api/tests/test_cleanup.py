"""Tests for CP23 deterministic header/footer cleanup.

Covers:
- The pure :func:`cleanup_pages` algorithm: repeated header/footer lines are
  detected and stripped from ``cleaned_text`` (never from the raw text),
  while unique body text, varying per-page lines, and numbered-clause
  references are left untouched.
- :meth:`DocumentService.store_pages` persists ``cleaned_text`` and the
  header/footer provenance into ``DocumentPage.structural_metadata``.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import uuid

from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    StoredObject,
    TenderDocument,
    User,
)
from tender_compliance_api.document.service import DocumentService
from tender_compliance_api.parser.adapter import PageResult, ParseResult
from tender_compliance_api.parser.cleanup import cleanup_pages
from tender_compliance_api.storage.keys import build_key
from tender_compliance_worker.processor import WORKER_ACTOR_ID

# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


def _page(text: str, num: int = 1) -> PageResult:
    return PageResult(
        page_number=num,
        text=text,
        text_length=len(text),
        ocr_needed=False,
        warnings=[],
        error=None,
    )


class TestCleanupPages:
    """Unit tests for the deterministic cleanup algorithm."""

    def test_single_page_not_stripped(self) -> None:
        # A line repeated on only 1 page cannot be a header/footer.
        pages = [_page("CONFIDENTIAL\nbody text\nCONFIDENTIAL")]
        out = cleanup_pages(pages)
        assert len(out) == 1
        assert out[0].cleaned_text == "CONFIDENTIAL\nbody text\nCONFIDENTIAL"
        assert out[0].headers == []
        assert out[0].footers == []

    def test_repeated_header_stripped(self) -> None:
        pages = [
            _page("CONFIDENTIAL\nBody of page one", 1),
            _page("CONFIDENTIAL\nBody of page two", 2),
            _page("CONFIDENTIAL\nBody of page three", 3),
        ]
        out = cleanup_pages(pages)
        assert len(out) == 3
        for c in out:
            assert c.headers == ["CONFIDENTIAL"]
            assert "CONFIDENTIAL" not in c.cleaned_text
            assert any("stripped repeated header" in w for w in c.warnings)
        # Raw text on the input PageResults is untouched (no mutation).
        assert pages[0].text.startswith("CONFIDENTIAL\nBody of page one")

    def test_repeated_footer_stripped(self) -> None:
        pages = [
            _page("Body one\nPage 1 of 3", 1),
            _page("Body two\nPage 1 of 3", 2),
            _page("Body three\nPage 1 of 3", 3),
        ]
        out = cleanup_pages(pages)
        for c in out:
            assert c.footers == ["Page 1 of 3"]
            assert "Page 1 of 3" not in c.cleaned_text
            assert any("stripped repeated footer" in w for w in c.warnings)
        # Body text preserved.
        assert "Body one" in out[0].cleaned_text

    def test_varying_per_page_lines_not_stripped(self) -> None:
        # "Page N" footers vary per page -> not identical -> never stripped.
        pages = [
            _page("Body one\nPage 1", 1),
            _page("Body two\nPage 2", 2),
            _page("Body three\nPage 3", 3),
        ]
        out = cleanup_pages(pages)
        # Nothing stripped: cleaned_text equals the raw text.
        assert [c.cleaned_text for c in out] == [p.text for p in pages]
        assert [c.headers for c in out] == [[], [], []]
        assert [c.footers for c in out] == [[], [], []]
        assert "Page 1" in out[0].cleaned_text
        assert "Page 2" in out[1].cleaned_text
        assert "Page 3" in out[2].cleaned_text

    def test_clause_numbered_lines_not_stripped(self) -> None:
        # Numbered clause references must never be treated as header/footer.
        pages = [
            _page("1.2.3 Scope\nBody one", 1),
            _page("1.2.3 Scope\nBody two", 2),
        ]
        out = cleanup_pages(pages)
        for c in out:
            assert c.headers == []
            assert "1.2.3 Scope" in c.cleaned_text

    def test_unique_body_text_preserved(self) -> None:
        # Distinct first/last lines on every page -> nothing matches the
        # header/footer repetition rule, so cleaned == raw.
        pages = [
            _page("Body one line A\nBody one line B", 1),
            _page("Body two line A\nBody two line B", 2),
        ]
        out = cleanup_pages(pages)
        assert [c.cleaned_text for c in out] == [p.text for p in pages]
        assert [c.headers for c in out] == [[], []]
        assert [c.footers for c in out] == [[], []]
        assert "Body one line A" in out[0].cleaned_text
        assert "Body two line B" in out[1].cleaned_text

    def test_long_header_not_stripped(self) -> None:
        # Lines longer than the header/footer length cap are content, not
        # noise — even if repeated.
        long_line = "x" * 200
        pages = [_page(f"{long_line}\nbody", 1), _page(f"{long_line}\nbody", 2)]
        out = cleanup_pages(pages)
        for c in out:
            assert c.headers == []
            assert long_line in c.cleaned_text

    def test_does_not_mutate_input(self) -> None:
        pages = [_page("CONFIDENTIAL\nbody", 1), _page("CONFIDENTIAL\nbody", 2)]
        original = [p.text for p in pages]
        cleanup_pages(pages)
        assert [p.text for p in pages] == original


# ---------------------------------------------------------------------------
# store_pages integration (DB)
# ---------------------------------------------------------------------------


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None, "Session factory not initialized"
    return _session_factory


def _pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buf)
    return buf.getvalue()


async def _create_version(session_cm, status: DocumentProcessingStatus) -> dict:
    """Create org/project/doc/version/stored-object (PDF-ish)."""
    data = _pdf_bytes()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    stored_object_id = uuid.uuid4()
    storage_key = build_key(
        org_id=org_id, project_id=project_id, document_id=doc_id, version=1
    )
    async with session_cm() as session:
        session.add(Organization(id=org_id, name="CP23 Org"))
        session.add(User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id)))
        session.add(Membership(organization_id=org_id, user_id=user_id, role="owner"))
        session.add(Project(id=project_id, organization_id=org_id, name="CP23 Project"))
        session.add(
            StoredObject(
                id=stored_object_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=storage_key,
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=len(data),
                checksum_sha256=hashlib.sha256(data).hexdigest(),
            )
        )
        session.add(TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf"))
        await session.flush()
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            stored_object_id=stored_object_id,
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type="application/pdf",
            size_bytes=len(data),
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
        "storage_key": storage_key,
    }


def _auth(org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=WORKER_ACTOR_ID, organization_id=org_id, roles=frozenset({"worker"})
    )


class TestStorePagesCleanup:
    """store_pages persists cleaned_text + header/footer provenance."""

    def test_store_pages_records_cleaned_text_and_headers(self, session_cm) -> None:
        async def _run():
            info = await _create_version(session_cm, DocumentProcessingStatus.QUEUED)
            sf = _get_session_factory()
            auth = _auth(info["org_id"])

            pages = [
                PageResult(page_number=1, text="CONFIDENTIAL\nReq one",
                           text_length=0, ocr_needed=False, warnings=[], error=None),
                PageResult(page_number=2, text="CONFIDENTIAL\nReq two",
                           text_length=0, ocr_needed=False, warnings=[], error=None),
                PageResult(page_number=3, text="CONFIDENTIAL\nReq three",
                           text_length=0, ocr_needed=False, warnings=[], error=None),
            ]
            parse_result = ParseResult(
                parser_name="test", parser_version="test",
                page_count=len(pages), pages=pages,
            )

            async with sf() as session:
                svc = DocumentService(session)
                stored = await svc.store_pages(
                    auth, info["doc_id"], info["version_number"], parse_result
                )
                assert len(stored) == 3
                await session.commit()
                session.expunge_all()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                rows.sort(key=lambda r: r.page_number)
                # Raw text preserved.
                assert rows[0].extracted_text == "CONFIDENTIAL\nReq one"
                # Header stripped from cleaned view.
                assert rows[0].cleaned_text == "Req one"
                assert "CONFIDENTIAL" not in rows[0].cleaned_text
                # Provenance recorded in structural_metadata.
                meta = rows[0].structural_metadata or {}
                assert meta.get("headers") == ["CONFIDENTIAL"]
                assert any("stripped repeated header" in w for w in meta.get("warnings", []))

        asyncio.run(_run())

    def test_reparse_does_not_duplicate_pages(self, session_cm) -> None:
        async def _run():
            info = await _create_version(session_cm, DocumentProcessingStatus.QUEUED)
            sf = _get_session_factory()
            auth = _auth(info["org_id"])

            parse_result = ParseResult(
                parser_name="test", parser_version="test",
                page_count=2,
                pages=[
                    PageResult(page_number=1, text="a", text_length=1,
                               ocr_needed=False, warnings=[], error=None),
                    PageResult(page_number=2, text="b", text_length=1,
                               ocr_needed=False, warnings=[], error=None),
                ],
            )

            async with sf() as session:
                svc = DocumentService(session)
                await svc.store_pages(auth, info["doc_id"], info["version_number"], parse_result)
                await session.commit()
                # Re-store with a different page count -> old rows replaced.
                parse_result2 = ParseResult(
                    parser_name="test", parser_version="test",
                    page_count=1,
                    pages=[
                        PageResult(page_number=1, text="only", text_length=4,
                                   ocr_needed=False, warnings=[], error=None),
                    ],
                )
                await svc.store_pages(auth, info["doc_id"], info["version_number"], parse_result2)
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id == info["version_id"]
                        )
                    )
                ).scalars().all()
                assert len(rows) == 1  # old rows replaced, not duplicated
                assert rows[0].extracted_text == "only"

        asyncio.run(_run())

    def test_store_pages_persists_page_error(self, session_cm) -> None:
        """A page-level parse/extraction error is preserved in structural
        metadata (never silently swallowed), while healthy pages stay clean."""
        async def _run():
            info = await _create_version(
                session_cm, DocumentProcessingStatus.QUEUED
            )
            sf = _get_session_factory()
            auth = _auth(info["org_id"])

            pages = [
                PageResult(
                    page_number=1,
                    text="",
                    text_length=0,
                    ocr_needed=False,
                    warnings=[],
                    error="text extraction failed: corrupted stream",
                ),
                PageResult(
                    page_number=2,
                    text="Body two",
                    text_length=8,
                    ocr_needed=False,
                    warnings=[],
                    error=None,
                ),
            ]
            parse_result = ParseResult(
                parser_name="test",
                parser_version="test",
                page_count=len(pages),
                pages=pages,
            )

            async with sf() as session:
                svc = DocumentService(session)
                stored = await svc.store_pages(
                    auth, info["doc_id"], info["version_number"], parse_result
                )
                assert len(stored) == 2
                await session.commit()

            async with sf() as session:
                rows = (
                    await session.execute(
                        select(DocumentPage).where(
                            DocumentPage.document_version_id
                            == info["version_id"]
                        )
                    )
                ).scalars().all()
                rows.sort(key=lambda r: r.page_number)
                # Failed page: error preserved, cleaned_text empty (no text
                # to clean — empty extraction stores NULL per CP19 behaviour).
                err_meta = rows[0].structural_metadata or {}
                assert (
                    err_meta.get("error")
                    == "text extraction failed: corrupted stream"
                )
                assert rows[0].extracted_text is None
                # Healthy page: no error key, text preserved.
                ok_meta = rows[1].structural_metadata or {}
                assert "error" not in ok_meta
                assert rows[1].extracted_text == "Body two"

        asyncio.run(_run())
