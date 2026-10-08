"""pypdf-based PDF parser adapter (CP19).

Uses the already-present ``pypdf`` dependency to extract per-page text
from digitally-born PDFs.  Detects unencrypted, text-bearing pages and
flags pages that appear to be scanned rasters (no extractable text) as
``ocr_needed=True``.

Security: ``pypdf.PdfReader`` only reads structural text — it does not
execute JavaScript or render page content.
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from tender_compliance_api.errors import PAGE_TEXT_FAILURE, PROCESSING_STAGE_FAILURE
from tender_compliance_api.parser.adapter import (
    PageResult,
    ParserAdapter,
    ParseResult,
)

logger = logging.getLogger(__name__)

#: Minimum text length to consider a page's native text trustworthy.
_MIN_TRUSTWORTHY_TEXT_LEN = 5


class PypdfParserAdapter(ParserAdapter):
    """PDF parser backed by ``pypdf``.

    Extracts text per page, preserving page order.  Pages with no
    extractable text (e.g. scanned images) are flagged with
    ``ocr_needed=True``.
    """

    @property
    def name(self) -> str:
        return "pypdf"

    @property
    def version(self) -> str:
        return _PYPDF_VERSION

    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        # Only parse PDFs — other MIME types are a fatal error.
        if mime_type != "application/pdf":
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=f"unsupported MIME type: {mime_type}",
            )

        try:
            reader = PdfReader(io.BytesIO(data))
        except PdfReadError as exc:
            logger.warning("pypdf rejected document (%s)", type(exc).__name__)
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=PROCESSING_STAGE_FAILURE,
            )
        except Exception as exc:  # noqa: BLE001 — any parse failure is non-fatal
            logger.warning("pypdf unexpected error (%s)", type(exc).__name__)
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=PROCESSING_STAGE_FAILURE,
            )

        # --- Encryption check ---
        if reader.is_encrypted:
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
        for i, page in enumerate(reader.pages):
            page_number = i + 1  # 1-indexed
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                pages.append(
                    PageResult(
                        page_number=page_number,
                        text="",
                        text_length=0,
                        ocr_needed=True,
                        warnings=[],
                        error=PAGE_TEXT_FAILURE,
                    )
                )
                continue

            text = text.strip()
            has_images = len(page.images) > 0 if hasattr(page, "images") else False

            warnings: list[str] = []
            ocr_needed = False

            if not text:
                # No native text — likely a scanned raster page.
                ocr_needed = True
                if has_images:
                    warnings.append(
                        "page has images but no extractable text — OCR recommended"
                    )
                else:
                    warnings.append("page has no text layer")
            elif len(text) < _MIN_TRUSTWORTHY_TEXT_LEN:
                warnings.append(
                    f"page text is very short ({len(text)} chars) — "
                    "may be a watermark or artifact"
                )
            elif has_images and len(text) < 50:
                warnings.append(
                    "page has images with very little text — may be a "
                    "scanned-with-text-overlay page"
                )

            pages.append(
                PageResult(
                    page_number=page_number,
                    text=text,
                    text_length=len(text),
                    ocr_needed=ocr_needed,
                    warnings=warnings,
                    error=None,
                )
            )

        return ParseResult(
            parser_name=self.name,
            parser_version=self.version,
            page_count=len(pages),
            pages=pages,
        )


# Resolve the pypdf version at import time so it is recorded on every
# ParseResult without re-reading the package metadata on each call.
try:
    from pypdf import __version__ as _PYPDF_VERSION
except ImportError:  # pragma: no cover
    _PYPDF_VERSION = "unknown"
