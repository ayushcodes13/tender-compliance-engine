"""Data models for file-upload validation (CP13).

Defines the file-format enum, the immutable :class:`ValidationResult`
returned by every rule, and :class:`FileValidationError` for when
validation cannot proceed at all (e.g. empty upload).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class FileFormat(enum.StrEnum):
    """Supported primary source document formats.

    Phase 1 starts with PDF only; additional formats (DOCX, images) are
    added by later checkpoints.
    """

    PDF = "pdf"


# Magic bytes for each supported format.
MAGIC_BYTES: dict[FileFormat, bytes] = {
    FileFormat.PDF: b"%PDF-",
}

# Expected MIME type for each supported format.
MIME_TYPES: dict[FileFormat, str] = {
    FileFormat.PDF: "application/pdf",
}

# Allowed file extensions per format.
ALLOWED_EXTENSIONS: dict[FileFormat, set[str]] = {
    FileFormat.PDF: {".pdf"},
}


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a single uploaded file.

    Attributes:
        valid: ``True`` when the file passed all hard rules.
        errors: Fatal problems — the file must be rejected.
        warnings: Non-fatal observations (e.g. MIME mismatch) that do not
            block processing on their own.
        detected_format: The inferred :class:`FileFormat`, or ``None``
            when the signature did not match any known format.
        detected_content_type: The content type inferred from the file
            signature (authoritative, not browser-supplied).
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_format: FileFormat | None = None
    detected_content_type: str | None = None


class FileValidationError(Exception):
    """Raised when the upload payload is structurally unusable."""
