"""PyMuPDF parser adapter for source-faithful native PDF text extraction.

PyMuPDF preserves text ordering and hyphenated words more accurately than the
legacy pypdf extractor on many digitally-born tender PDFs. Scanned pages remain
explicitly marked for OCR; this adapter never guesses their text.
"""

from __future__ import annotations

import logging
import re
import warnings

import pymupdf

from tender_compliance_api.errors import PAGE_TEXT_FAILURE, PROCESSING_STAGE_FAILURE
from tender_compliance_api.parser.adapter import PageResult, ParserAdapter, ParseResult

logger = logging.getLogger(__name__)
_MIN_TRUSTWORTHY_TEXT_LEN = 5
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$")
_PAGE_MARGIN_POINTS = 120.0
_SUSPICIOUS_SUBSCRIPT_ORDER = re.compile(
    r"\b(?:details\s+of\s+)?\d\s+\d+\s+achievable\s+"
    r"[A-Z][a-z]?\s*/\s*[A-Z][a-z]?\b",
    re.I,
)


def _page_number_artifacts(
    page: pymupdf.Page, page_number: int
) -> tuple[set[str], set[str]]:
    """Find standalone physical page numbers in the PDF header/footer area."""
    height = page.rect.height
    headers: set[str] = set()
    footers: set[str] = set()
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:  # noqa: BLE001 — text parsing below remains available
        return headers, footers
    for block in blocks:
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            bbox = line.get("bbox")
            if not isinstance(bbox, (tuple, list)) or len(bbox) < 4:
                continue
            if not _PAGE_NUMBER_RE.fullmatch(text) or text.strip() != str(page_number):
                continue
            if bbox[1] <= _PAGE_MARGIN_POINTS:
                headers.add(text.strip())
            elif bbox[3] >= height - _PAGE_MARGIN_POINTS:
                footers.add(text.strip())
    return headers, footers


def _remove_page_number_lines(
    text: str, artifacts: tuple[set[str], set[str]]
) -> str:
    headers, footers = artifacts
    if not headers and not footers:
        return text
    lines = text.splitlines(keepends=True)
    remove_indices: set[int] = set()
    for candidate in headers:
        index = next(
            (i for i, line in enumerate(lines) if line.strip() == candidate), None
        )
        if index is not None:
            remove_indices.add(index)
    for candidate in footers:
        index = next(
            (i for i in range(len(lines) - 1, -1, -1) if lines[i].strip() == candidate),
            None,
        )
        if index is not None:
            remove_indices.add(index)
    return "".join(line for i, line in enumerate(lines) if i not in remove_indices)


def _table_aware_text(page: pymupdf.Page, native_text: str) -> str | None:
    """Return row-ordered table text when it accounts for most page content.

    PDF content-stream order can interleave adjacent table columns. PyMuPDF's
    table detector returns cell text in row order; use it only when the detected
    tables cover at least 72% of the native page text, leaving ordinary prose
    pages on the native-text path.
    """
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Consider using the pymupdf_layout package.*"
            )
            tables = page.find_tables().tables
    except Exception:  # noqa: BLE001 — retain native text on layout failures
        return None

    content_blocks: list[tuple[float, str]] = []
    table_boxes: list[tuple[float, float, float, float]] = []
    for table in tables:
        try:
            bbox = tuple(float(value) for value in table.bbox)
            table_boxes.append(bbox)
            for cells in table.extract():
                values = [" ".join(str(cell).split()) for cell in cells if cell]
                row_text = " | ".join(values).strip()
                if row_text:
                    content_blocks.append((bbox[1], row_text))
        except Exception:  # noqa: BLE001 — skip a corrupt table and keep others
            continue

    # Preserve headings, prose, and footnotes outside detected table bounds.
    # Dropping them can hide the explicit technical-section boundary even when
    # the table itself is reconstructed correctly.
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:  # noqa: BLE001 — keep extracted table rows if dict fails
        blocks = []
    for block in blocks:
        bbox = block.get("bbox")
        if (
            block.get("type") != 0
            or not isinstance(bbox, (tuple, list))
            or len(bbox) < 4
        ):
            continue
        left, top, right, bottom = (float(value) for value in bbox[:4])
        overlaps_table = any(
            left < table_right
            and right > table_left
            and top < table_bottom
            and bottom > table_top
            for table_left, table_top, table_right, table_bottom in table_boxes
        )
        if overlaps_table:
            continue
        lines = []
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if text.strip():
                lines.append(text.strip())
        if lines:
            content_blocks.append((top, "\n".join(lines)))

    table_text = "\n\n".join(
        text for _, text in sorted(content_blocks, key=lambda item: item[0])
    ).strip()
    if len(table_text) < 300 or len(table_text) < len(native_text.strip()) * 0.72:
        return None
    return _remove_page_number_lines(
        table_text, _page_number_artifacts(page, page.number + 1)
    )


class PyMuPDFParserAdapter(ParserAdapter):
    """Extract per-page text from native PDF text layers using PyMuPDF."""

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        return pymupdf.VersionBind

    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        if mime_type != "application/pdf":
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=f"unsupported MIME type: {mime_type}",
            )

        try:
            document = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001 — parser errors are non-fatal
            logger.warning("PyMuPDF rejected document (%s)", type(exc).__name__)
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=PROCESSING_STAGE_FAILURE,
            )

        if document.needs_pass:
            document.close()
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=(
                    "PDF is password-protected; password-protected documents "
                    "are not supported in Phase 1"
                ),
            )

        pages: list[PageResult] = []
        try:
            for index, page in enumerate(document, start=1):
                try:
                    # Preserve PDF content-stream order. Spatial ``sort=True``
                    # can interleave adjacent table columns and bullet glyphs
                    # (e.g. a bullet from the next table row inside a value).
                    text = page.get_text("text", sort=False) or ""
                    table_text = _table_aware_text(page, text)
                    if table_text is not None:
                        # The table detector returns cell text in row order.
                        # This is a structured native-text extraction path, not
                        # OCR; keep row/cell boundaries in the canonical page
                        # text without forcing every exact table quote through
                        # the slower page-image fallback.
                        text = table_text
                        visual_verification_required = False
                    else:
                        text = _remove_page_number_lines(
                            text, _page_number_artifacts(page, index)
                        )
                        visual_verification_required = False
                except Exception as exc:  # noqa: BLE001 — preserve page failure
                    logger.warning(
                        "PyMuPDF page text failed (page=%d, error=%s)",
                        index,
                        type(exc).__name__,
                    )
                    pages.append(
                        PageResult(
                            page_number=index,
                            text="",
                            text_length=0,
                            ocr_needed=True,
                            warnings=[],
                            error=PAGE_TEXT_FAILURE,
                        )
                    )
                    continue

                text = text.strip()
                warnings: list[str] = []
                ocr_needed = False
                if _SUSPICIOUS_SUBSCRIPT_ORDER.search(text):
                    visual_verification_required = True
                    warnings.append(
                        "native text may have separated chemical subscripts; "
                        "compare with rendered page"
                    )
                if not text:
                    ocr_needed = True
                    warnings.append("page has no extractable text layer — OCR required")
                elif len(text) < _MIN_TRUSTWORTHY_TEXT_LEN:
                    warnings.append(
                        f"page text is very short ({len(text)} chars) — "
                        "may be a watermark or artifact"
                    )

                pages.append(
                    PageResult(
                        page_number=index,
                        text=text,
                        text_length=len(text),
                        ocr_needed=ocr_needed,
                        warnings=warnings,
                        error=None,
                        visual_verification_required=visual_verification_required,
                    )
                )
        finally:
            document.close()

        return ParseResult(
            parser_name=self.name,
            parser_version=self.version,
            page_count=len(pages),
            pages=pages,
        )


__all__ = ["PyMuPDFParserAdapter"]
