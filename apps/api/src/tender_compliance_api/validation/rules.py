"""File-upload validation rules (CP13).

Each rule is a small, independently testable unit.  A rule inspects the
filename (extension), the browser-supplied content-type, and the actual
file bytes (signature), returning a list of error strings.  An empty
list means the rule passed.

Rules are designed to fail *closed*: if a signature does not match any
known format, the file is rejected regardless of the claimed extension
or MIME type.
"""

from __future__ import annotations

from pathlib import PurePath

from tender_compliance_api.validation.models import (
    ALLOWED_EXTENSIONS,
    MAGIC_BYTES,
    FileFormat,
)


class FileValidationRule:
    """Base class for file-validation rules.

    Subclasses implement :meth:`check` which receives the filename, the
    browser-supplied ``content_type``, and the raw file bytes, returning
    a list of error strings (empty list = pass).
    """

    name: str = "base"

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        raise NotImplementedError


class ExtensionRule(FileValidationRule):
    """Verify the file extension is in the allowed set."""

    name = "extension"

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        ext = PurePath(filename).suffix.lower()
        allowed: set[str] = set()
        for fmt in FileFormat:
            allowed.update(ALLOWED_EXTENSIONS[fmt])
        if ext not in allowed:
            return [
                f"File extension '{ext or '(none)'}' is not allowed. "
                f"Allowed: {sorted(allowed)}"
            ]
        return []


class FileSignatureRule(FileValidationRule):
    """Sniff the file signature (magic bytes) to infer the real format.

    Never trusts the browser-supplied MIME type.  If the signature does
    not match any known format, the file is rejected.
    """

    name = "signature"

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        if len(data) < 4:
            return ["File is too small to contain a valid header"]
        for _fmt, magic in MAGIC_BYTES.items():
            if data.startswith(magic):
                return []
        return [
            "File signature does not match any supported format "
            "(possible MIME mismatch or corrupted file)"
        ]


class FileSizeRule(FileValidationRule):
    """Reject files exceeding the maximum allowed size."""

    name = "size"

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    def check(
        self, filename: str, content_type: str | None, data: bytes
    ) -> list[str]:
        if len(data) > self._max_bytes:
            return [
                f"File size {len(data)} bytes exceeds the maximum "
                f"allowed {self._max_bytes} bytes"
            ]
        return []
