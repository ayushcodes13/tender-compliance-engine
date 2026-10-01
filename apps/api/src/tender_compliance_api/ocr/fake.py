"""Deterministic fake OCR adapter for tests (CP21).

Returns a fixed, configurable :class:`OcrResult` so that extraction/
state-machine logic can be tested without a ``tesseract`` binary or any
network provider.  It deliberately does **not** claim to be a real OCR
engine — its ``name``/``version`` mark it as a test double.
"""

from __future__ import annotations

from tender_compliance_api.ocr.adapter import OcrAdapter, OcrResult, OcrWord


class FakeOcrAdapter(OcrAdapter):
    """Deterministic OCR adapter used by tests.

    Args:
        text: The ``OcrResult.text`` to return for every image.
        confidence: The ``OcrResult.confidence`` to return (``None`` =
            unknown).
        words: Optional pre-built word list (e.g. to exercise geometry).
    """

    def __init__(
        self,
        text: str = "",
        confidence: float | None = 95.0,
        words: list[OcrWord] | None = None,
    ) -> None:
        self._text = text
        self._confidence = confidence
        self._words = list(words) if words else []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def version(self) -> str:
        return "0.0.0-test"

    async def ocr(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> OcrResult:
        # Image content is ignored — this is a test double.  The bytes are
        # accepted (and validated as non-empty bytes) so caller wiring is
        # exercised, but recognition is fully deterministic.
        return OcrResult(
            text=self._text,
            confidence=self._confidence,
            words=list(self._words),
        )


__all__ = ["FakeOcrAdapter"]
