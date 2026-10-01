"""Tesseract-backed OCR adapter (CP21).

Uses `pytesseract` to drive the local `tesseract` OCR engine on rendered
page images.  PyTesseract/PyTesseract perform a **non-executing**
recognition pass — they do not run JavaScript or page content as code —
so they are safe to run on untrusted uploads.

Per-page CPU-bound work is dispatched via :func:`asyncio.to_thread` so the
worker event loop is not blocked.

Provider-availability errors (e.g. the ``tesseract`` binary is missing) are
**not** swallowed: they propagate to :meth:`DocumentService.apply_ocr`,
which records a per-page, non-fatal warning and leaves the page's
``ocr_needed`` flag set so the version correctly lands in ``PARTIAL``.
Genuine per-page OCR failures (e.g. a corrupt image that PIL cannot open)
are returned as an empty :class:`OcrResult` per the adapter contract.

A real ``tesseract`` binary is a production system dependency (not a
Python package) — see ``review.md``.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

import pytesseract  # type: ignore[import-untyped]
from PIL import Image

from tender_compliance_api.ocr.adapter import OcrAdapter, OcrResult, OcrWord


class TesseractOcrAdapter(OcrAdapter):
    """OCR adapter backed by the local Tesseract engine via pytesseract."""

    def __init__(self, lang: str | None = None) -> None:
        self._lang = lang

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def version(self) -> str:
        try:
            raw = pytesseract.get_tesseract_version()
        except Exception:  # noqa: BLE001 — binary may be absent
            return "unavailable"
        if isinstance(raw, (tuple, list)):
            return ".".join(str(x) for x in raw)
        return str(raw)

    async def ocr(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> OcrResult:
        # A corrupt/unreadable image is a per-page failure: return an empty
        # result per the adapter contract rather than propagating.
        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception:  # noqa: BLE001 — image decode failure
            return OcrResult(text="", confidence=None, words=[])

        lang = self._lang

        def _recognize() -> OcrResult:
            text = pytesseract.image_to_string(
                img, lang=lang
            )
            data = pytesseract.image_to_data(
                img,
                lang=lang,
                output_type=pytesseract.Output.DICT,
            )
            words: list[OcrWord] = []
            confs: list[float] = []
            text_list: list[Any] = data.get("text", [])
            conf_list: list[Any] = data.get("conf", [])
            for i in range(len(text_list)):
                t = text_list[i]
                if not t:
                    continue
                c = conf_list[i] if i < len(conf_list) else -1
                conf = float(c) if (c is not None and c != -1) else None
                if conf is not None:
                    confs.append(conf)
                bbox = (
                    int(data["left"][i]),
                    int(data["top"][i]),
                    int(data["width"][i]),
                    int(data["height"][i]),
                )
                words.append(OcrWord(text=t, confidence=conf, bbox=bbox))
            mean = sum(confs) / len(confs) if confs else None
            return OcrResult(text=text, confidence=mean, words=words)

        # Provider/binary errors (e.g. TesseractNotFoundError) propagate so the
        # service can treat them as non-fatal per-page failures.
        return await asyncio.to_thread(_recognize)


__all__ = ["TesseractOcrAdapter"]
