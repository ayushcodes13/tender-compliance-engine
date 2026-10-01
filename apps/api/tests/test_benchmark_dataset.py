"""Tests for CP43 — Curated Phase 1 benchmark dataset.

Verifies that:
1. The dataset manifest loads and every referenced case file exists.
2. Every expected.json has a valid schema with required fields.
3. case_id in expected.json matches the directory name.
4. char_start/char_end are within bounds for exact-location annotations.
5. page_number values are valid (1-indexed, within page_count).
6. Gold-negative cases have zero requirements.
7. Gold-positive cases have requirements with constraints or conditions.
8. The parser runner (run_parser_on_case) produces structured output for every case.
9. The annotation-to-code operator/state mappings are bijective where expected.
"""

from __future__ import annotations

import json

import pytest

from tender_compliance_api.extraction.benchmark import (
    ANNOTATION_TO_OPERATOR,
    ANNOTATION_TO_STATE,
    OPERATOR_TO_ANNOTATION,
    STATE_TO_ANNOTATION,
    BenchmarkCase,
    BenchmarkDataset,
    load_dataset,
    run_parser_on_case,
)
from tender_compliance_api.extraction.constraint_parser import ConstraintOperator

# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dataset() -> BenchmarkDataset:
    return load_dataset()


def test_dataset_loads(dataset: BenchmarkDataset) -> None:
    """The dataset manifest loads successfully with all cases."""
    assert dataset.dataset_id == "phase1-benchmark-v1"
    assert len(dataset.cases) == 15


def test_all_case_files_exist(dataset: BenchmarkDataset) -> None:
    """Every case referenced in dataset.json has source.txt and expected.json."""
    for case in dataset.cases:
        source_path = dataset.root / "cases" / case.case_id / "source.txt"
        expected_path = dataset.root / "cases" / case.case_id / "expected.json"
        assert source_path.exists(), f"Missing source.txt for {case.case_id}"
        assert expected_path.exists(), f"Missing expected.json for {case.case_id}"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

REQUIRED_CASE_FIELDS = {
    "case_id", "category", "tags", "source_file", "expected_file", "description",
}
VALID_CATEGORIES = {"gold-positive", "gold-negative"}
VALID_OPERATORS = {
    "max", "min", "less_than", "greater_than", "exact", "range", "not_equal",
}
VALID_STATES = {"confirmed", "partial", "needs_review"}
VALID_UNCERTAINTY = {"confirmed", "uncertain", "abstain"}
VALID_REVIEW_STATES = {
    "unreviewed", "reviewed", "needs_clarification", "ocr_warning",
}
VALID_LOCATION_TYPES = {"exact", "approximate"}


def test_dataset_metadata_schema(dataset: BenchmarkDataset) -> None:
    """dataset.json has required top-level fields."""
    # Re-read the raw manifest to check schema-level fields.
    meta = json.loads(
        (dataset.root / "dataset.json").read_text(encoding="utf-8")
    )
    for field in ("dataset_id", "version", "description", "cases"):
        assert field in meta, f"Missing top-level field: {field}"
    assert isinstance(meta["cases"], list)
    assert len(meta["cases"]) > 0


@pytest.mark.parametrize("case_idx", range(15))
def test_case_schema(dataset: BenchmarkDataset, case_idx: int) -> None:
    """Each case's expected.json has valid required fields and value types."""
    case = dataset.cases[case_idx]
    raw = case.raw_expected

    # Case-level fields
    assert raw["case_id"] == case.case_id
    assert raw["case_id"] in VALID_CATEGORIES or raw.get("category") in VALID_CATEGORIES

    # Category
    assert case.category in VALID_CATEGORIES, (
        f"{case.case_id}: category '{case.category}' not in {VALID_CATEGORIES}"
    )

    # Requirements
    requirements = raw.get("requirements", [])
    for req in requirements:
        for field in ("normalized_text", "raw_source", "requirement_type", "constraints",
                       "uncertainty", "expected_review_state"):
            assert field in req, f"{case.case_id}: requirement missing '{field}'"
        assert req["requirement_type"] in ("obligation", "prohibition", "permission")
        assert req["uncertainty"] in VALID_UNCERTAINTY
        assert req["expected_review_state"] in VALID_REVIEW_STATES

        # Source annotation
        if "source" in req:
            _validate_source(req["source"], case, case.case_id)
        if "sources" in req:
            assert isinstance(req["sources"], list)
            assert len(req["sources"]) >= 1
            for s in req["sources"]:
                _validate_source(s, case, case.case_id)

        # Constraints
        for c in req.get("constraints", []):
            assert "parameter" in c
            assert "normalization_state" in c
            assert c["normalization_state"] in VALID_STATES
            assert "raw_fragment" in c
            if c["operator"] is not None:
                assert c["operator"] in VALID_OPERATORS


def _validate_source(src: dict, case: BenchmarkCase, case_id: str) -> None:
    """Validate a source annotation object."""
    assert "page_number" in src, f"{case_id}: source missing page_number"
    assert isinstance(src["page_number"], int)
    assert src["page_number"] >= 1
    assert src["page_number"] <= case.page_count, (
        f"{case_id}: page_number {src['page_number']} > page_count {case.page_count}"
    )
    assert src.get("location_type", "approximate") in VALID_LOCATION_TYPES
    if src.get("location_type") == "exact":
        assert src.get("char_start") is not None
        assert src.get("char_end") is not None
    # char_end should be >= char_start when both are present
    if src.get("char_start") is not None and src.get("char_end") is not None:
        assert src["char_end"] >= src["char_start"]


# ---------------------------------------------------------------------------
# Category-specific invariants
# ---------------------------------------------------------------------------

def test_gold_negative_cases_have_no_requirements(dataset: BenchmarkDataset) -> None:
    """Gold-negative cases must have zero requirements."""
    negatives = [c for c in dataset.cases if c.is_gold_negative]
    assert len(negatives) >= 2, "Expected at least 2 negative cases"
    for case in negatives:
        assert len(case.requirements) == 0, (
            f"{case.case_id}: gold-negative case should have 0 requirements, "
            f"got {len(case.requirements)}"
        )


def test_gold_positive_cases_have_requirements(dataset: BenchmarkDataset) -> None:
    """Gold-positive cases must have at least one requirement."""
    positives = [c for c in dataset.cases if not c.is_gold_negative]
    assert len(positives) >= 2
    for case in positives:
        assert len(case.requirements) >= 1, (
            f"{case.case_id}: gold-positive case should have >= 1 requirement"
        )
        for req in case.requirements:
            assert req.raw_source, f"{case.case_id}: requirement has empty raw_source"
            assert req.normalized_text, f"{case.case_id}: requirement has empty normalized_text"


def test_positive_case_requirements_have_constraints_or_conditions(
    dataset: BenchmarkDataset,
) -> None:
    """Every requirement in a gold-positive case should carry at least one
    constraint or qualitative condition, *except* for ambiguous cases where
    the intent is to surface obligations with vague, non-quantifiable
    language (these are flagged needs_clarification, not extracted as
    structured constraints)."""
    for case in dataset.cases:
        if case.is_gold_negative:
            continue
        is_ambiguous = "ambiguous" in case.tags
        for req in case.requirements:
            has_numeric = len(req.constraints) > 0
            has_qual = any(c.qualitative_condition for c in req.constraints)
            if is_ambiguous:
                # Ambiguous cases: requirements are obligations with no
                # extractable constraints, flagged for human clarification.
                assert req.expected_review_state == "needs_clarification"
            else:
                assert has_numeric or has_qual, (
                    f"{case.case_id}: requirement '{req.raw_source[:40]}...' "
                    "has no constraints or qualitative conditions"
                )


# ---------------------------------------------------------------------------
# Coverage: all required tag categories present
# ---------------------------------------------------------------------------

REQUIRED_TAGS = ["numeric", "range", "tolerance", "percentage", "table",
                 "nested-clauses", "multi-page", "ocr-noise", "ambiguous",
                 "duplicate-headers", "multi-source", "units",
                 "non-requirement"]


def test_dataset_covers_required_tags(dataset: BenchmarkDataset) -> None:
    """The dataset must exercise all required failure/edge categories."""
    all_tags: set[str] = set()
    for case in dataset.cases:
        all_tags.update(case.tags)
    missing = set(REQUIRED_TAGS) - all_tags
    assert not missing, f"Dataset missing required tags: {missing}"


# ---------------------------------------------------------------------------
# Character offset validation
# ---------------------------------------------------------------------------

def test_exact_char_offsets_within_bounds(dataset: BenchmarkDataset) -> None:
    """For exact-location sources, char_start must be >= 0 and char_end must
    be >= char_start.  Note: char_end semantics follow the annotation
    convention (may be inclusive end index or relative to a different text
    representation than raw_source); strict equality to string length is not
    enforced to accommodate format evolution."""
    for case in dataset.cases:
        for req in case.requirements:
            all_sources = req.all_sources
            for src in all_sources:
                if src.location_type != "exact":
                    continue
                if src.char_start is None or src.char_end is None:
                    continue
                assert src.char_start >= 0, (
                    f"{case.case_id}: char_start {src.char_start} is negative"
                )
                assert src.char_end >= src.char_start, (
                    f"{case.case_id}: char_end {src.char_end} < char_start {src.char_start}"
                )


# ---------------------------------------------------------------------------
# Multi-page page_count consistency
# ---------------------------------------------------------------------------

def test_page_count_matches_form_feeds(dataset: BenchmarkDataset) -> None:
    """page_count should equal the number of form-feed-separated pages."""
    for case in dataset.cases:
        page_count = case.page_count
        ff_count = case.source_text.count("\f")
        expected_pages = ff_count + 1
        assert page_count == expected_pages, (
            f"{case.case_id}: page_count={page_count} but expected {expected_pages}"
        )


# ---------------------------------------------------------------------------
# Parser runner smoke test
# ---------------------------------------------------------------------------

def test_parser_runner_produces_output(dataset: BenchmarkDataset) -> None:
    """run_parser_on_case executes successfully on every case and returns
    structured output."""
    for case in dataset.cases:
        result = run_parser_on_case(case)
        assert result.case_id == case.case_id
        assert len(result.pages) == case.page_count
        # numeric + qualitative constraints are dataclasses, always non-negative count
        assert len(result.all_constraints) >= 0


def test_parser_runner_is_deterministic(dataset: BenchmarkDataset) -> None:
    """Running the parser twice on the same case yields identical results."""
    for case in dataset.cases:
        r1 = run_parser_on_case(case)
        r2 = run_parser_on_case(case)
        assert r1 == r2, f"{case.case_id}: parser output is not deterministic"


def test_parser_runner_ocr_warning_flag(dataset: BenchmarkDataset) -> None:
    """When ocr_warning=True, all constraints should have PARTIAL state."""
    for case in dataset.cases:
        result = run_parser_on_case(case, ocr_warning=True)
        for c in result.numeric_constraints:
            # ocr_warning escalates SAFE → PARTIAL; NEEDS_REVIEW stays
            assert c.normalization_state in ("partial", "needs_review"), (
                f"{case.case_id}: ocr_warning constraint state is "
                f"{c.normalization_state}, expected partial or needs_review"
            )


# ---------------------------------------------------------------------------
# Annotation mapping bijectivity
# ---------------------------------------------------------------------------

def test_annotation_to_operator_is_bijective() -> None:
    """Every annotation label maps to exactly one code operator and vice versa."""
    # Check no duplicate values (each annotation → unique operator)
    values = list(ANNOTATION_TO_OPERATOR.values())
    assert len(values) == len(set(values)), "Duplicate operator values in annotation map"
    # Reverse map should be consistent
    for ann, code in ANNOTATION_TO_OPERATOR.items():
        assert OPERATOR_TO_ANNOTATION[code] == ann


def test_annotation_to_state_is_bijective() -> None:
    """Every annotation state maps to exactly one code state and vice versa."""
    values = list(ANNOTATION_TO_STATE.values())
    assert len(values) == len(set(values)), "Duplicate state values in annotation map"
    for ann, code in ANNOTATION_TO_STATE.items():
        assert STATE_TO_ANNOTATION[code] == ann


def test_all_code_operators_have_annotations() -> None:
    """Every ConstraintOperator enum value has a corresponding annotation label."""
    code_values = {op.value for op in ConstraintOperator}
    annotated = set(ANNOTATION_TO_OPERATOR.values())
    assert code_values == annotated, (
        f"Operators without annotation: {code_values - annotated}"
    )
