"""In-memory fake page renderer (CP20).

Used by tests and local development without a PDF rendering engine.
Produces deterministic, minimal valid PNG bytes per page so tests can
exercise the storage/key-persistence path without depending on
PyMuPDF's exact rasterization output.
"""

from __future__ import annotations

import struct
import zlib

from tender_compliance_api.renderer.adapter import (
    RendererAdapter,
    RenderPageResult,
    RenderResult,
)


def _minimal_png() -> bytes:
    """Return a valid, minimal (1×1) PNG via the stdlib only.

    Encoding a real PNG with only ``zlib`` + ``struct`` keeps the fake
    renderer dependency-free while still producing bytes that begin with
    the PNG signature, so downstream assertions on content type / size
    behave as they would for a real render.
    """

    width = height = 1
    # Raw scanline: filter byte (0) + one RGB pixel (red).
    raw = b"\x00\xff\x00\x00"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


class FakeRendererAdapter(RendererAdapter):
    """Deterministic renderer that never touches real PDF tooling.

    It reports the page count configured at construction time and emits a
    minimal PNG for each page.  Tests can assert that rendering ran and
    that image keys were persisted without depending on PyMuPDF's exact
    output.
    """

    def __init__(self, *, dpi: int = 150, page_count: int = 1) -> None:
        self._dpi = dpi
        self._page_count = page_count

    @property
    def name(self) -> str:
        return "fake"

    @property
    def version(self) -> str:
        return "0.0.0-fake"

    @property
    def render_dpi(self) -> int:
        return self._dpi

    async def render(
        self, data: bytes, mime_type: str
    ) -> RenderResult:
        if mime_type != "application/pdf":
            return RenderResult(
                renderer_name=self.name,
                renderer_version=self.version,
                render_dpi=self._dpi,
                page_count=0,
                pages=[],
                fatal_error=f"unsupported MIME type: {mime_type}",
            )

        png = _minimal_png()
        pages = [
            RenderPageResult(
                page_number=i + 1,
                image_bytes=png,
                content_type="image/png",
                render_dpi=self._dpi,
                warnings=["fake render — deterministic test fixture"],
                error=None,
            )
            for i in range(self._page_count)
        ]
        return RenderResult(
            renderer_name=self.name,
            renderer_version=self.version,
            render_dpi=self._dpi,
            page_count=len(pages),
            pages=pages,
        )
