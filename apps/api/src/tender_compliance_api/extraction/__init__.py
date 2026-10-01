"""Structured extraction: schema, adapter port, providers, and prompts (CP25–26).

Phase 1 boundary: model output is bounded by the CP25 schema and the
:class:`~tender_compliance_api.extraction.adapter.LlmAdapter` port — a
provider-agnostic seam so swapping providers does not rewrite services (CP26,
"changing providers does not require rewriting document services").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tender_compliance_api.extraction.adapter import (
    ExtractResult,
    LlmAdapter,
    LlmCallConfig,
    LlmCallError,
    LlmCallResult,
)
from tender_compliance_api.extraction.chunking import SourceWindow, build_source_windows
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter
from tender_compliance_api.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionResponse,
)
from tender_compliance_api.extraction.schema import (
    CandidateValidationError,
    LocationType,
    RequirementCandidate,
    RequirementType,
    SourcedRequirementCandidate,
    TrustedSourceContext,
    UncertaintyLevel,
)

if TYPE_CHECKING:  # pragma: no cover - re-export only
    from tender_compliance_api.db.models import DocumentPage  # noqa: F401

__all__ = [
    "CandidateValidationError",
    "EXTRACTION_SYSTEM_PROMPT",
    "ExtractResult",
    "ExtractionResponse",
    "FakeLlmAdapter",
    "LlmAdapter",
    "LlmCallConfig",
    "LlmCallError",
    "LlmCallResult",
    "LocationType",
    "OpenAiLlmAdapter",
    "PROMPT_VERSION",
    "RequirementCandidate",
    "RequirementType",
    "SCHEMA_VERSION",
    "SourceWindow",
    "SourcedRequirementCandidate",
    "build_source_windows",
    "TrustedSourceContext",
    "UncertaintyLevel",
]
