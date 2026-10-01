"""Validation orchestration service (CP13).

Runs all registered :class:`FileValidationRule` instances against an
uploaded file and returns an aggregated :class:`ValidationResult`.

The service is synchronous in its public API (rules are CPU-bound);
the async upload route wraps the call in ``asyncio.to_thread`` when
needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from tender_compliance_api.validation.models import (
    MAGIC_BYTES,
    MIME_TYPES,
    FileFormat,
    ValidationResult,
)
from tender_compliance_api.validation.pdf import PdfValidationRule
from tender_compliance_api.validation.rules import (
    ExtensionRule,
    FileSignatureRule,
    FileSizeRule,
    FileValidationRule,
)

DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


class ValidationService:
    """Orchestrates file-validation rules.

    Args:
        max_bytes: Maximum allowed file size in bytes.
        max_pdf_pages: Maximum allowed PDF page count.
        extra_rules: Additional rules to run after the built-in set.
    """

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_pdf_pages: int = 500,
        extra_rules: Sequence[FileValidationRule] | None = None,
    ) -> None:
        self._rules: list[FileValidationRule] = [
            ExtensionRule(),
            FileSignatureRule(),
            FileSizeRule(max_bytes),
            PdfValidationRule(max_pages=max_pdf_pages),
        ]
        if extra_rules:
            self._rules.extend(extra_rules)

    def validate(
        self, filename: str, content_type: str | None, data: bytes
    ) -> ValidationResult:
        """Run all rules and return an aggregated result.

        Returns a :class:`ValidationResult` with ``valid=True`` when no
        rule reported a hard error.  The ``detected_format`` and
        ``detected_content_type`` fields are populated from the file
        signature, not the browser-supplied content type.
        """
        errors: list[str] = []

        for rule in self._rules:
            rule_errors = rule.check(filename, content_type, data)
            if rule_errors:
                errors.extend(rule_errors)

        # Infer format and content type from the signature.
        detected_format: FileFormat | None = None
        detected_content_type: str | None = None
        for fmt, magic in MAGIC_BYTES.items():
            if data.startswith(magic):
                detected_format = fmt
                detected_content_type = MIME_TYPES[fmt]
                break

        return ValidationResult(
            valid=(len(errors) == 0),
            errors=errors,
            detected_format=detected_format,
            detected_content_type=detected_content_type,
        )
