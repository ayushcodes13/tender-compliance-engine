"""Data models for file-upload validation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class FileFormat(enum.StrEnum):
    """Supported source document formats."""

    PDF = "pdf"
    DOCX = "docx"


DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

MAGIC_BYTES: dict[FileFormat, bytes] = {
    FileFormat.PDF: b"%PDF-",
    FileFormat.DOCX: b"PK\x03\x04",
}

MIME_TYPES: dict[FileFormat, str] = {
    FileFormat.PDF: "application/pdf",
    FileFormat.DOCX: DOCX_MIME_TYPE,
}

ALLOWED_EXTENSIONS: dict[FileFormat, set[str]] = {
    FileFormat.PDF: {".pdf"},
    FileFormat.DOCX: {".docx"},
}


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one untrusted upload."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_format: FileFormat | None = None
    detected_content_type: str | None = None


class FileValidationError(Exception):
    """Raised when the upload payload is structurally unusable."""
