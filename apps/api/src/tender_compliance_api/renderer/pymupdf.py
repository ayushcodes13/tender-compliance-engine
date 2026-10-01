"""PyMuPDF-based page renderer (CP20).

Uses the ``pymupdf`` (``fitz``) library to rasterize each PDF page to a
PNG image at a stable DPI.  PyMuPDF does **not** execute embedded
JavaScript or render page content as code — it performs a safe
structural rasterization, so it is safe to run on untrusted uploads.

Each page is rendered independently so a single corrupt page does not
abort the whole document; per-page failures are surfaced as
``RenderPageResult.error`` rather than fatal errors.
"""

from __future__ import annotations

import logging

import pymupdf

from tender_compliance_api.renderer.adapter import (
    RendererAdapter,
    RenderPageResult,
    RenderResult,
)

logger = logging.getLogger(__name__)

#: Minimum PNG bytes that count as a successful render of a page.
_MIN_RENDERED_BYTES = 16


class PymupdfRendererAdapter(RendererAdapter):
    """Render PDF pages to PNG images using PyMuPDF.

    Args:
        dpi: Dots-per-inch for rasterization.  150 is a deliberate
            balance between readability and storage cost (matches the
            resolution chosen for local review).
    """

    def __init__(self, *, dpi: int = 150) -> None:
        self._dpi = dpi

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        try:
            # ``pymupdf.__version__`` is the canonical release string
            # (e.g. "1.28.2").  ``pymupdf.version`` is a deprecated,
            # oddly-shaped tuple (e.g. ("1.28.2", "1.28.2", None)) and is
            # not safe to join.
            return pymupdf.__version__
        except AttributeError:
            parts = getattr(pymupdf, "version", ())
            first = parts[0] if parts else "unknown"
            return str(first)

    @property
    def render_dpi(self) -> int:
        return self._dpi

    async def render(self, data: bytes, mime_type: str) -> RenderResult:
        if mime_type != "application/pdf":
            return RenderResult(
                renderer_name=self.name,
                renderer_version=self.version,
                render_dpi=self._dpi,
                page_count=0,
                pages=[],
                fatal_error=f"unsupported MIME type: {mime_type}",
            )

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as exc:  # noqa: BLE001 — any open failure is non-fatal
            logger.warning("pymupdf document open error: %s", exc)
            if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
                return self._encrypted(data, str(exc))
            return RenderResult(
                renderer_name=self.name,
                renderer_version=self.version,
                render_dpi=self._dpi,
                page_count=0,
                pages=[],
                fatal_error=f"PDF could not be opened for rendering: {exc!r}",
            )

        try:
            if doc.is_encrypted:
                return self._encrypted(data, "document is encrypted")

            page_count = doc.page_count
            pages: list[RenderPageResult] = []
            for i in range(page_count):
                page_number = i + 1  # 1-indexed
                try:
                    page = doc[i]
                    pix = page.get_pixmap(dpi=self._dpi)
                    png_bytes = pix.tobytes("png")  # type: ignore[no-untyped-call]
                except Exception as exc:  # noqa: BLE001 — per-page failure
                    pages.append(
                        RenderPageResult(
                            page_number=page_number,
                            image_bytes=b"",
                            content_type="image/png",
                            render_dpi=self._dpi,
                            warnings=[],
                            error=f"page render failed: {exc!r}",
                        )
                    )
                    continue

                warnings: list[str] = []
                if len(png_bytes) < _MIN_RENDERED_BYTES:
                    warnings.append("rendered page image is suspiciously small")
                # A blank (all-white) page is valid but worth noting.
                if self._is_blank(png_bytes):
                    warnings.append("page appears blank")

                pages.append(
                    RenderPageResult(
                        page_number=page_number,
                        image_bytes=png_bytes,
                        content_type="image/png",
                        render_dpi=self._dpi,
                        warnings=warnings,
                        error=None,
                    )
                )

            return RenderResult(
                renderer_name=self.name,
                renderer_version=self.version,
                render_dpi=self._dpi,
                page_count=len(pages),
                pages=pages,
            )
        finally:
            doc.close()  # type: ignore[no-untyped-call]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _encrypted(self, data: bytes, reason: str) -> RenderResult:
        return RenderResult(
            renderer_name=self.name,
            renderer_version=self.version,
            render_dpi=self._dpi,
            page_count=0,
            pages=[],
            fatal_error=(
                "PDF is password-protected; password-protected documents "
                "are not supported in Phase 1"
            ),
        )

    @staticmethod
    def _is_blank(png_bytes: bytes) -> bool:
        """Heuristic: treat a tiny image as blank/uninformative.

        A full blankness check would require decoding the PNG and scanning
        pixels; that is overkill for a warning flag, so we only suppress
        the warning for images that are too small to carry page content.
        """
        return len(png_bytes) < 64
