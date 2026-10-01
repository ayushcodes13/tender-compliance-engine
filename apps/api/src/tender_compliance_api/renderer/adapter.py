"""Page renderer adapter abstractions (CP20).

Defines the *port* that the worker depends on: a :class:`RendererAdapter`
that takes raw PDF bytes and returns a :class:`RenderResult` containing
one :class:`RenderPageResult` per page — a stable visual representation
of each page that reviewers can inspect even when native text extraction
is imperfect (e.g. scanned pages).

Design rules mirror :mod:`tender_compliance_api.parser`:

* Only **identifiers** or already-derived image bytes travel through this
  interface — the raw PDF bytes are consumed by the adapter, never placed
  on the queue.
* Page identity is preserved via ``page_number`` (1-indexed, never None).
* Fatal failures (corrupt/encrypted PDF) are returned as ``fatal_error``,
  never raised, so the worker can record them without crashing.
* Per-page render failures are reported on the individual
  :class:`RenderPageResult` (``error`` set) so they can be recorded as
  warnings without aborting the whole document.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RenderPageResult:
    """A rendered image for a single document page.

    Attributes:
        page_number: 1-indexed page number (always set — never None).
        image_bytes: Rendered image bytes (e.g. PNG), or empty if the
            page could not be rendered (``error`` set).
        content_type: Media type of ``image_bytes`` (e.g. ``image/png``).
        render_dpi: The DPI at which the page was rendered.
        warnings: Non-fatal page-level notes (e.g. "page is blank").
        error: Fatal error for this page (e.g. "page corrupt"), or None.
    """

    page_number: int
    image_bytes: bytes
    content_type: str
    render_dpi: int
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class RenderResult:
    """Aggregate result of rendering a single document version.

    Attributes:
        renderer_name: Name of the renderer implementation.
        renderer_version: Version of the renderer implementation.
        render_dpi: The DPI applied to every page.
        page_count: Total number of pages rendered (may be less than the
            source page count if the document could not be opened).
        pages: One :class:`RenderPageResult` per page, ordered by page_number.
        fatal_error: If the document could not be rendered at all (e.g.
            corrupted or encrypted PDF), this holds the error message.
            In that case ``pages`` will be empty and ``page_count`` 0.
    """

    renderer_name: str
    renderer_version: str
    render_dpi: int
    page_count: int
    pages: list[RenderPageResult]
    fatal_error: str | None = None


class RendererAdapter(abc.ABC):
    """Abstract interface for a page renderer.

    Implementations must be safe to call with untrusted input (uploaded
    documents may contain malformed or hostile content).  Rendering must
    not execute embedded document content (JavaScript, embedded files,
    embedded fonts that trigger code paths — PyMuPDF does not execute
    these).
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable renderer name (e.g. ``"pymupdf"``)."""

    @property
    @abc.abstractmethod
    def version(self) -> str:
        """Renderer version (e.g. ``"1.28.2"``)."""

    @property
    @abc.abstractmethod
    def render_dpi(self) -> int:
        """The DPI at which pages are rendered."""

    @abc.abstractmethod
    async def render(
        self, data: bytes, mime_type: str
    ) -> RenderResult:
        """Render ``data`` and return a :class:`RenderResult`.

        Must not raise on malformed input — return a ``RenderResult``
        with ``fatal_error`` set instead.
        """
