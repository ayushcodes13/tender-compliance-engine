"""DOCX parser adapter (CP22).

Parses ``application/vnd.openxmlformats-officedocument.wordprocessingml.document``
(.docx) files into the same :class:`PageResult`/`ParseResult` structures the
rest of the pipeline expects, so DOCX documents can enter the same
PARSE → OCR → EXTRACT flow as PDFs.

Format-appropriate provenance (the CP22 guardrail):

* ``python-docx`` exposes paragraphs, headings, lists, and table cells as
  text content, **not** page numbers.  A .docx carries no inherent page
  count — the rendered page count is determined only by the consuming
  application (Word, LibreOffice, a print driver).  We therefore do **not**
  fabricate per-page page numbers: the whole document is surfaced as a
  single text segment (``page_number=1``) with a warning that makes the
  limitation explicit.
* Native .docx text is authoritative (it is not OCR), so every page is
``ocr_needed=False``.

Security: ``python-docx`` only reads structural XML — it does not execute
macros, JavaScript, or embedded ActiveX.  Malicious macro/active-content
payloads are *not* executed by this parser (they are not run at all).

A future checkpoint (CP23) may split on explicit ``<w:br w:type="page">``
elements to produce genuinely page-bounded segments; until then the single
segment is the honest representation.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from tender_compliance_api.parser.adapter import (
    PageResult,
    ParserAdapter,
    ParseResult,
)

logger = logging.getLogger(__name__)

# The media type for Office Open XML wordprocessing documents.
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)


def _paragraph_text(para: Any) -> str:
    """Return the concatenated text of all ``w:t`` runs in a paragraph."""
    return "".join(t.text or "" for t in para.iter(qn("w:t")))


def _table_text(table: Any) -> str:
    """Return cell text joined by row/cell, preserving table order."""
    rows: list[str] = []
    for row in table.iter(qn("w:tr")):
        for cell in row.iter(qn("w:tc")):
            cell_text = "".join(t.text or "" for t in cell.iter(qn("w:t")))
            if cell_text.strip():
                rows.append(cell_text.strip())
    return "\n".join(rows)


class DocxParserAdapter(ParserAdapter):
    """Parser for ``.docx`` documents via ``python-docx``."""

    @property
    def name(self) -> str:
        return "python-docx"

    @property
    def version(self) -> str:
        try:
            import docx as _docx

            return _docx.__version__
        except Exception:  # noqa: BLE001 — never block a parse on metadata
            return "unknown"

    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        # Only parse .docx — other MIME types are a fatal error.
        if mime_type != DOCX_MIME_TYPE:
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=f"unsupported MIME type: {mime_type}",
            )

        try:
            document = Document(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001 — untrusted input, never raise
            logger.warning("docx parse failed: %s", exc)
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=f"DOCX could not be read: {exc!r}",
            )

        # Walk the document body in element order so that paragraphs and
        # tables are interleaved in source order.  Non-paragraph/table
        # children (e.g. sectPr) are skipped.
        body = document.element.body
        chunks: list[str] = []
        for child in body:
            tag = child.tag
            if tag == qn("w:p"):
                text = _paragraph_text(child)
                if text.strip():
                    chunks.append(text.strip())
            elif tag == qn("w:tbl"):
                text = _table_text(child)
                if text:
                    chunks.append(text)

        text = "\n".join(chunks)

        return ParseResult(
            parser_name=self.name,
            parser_version=self.version,
            page_count=1,
            pages=[
                PageResult(
                    page_number=1,
                    text=text,
                    text_length=len(text),
                    ocr_needed=False,
                    warnings=[
                        "DOCX carries no inherent page count; the document is "
                        "surfaced as a single text segment. Page boundaries are "
                        "not asserted here (see CP23 for page-break splitting)."
                    ],
                    error=None,
                )
            ],
        )


__all__ = ["DocxParserAdapter", "DOCX_MIME_TYPE"]
