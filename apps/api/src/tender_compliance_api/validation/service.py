"""Upload validation orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from tender_compliance_api.validation.docx import DocxValidationRule
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

DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024


class ValidationService:
    """Run fail-closed validation for PDF and DOCX uploads."""

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
            DocxValidationRule(),
        ]
        if extra_rules:
            self._rules.extend(extra_rules)

    def validate(
        self, filename: str, content_type: str | None, data: bytes
    ) -> ValidationResult:
        errors: list[str] = []
        for rule in self._rules:
            errors.extend(rule.check(filename, content_type, data))

        detected_format: FileFormat | None = None
        detected_content_type: str | None = None
        for fmt, magic in MAGIC_BYTES.items():
            if data.startswith(magic):
                detected_format = fmt
                detected_content_type = MIME_TYPES[fmt]
                break

        return ValidationResult(
            valid=not errors,
            errors=errors,
            detected_format=detected_format,
            detected_content_type=detected_content_type,
        )
