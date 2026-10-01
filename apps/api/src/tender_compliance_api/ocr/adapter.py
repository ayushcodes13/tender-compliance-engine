"""OCR adapter port (CP21).

This module defines the *abstract interface* the application depends on
for turning a rendered page image into recognized text.  Concrete
implementations (Tesseract, cloud providers) live in sibling modules.

The interface is intentionally narrow and provider-agnostic so that a
different OCR backend can be swapped in without touching business logic
— mirroring the :mod:`tender_compliance_api.renderer` and
:mod:`tender_compliance_api.parser` abstractions.

A recognised page is returned as an :class:`OcrResult` carrying the
plain text, an aggregate confidence, and optional per-word geometry.
``confidence`` is ``None`` when the provider cannot supply one; callers
must treat ``None`` as "unknown", never as "high".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OcrWord:
    """A single recognized word with optional geometry + confidence.

    ``bbox`` is the word's bounding box in *image coordinates* as
    ``(x, y, width, height)`` when the provider exposes it, else
    ``None``.
    """

    text: str
    confidence: float | None = None
    bbox: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class OcrResult:
    """The OCR output for a single page image.

    ``text`` is the provider's best recognized text (may be empty when
    nothing could be read — this is **not** the same as "no OCR was
    attempted").  ``confidence`` is an aggregate in ``[0, 100]`` or
    ``None`` when unknown.  ``words`` carries per-symbol detail used for
    uncertainty preservation and geometry provenance.
    """

    text: str
    confidence: float | None = None
    words: list[OcrWord] = field(default_factory=list)


class OcrAdapter(ABC):
    """Abstract interface every OCR provider implementation must satisfy.

    Methods are ``async`` so callers (the worker) can ``await`` them;
    CPU-bound providers wrap their synchronous work in
    ``asyncio.to_thread``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier persisted to ``DocumentVersion.ocr_name``."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider/version string persisted to ``DocumentVersion.ocr_version``."""

    @abstractmethod
    async def ocr(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> OcrResult:
        """OCR a single rendered page image.

        ``image_bytes`` is the page image (typically the PNG produced by
        CP20's renderer).  Returns an :class:`OcrResult`; per-page
        failures are surfaced as a result with empty text and a
        ``None`` confidence rather than by raising.
        """


__all__ = ["OcrAdapter", "OcrResult", "OcrWord"]
