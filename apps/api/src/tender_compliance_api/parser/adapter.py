"""PDF parser adapter abstractions (CP19).

Defines the *port* that the worker depends on: a :class:`ParserAdapter`
that takes raw PDF bytes and returns a :class:`ParseResult` containing
one :class:`PageResult` per page.

Security: the parser only reads structural text from the PDF — it never
executes embedded content (JavaScript, embedded files, etc.).  Warnings
about embedded content are reported but never acted upon.

Every parsed fragment retains document-version/page identity via
``page_number`` on :class:`PageResult`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageResult:
    """Text extracted from a single PDF page.

    Attributes:
        page_number: 1-indexed page number (always set — never None).
        text: The extracted native text, or empty string if the page
            has no text layer (e.g. a scanned raster).
        text_length: ``len(text)`` — precomputed for fast checks.
        ocr_needed: True if the native text is untrustworthy or absent
            and OCR should be applied (CP21).
        warnings: Page-level warnings (e.g. "page has images but no text").
        error: Fatal error for this page (e.g. "page corrupt"), or None.
    """

    page_number: int
    text: str
    text_length: int
    ocr_needed: bool
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ParseResult:
    """Aggregate result of parsing a single document version.

    Attributes:
        parser_name: Name of the parser implementation.
        parser_version: Version of the parser implementation.
        page_count: Total number of pages in the document.
        pages: One :class:`PageResult` per page, ordered by page_number.
        fatal_error: If the document could not be parsed at all (e.g.
            corrupted or encrypted PDF), this holds the error message.
            In that case ``pages`` will be empty and ``page_count`` 0.
    """

    parser_name: str
    parser_version: str
    page_count: int
    pages: list[PageResult]
    fatal_error: str | None = None


class ParserAdapter(abc.ABC):
    """Abstract interface for a document-format parser.

    Implementations must be safe to call with untrusted input (uploaded
    documents may contain malformed or hostile content).
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable parser name (e.g. ``\"pypdf\"``)."""

    @property
    @abc.abstractmethod
    def version(self) -> str:
        """Parser version (e.g. ``\"4.3.1\"``)."""

    @abc.abstractmethod
    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        """Parse ``data`` and return a :class:`ParseResult`.

        Must not raise on malformed input — return a ``ParseResult``
        with ``fatal_error`` set instead.
        """
