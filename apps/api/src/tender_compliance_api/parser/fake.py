"""In-memory fake PDF parser for testing (CP19).

Returns predetermined :class:`ParseResult` objects without touching real
PDF data.  Useful for unit-testing the worker and storage layers without
generating synthetic PDFs.
"""

from __future__ import annotations

from tender_compliance_api.parser.adapter import (
    PageResult,
    ParserAdapter,
    ParseResult,
)

DEFAULT_PARSER_NAME = "fake"
DEFAULT_PARSER_VERSION = "test"


class FakeParserAdapter(ParserAdapter):
    """Deterministic stub parser for testing.

    Args:
        pages: Optional pre-built list of :class:`PageResult` to return.
            If ``None``, a single-page result with placeholder text is
            produced for any input.
    """

    def __init__(self, pages: list[PageResult] | None = None) -> None:
        self._pages = pages
        self.parse_calls: list[tuple[bytes, str]] = []

    @property
    def name(self) -> str:
        return DEFAULT_PARSER_NAME

    @property
    def version(self) -> str:
        return DEFAULT_PARSER_VERSION

    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        self.parse_calls.append((data, mime_type))
        if self._pages is not None:
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=len(self._pages),
                pages=self._pages,
            )
        # Default: single page with placeholder text.
        text = data.decode("utf-8", errors="replace") if data else ""
        return ParseResult(
            parser_name=self.name,
            parser_version=self.version,
            page_count=1,
            pages=[
                PageResult(
                    page_number=1,
                    text=text or "placeholder",
                    text_length=len(text),
                    ocr_needed=False,
                    warnings=[],
                    error=None,
                )
            ],
        )
