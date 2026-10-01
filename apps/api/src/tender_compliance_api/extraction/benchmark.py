"""Curated Phase 1 benchmark dataset loader and parser runner (CP43).

This module provides the data model and loading logic for the benchmark
dataset that lives under ``tests/fixtures/benchmark/``.  The dataset is the
single source of truth for extraction quality evaluation (CP44 and later
checkpoints).

Design notes (per AGENTS.md):
- Pure module: no database, no network, no LLM.  Only file system reads for
  fixture loading and the deterministic ``parse_constraint`` /
  ``parse_qualitative_conditions`` functions for parser execution.
- The annotation format (operator labels like ``"max"``, state names like
  ``"confirmed"``) is intentionally human-friendly and **distinct** from the
  internal code representations (``ConstraintOperator.LESS_THAN_OR_EQUAL``,
  ``ConstraintNormalizationState.SAFE``).  The
  :data:`ANNOTATION_TO_OPERATOR` and :data:`ANNOTATION_TO_STATE` maps bridge
  the two so the eval harness (CP44) can compare apples to apples.
- Never fabricate: cases whose source text yields no constraints are
  legitimate (``negative`` categories, vague prose).  The parser runner
  faithfully records whatever the parser produces, including empty results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tender_compliance_api.extraction.constraint_parser import parse_constraint
from tender_compliance_api.extraction.qualitative import (
    conservative_normalized_text,
    parse_qualitative_conditions,
)

# ---------------------------------------------------------------------------
# Annotation → code mappings
# ---------------------------------------------------------------------------

#: Maps the human-friendly operator labels used in ``expected.json`` to the
#: :class:`ConstraintOperator` enum values used by the parser.
ANNOTATION_TO_OPERATOR: dict[str, str] = {
    "max": "<=",
    "min": ">=",
    "less_than": "<",
    "greater_than": ">",
    "exact": "=",
    "range": "between",
    "not_equal": "!=",
}

#: Reverse mapping: code operator → annotation label.
OPERATOR_TO_ANNOTATION: dict[str, str] = {
    v: k for k, v in ANNOTATION_TO_OPERATOR.items()
}

#: Maps the human-friendly normalization-state labels used in ``expected.json``
#: to the :class:`ConstraintNormalizationState` string values.
ANNOTATION_TO_STATE: dict[str, str] = {
    "confirmed": "safe",
    "partial": "partial",
    "needs_review": "needs_review",
}

#: Reverse mapping: code state → annotation label.
STATE_TO_ANNOTATION: dict[str, str] = {
    v: k for k, v in ANNOTATION_TO_STATE.items()
}

#: Maps human-friendly review-state labels to the
#: :class:`RequirementReviewState` string values.
ANNOTATION_TO_REVIEW_STATE: dict[str, str] = {
    "unreviewed": "unreviewed",
    "reviewed": "reviewed",
    "needs_clarification": "needs_clarification",
    "ocr_warning": "ocr_warning",
}

#: Maps human-friendly requirement-type labels to code values.
ANNOTATION_TO_REQUIREMENT_TYPE: dict[str, str] = {
    "obligation": "obligation",
    "prohibition": "prohibition",
    "permission": "permission",
}

# ---------------------------------------------------------------------------
# Dataset model
# ---------------------------------------------------------------------------

#: Default root for the benchmark fixtures.
DEFAULT_DATASET_ROOT = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "benchmark"
)


@dataclass(frozen=True)
class BenchmarkConstraint:
    """A single annotated constraint (numeric or qualitative).

    Mirrors the JSON schema in ``expected.json`` files.  ``operator``,
    ``normalization_state``, and ``qualitative_condition`` are nullable — a
    qualitative constraint has ``qualitative_condition`` set and
    ``operator``/``numeric_value``/``unit`` as ``null``.
    """

    parameter: str
    operator: str | None  # annotation label (e.g. "max", "range", "exact")
    numeric_value: float | None
    unit: str | None
    tolerance: float | None
    lower_bound: float | None
    upper_bound: float | None
    qualitative_condition: str | None
    normalization_state: str  # annotation label: "confirmed" / "partial" / "needs_review"
    raw_fragment: str
    raw_value_lexical: str | None = None


@dataclass(frozen=True)
class BenchmarkSource:
    """A single source anchor for a benchmark requirement."""

    page_number: int
    char_start: int | None = None
    char_end: int | None = None
    location_type: str = "approximate"  # "exact" or "approximate"
    source_text: str | None = None


@dataclass(frozen=True)
class BenchmarkRequirement:
    """A single annotated requirement from an expected.json file."""

    normalized_text: str
    raw_source: str
    clause_number: str | None
    requirement_type: str
    constraints: list[BenchmarkConstraint] = field(default_factory=list)
    uncertainty: str = "confirmed"  # "confirmed" | "uncertain" | "abstain"
    expected_review_state: str = "unreviewed"
    source: BenchmarkSource | None = None
    sources: list[BenchmarkSource] = field(default_factory=list)  # multi-page

    @property
    def all_sources(self) -> list[BenchmarkSource]:
        """Return all source anchors, preferring ``sources`` if present."""
        if self.sources:
            return self.sources
        if self.source is not None:
            return [self.source]
        return []


@dataclass(frozen=True)
class BenchmarkCase:
    """A single benchmark case (directory + source + expected)."""

    case_id: str
    category: str  # "gold-positive" | "gold-negative"
    tags: list[str]
    description: str
    source_text: str
    raw_expected: dict[str, Any]
    requirements: list[BenchmarkRequirement] = field(default_factory=list)
    page_count: int = 1

    @property
    def is_gold_negative(self) -> bool:
        return self.category == "gold-negative"


@dataclass(frozen=True)
class BenchmarkDataset:
    """The entire curated benchmark dataset."""

    dataset_id: str
    version: str
    description: str
    cases: list[BenchmarkCase]
    root: Path


# ---------------------------------------------------------------------------
# JSON → dataclass parsing
# ---------------------------------------------------------------------------

def _parse_constraint(d: dict[str, Any]) -> BenchmarkConstraint:
    return BenchmarkConstraint(
        parameter=d["parameter"],
        operator=d.get("operator"),
        numeric_value=d.get("numeric_value"),
        unit=d.get("unit"),
        tolerance=d.get("tolerance"),
        lower_bound=d.get("lower_bound"),
        upper_bound=d.get("upper_bound"),
        qualitative_condition=d.get("qualitative_condition"),
        normalization_state=d.get("normalization_state", "confirmed"),
        raw_fragment=d.get("raw_fragment", ""),
        raw_value_lexical=d.get("raw_value_lexical"),
    )


def _parse_source(d: dict[str, Any]) -> BenchmarkSource:
    return BenchmarkSource(
        page_number=d.get("page_number", 1),
        char_start=d.get("char_start"),
        char_end=d.get("char_end"),
        location_type=d.get("location_type", "approximate"),
        source_text=d.get("source_text"),
    )


def _parse_requirement(d: dict[str, Any]) -> BenchmarkRequirement:
    constraints = [_parse_constraint(c) for c in d.get("constraints", [])]
    src = d.get("source")
    srcs = d.get("sources")
    source = _parse_source(src) if src else None
    sources = [_parse_source(s) for s in srcs] if srcs else []
    return BenchmarkRequirement(
        normalized_text=d.get("normalized_text", ""),
        raw_source=d.get("raw_source", ""),
        clause_number=d.get("clause_number"),
        requirement_type=d.get("requirement_type", "obligation"),
        constraints=constraints,
        uncertainty=d.get("uncertainty", "confirmed"),
        expected_review_state=d.get("expected_review_state", "unreviewed"),
        source=source,
        sources=sources,
    )


def _count_pages(text: str) -> int:
    """Count the number of pages in source text (form-feed separated)."""
    if "\f" in text:
        return text.count("\f") + 1
    return 1


def _split_pages(text: str) -> list[str]:
    """Split source text into pages by form-feed character.

    When a form-feed (``\\f``) boundary falls in the middle of a token
    (e.g. a number or word that wraps across pages), the last token of
    the preceding page is often repeated verbatim at the start of the
    next page — a common PDF-extraction artefact.  This function
    deduplicates such boundary repeats so that, e.g., ``85\\f85 °C``
    becomes ``85 °C`` rather than ``85 85 °C`` (which the number parser
    would flag as an ambiguous space-separated group).
    """

    if "\f" not in text:
        return [text]

    pages = text.split("\f")
    # Deduplicate boundary repeats: if the last non-whitespace token of
    # page N equals the first non-whitespace token of page N+1, strip the
    # duplicate from page N+1.
    _boundary_repeat = re.compile(
        r"^(?P<first>\S+)"  # first token of next page
        r"(?P<rest>\s+\S.*)?$",
        re.DOTALL,
    )
    for i in range(len(pages) - 1):
        cur = pages[i].rstrip()
        nxt = pages[i + 1].lstrip()
        cur_tokens = cur.split()
        nxt_m = _boundary_repeat.match(nxt)
        if cur_tokens and nxt_m:
            last_cur = cur_tokens[-1]
            if _strip_num_marker(last_cur) == _strip_num_marker(nxt_m.group("first")):
                pages[i + 1] = (nxt_m.group("rest") or "").lstrip()
    return pages


def _strip_num_marker(tok: str) -> str:
    """Normalise a boundary token for comparison (strip common OCR/mark
    artefacts like trailing punctuation)."""

    return tok.rstrip(".,;:").lower()


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_dataset(root: Path | None = None) -> BenchmarkDataset:
    """Load the full benchmark dataset from disk.

    Args:
        root: Path to the benchmark directory.  Defaults to
            ``tests/fixtures/benchmark``.

    Returns:
        A :class:`BenchmarkDataset` with all cases loaded and parsed.
    """

    dataset_root = Path(root) if root else DEFAULT_DATASET_ROOT
    meta_path = dataset_root / "dataset.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"dataset.json not found at {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    cases: list[BenchmarkCase] = []
    for case_meta in meta["cases"]:
        case_id = case_meta["case_id"]
        source_path = dataset_root / case_meta["source_file"]
        expected_path = dataset_root / case_meta["expected_file"]

        source_text = source_path.read_text(encoding="utf-8")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        requirements = [
            _parse_requirement(r) for r in expected.get("requirements", [])
        ]

        cases.append(
            BenchmarkCase(
                case_id=case_id,
                category=case_meta["category"],
                tags=case_meta.get("tags", []),
                description=case_meta.get("description", ""),
                source_text=source_text,
                raw_expected=expected,
                requirements=requirements,
                page_count=_count_pages(source_text),
            )
        )

    return BenchmarkDataset(
        dataset_id=meta["dataset_id"],
        version=meta["version"],
        description=meta.get("description", ""),
        cases=cases,
        root=dataset_root,
    )


# ---------------------------------------------------------------------------
# Parser runner — produces structured output from a case's source text
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedBenchmarkConstraint:
    """A constraint produced by running the parser on a benchmark case.

    ``operator`` is the code-level operator string (e.g. ``"<="``), and
    ``normalization_state`` is the code-level state string (e.g. ``"<="``).
    These are mapped back to annotation labels by the eval harness (CP44)
    via :data:`OPERATOR_TO_ANNOTATION` and :data:`STATE_TO_ANNOTATION`.
    """

    parameter: str
    operator: str | None
    numeric_value: float | None
    unit: str | None
    tolerance: float | None
    lower_bound: float | None
    upper_bound: float | None
    qualitative_condition: str | None
    normalization_state: str  # code-level: "safe" | "partial" | "needs_review"
    raw_fragment: str
    raw_value_lexical: str | None
    issues: tuple[str, ...] = ()
    source_type: str = "numeric"  # "numeric" or "qualitative"


@dataclass(frozen=True)
class ParsedBenchmarkResult:
    """The structured output of running the parser on a benchmark case."""

    case_id: str
    pages: list[str]
    numeric_constraints: list[ParsedBenchmarkConstraint]
    qualitative_conditions: list[ParsedBenchmarkConstraint]
    normalized_text: str
    has_ocr_warning: bool = False

    @property
    def all_constraints(self) -> list[ParsedBenchmarkConstraint]:
        return list(self.numeric_constraints) + list(self.qualitative_conditions)


def run_parser_on_case(case: BenchmarkCase, *, ocr_warning: bool = False) -> ParsedBenchmarkResult:
    """Run the deterministic parser on a benchmark case's source text.

    Splits the source text on form-feed (``\\f``) into pages, then runs
    :func:`parse_constraint` and :func:`parse_qualitative_conditions` on each
    page's text.  The ``raw_source`` for each requirement is the full
    per-page text (each page is treated as a potential requirement unit).

    this is a **pure** function — no database, no network — so it can be
    called from tests and the eval harness alike.
    """

    pages = _split_pages(case.source_text)
    all_numeric: list[ParsedBenchmarkConstraint] = []
    all_qualitative: list[ParsedBenchmarkConstraint] = []

    # Join pages into a single text after boundary deduplication (handled
    # in _split_pages).  This ensures requirements that span page breaks
    # — where the unit may sit on the next page — are parsed as a whole,
    # mirroring how the LLM would extract the full requirement fragment
    # in the real pipeline.
    full_text = " ".join(p.strip() for p in pages if p.strip())
    if not full_text:
        return ParsedBenchmarkResult(
            case_id=case.case_id,
            pages=pages,
            numeric_constraints=[],
            qualitative_conditions=[],
            normalized_text="",
            has_ocr_warning=False,
        )

    # Numeric constraints (CP33).
    for pc in parse_constraint(full_text, ocr_warning=ocr_warning):
        all_numeric.append(
            ParsedBenchmarkConstraint(
                parameter=pc.parameter,
                operator=pc.operator,
                numeric_value=pc.numeric_value,
                unit=pc.unit,
                tolerance=pc.tolerance,
                lower_bound=pc.lower_bound,
                upper_bound=pc.upper_bound,
                qualitative_condition=None,
                normalization_state=pc.normalization_state.value,
                raw_fragment=pc.raw_fragment,
                raw_value_lexical=pc.raw_value_lexical,
                issues=pc.issues,
                source_type="numeric",
            )
        )

    # Qualitative conditions (CP34).
    for qc in parse_qualitative_conditions(full_text, ocr_warning=ocr_warning):
        all_qualitative.append(
            ParsedBenchmarkConstraint(
                parameter=qc.parameter,
                operator=None,
                numeric_value=None,
                unit=None,
                tolerance=None,
                lower_bound=None,
                upper_bound=None,
                qualitative_condition=qc.condition,
                normalization_state=qc.normalization_state.value,
                raw_fragment=qc.raw_fragment,
                raw_value_lexical=None,
                issues=qc.issues,
                source_type="qualitative",
                )
            )

    normalized = conservative_normalized_text(
        "\f".join(pages)
    )

    return ParsedBenchmarkResult(
        case_id=case.case_id,
        pages=pages,
        numeric_constraints=all_numeric,
        qualitative_conditions=all_qualitative,
        normalized_text=normalized,
        has_ocr_warning=ocr_warning,
    )


def get_expected_constraints(req: BenchmarkRequirement) -> list[BenchmarkConstraint]:
    """Convenience: flatten a requirement's expected constraints."""

    return req.constraints


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
    "OPERATOR_TO_ANNOTATION",
    "ParsedBenchmarkConstraint",
    "ParsedBenchmarkResult",
    "STATE_TO_ANNOTATION",
    "load_dataset",
    "run_parser_on_case",
]
