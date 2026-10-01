"""OCR provider abstraction (CP21).

Mirrors the :mod:`tender_compliance_api.parser` / :mod:`renderer` adapter
pattern: a provider-agnostic :class:`OcrAdapter` port plus the
recognised-text data structures, with concrete implementations
(:class:`TesseractOcrAdapter`, :class:`FakeOcrAdapter`) re-exported for
convenience.
"""

from __future__ import annotations

from tender_compliance_api.ocr.adapter import OcrAdapter, OcrResult, OcrWord
from tender_compliance_api.ocr.fake import FakeOcrAdapter
from tender_compliance_api.ocr.tesseract import TesseractOcrAdapter

__all__ = [
    "OcrAdapter",
    "OcrResult",
    "OcrWord",
    "TesseractOcrAdapter",
    "FakeOcrAdapter",
]
