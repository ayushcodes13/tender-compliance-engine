"""DOCX-specific upload validation.

A DOCX is a ZIP container. ZIP magic bytes alone are insufficient because an
arbitrary archive renamed to .docx must not enter the document pipeline.
This rule verifies the minimum Office Open XML package structure without
extracting files or executing embedded content.
"""

from __future__ import annotations

import io
import logging
import zipfile

from tender_compliance_api.errors import PROCESSING_STAGE_FAILURE
from tender_compliance_api.validation.rules import FileValidationRule

logger = logging.getLogger(__name__)

_REQUIRED_PARTS = frozenset({"[Content_Types].xml", "word/document.xml"})
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024


class DocxValidationRule(FileValidationRule):
    """Reject malformed, non-DOCX, or suspiciously large OOXML containers."""

    name = "docx"

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        if not data.startswith(b"PK\x03\x04"):
            return []

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > _MAX_ARCHIVE_ENTRIES:
                    return ["DOCX contains too many archive entries"]

                names = {info.filename for info in infos}
                missing = _REQUIRED_PARTS - names
                if missing:
                    return [
                        "DOCX package is missing required parts: "
                        + ", ".join(sorted(missing))
                    ]

                total_uncompressed = sum(info.file_size for info in infos)
                if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
                    return [
                        "DOCX uncompressed content exceeds the safety limit "
                        f"({_MAX_UNCOMPRESSED_BYTES} bytes)"
                    ]
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            logger.warning("DOCX validation rejected document (%s)", type(exc).__name__)
            return [PROCESSING_STAGE_FAILURE]

        return []
