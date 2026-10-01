"""File-upload validation package (CP13).

Exports the :class:`ValidationService` orchestrator and the shared
:dataclass:`ValidationResult` model.
"""

from tender_compliance_api.validation.models import (
    ALLOWED_EXTENSIONS,
    MAGIC_BYTES,
    MIME_TYPES,
    FileFormat,
    FileValidationError,
    ValidationResult,
)
from tender_compliance_api.validation.service import ValidationService

__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAGIC_BYTES",
    "MIME_TYPES",
    "FileFormat",
    "FileValidationError",
    "ValidationResult",
    "ValidationService",
]
