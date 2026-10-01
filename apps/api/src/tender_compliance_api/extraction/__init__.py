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
from tender_compliance_api.extraction.benchmark import (
    ANNOTATION_TO_OPERATOR,
    ANNOTATION_TO_REQUIREMENT_TYPE,
    ANNOTATION_TO_REVIEW_STATE,
    ANNOTATION_TO_STATE,
    OPERATOR_TO_ANNOTATION,
    STATE_TO_ANNOTATION,
    BenchmarkCase,
    BenchmarkConstraint,
    BenchmarkDataset,
    BenchmarkRequirement,
    BenchmarkSource,
    ParsedBenchmarkConstraint,
    ParsedBenchmarkResult,
    load_dataset,
    run_parser_on_case,
)
from tender_compliance_api.extraction.chunking import SourceWindow, build_source_windows
from tender_compliance_api.extraction.constraint_parser import (
    ConstraintOperator,
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.diagnostics import (
    ExtractionDiagnosticsSummary,
    compute_diagnostics,
)
from tender_compliance_api.extraction.eval_harness import (
    CaseEvalResult,
    EvalConfig,
    EvalReport,
    QualityGate,
    check_quality_gates,
    format_text_report,
    run_eval,
)
from tender_compliance_api.extraction.extractor import (
    CandidateRecord,
    ExtractionOutcome,
    extract_from_windows,
)
from tender_compliance_api.extraction.fake import FakeLlmAdapter
from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter
from tender_compliance_api.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionResponse,
)
from tender_compliance_api.extraction.qualitative import (
    NORMALIZATION_VERSION,
    QualitativeCondition,
    conservative_normalized_text,
    parse_qualitative_conditions,
)
from tender_compliance_api.extraction.reconcile import (
    DECISION_DEDUP,
    DECISION_FLAGGED,
    DECISION_SINGLETON,
    ReconciliationGroup,
    ReconciliationInput,
    ReconciliationResult,
    reconcile,
)
from tender_compliance_api.extraction.requirement import (
    PromotionInput,
    ResolvedSource,
    promotion_key,
    resolve_sources,
    to_promotion_input,
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
    "ANNOTATION_TO_OPERATOR",
    "ANNOTATION_TO_REQUIREMENT_TYPE",
    "ANNOTATION_TO_REVIEW_STATE",
    "ANNOTATION_TO_STATE",
    "BenchmarkCase",
    "BenchmarkConstraint",
    "BenchmarkDataset",
    "BenchmarkRequirement",
    "BenchmarkSource",
    "CaseEvalResult",
    "STATE_TO_ANNOTATION",
    "OPERATOR_TO_ANNOTATION",
    "EvalConfig",
    "EvalReport",
    "QualityGate",
    "ParsedBenchmarkConstraint",
    "ParsedBenchmarkResult",
    "SourceWindow",
    "load_dataset",
    "run_parser_on_case",
    "run_eval",
    "check_quality_gates",
    "format_text_report",
    "CandidateRecord",
    "CandidateValidationError",
    "compute_diagnostics",
    "ConstraintOperator",
    "ExtractionDiagnosticsSummary",
    "DECISION_DEDUP",
    "DECISION_FLAGGED",
    "DECISION_SINGLETON",
    "EXTRACTION_SYSTEM_PROMPT",
    "ExtractResult",
    "ExtractionOutcome",
    "ExtractionResponse",
    "FakeLlmAdapter",
    "LlmAdapter",
    "LlmCallConfig",
    "LlmCallError",
    "LlmCallResult",
    "LocationType",
    "OpenAiLlmAdapter",
    "PROMPT_VERSION",
    "NORMALIZATION_VERSION",
    "ParsedConstraint",
    "PromotionInput",
    "QualitativeCondition",
    "ReconciliationGroup",
    "ReconciliationInput",
    "ReconciliationResult",
    "RequirementCandidate",
    "RequirementType",
    "ResolvedSource",
    "SCHEMA_VERSION",
    "SourcedRequirementCandidate",
    "TrustedSourceContext",
    "UncertaintyLevel",
    "build_source_windows",
    "conservative_normalized_text",
    "extract_from_windows",
    "parse_constraint",
    "parse_qualitative_conditions",
    "promotion_key",
    "reconcile",
    "resolve_sources",
    "to_promotion_input",
]
