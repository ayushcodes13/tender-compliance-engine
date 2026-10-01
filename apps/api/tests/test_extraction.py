"""Tests for CP25: structured extraction schema + trusted source-window boundary.

Covers the machine-enforced boundary between a model-suggested
:class:`RequirementCandidate` (not persistable — and cannot carry a page/
version) and a :class:`SourcedRequirementCandidate` (candidate + a
service-attached :class:`TrustedSourceContext`), including rejection of
missing sources, malformed enums/structures, and citations that would move a
candidate to a different page/document.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tender_compliance_api.extraction import (
    CandidateValidationError,
    LocationType,
    RequirementCandidate,
    RequirementType,
    SourcedRequirementCandidate,
    TrustedSourceContext,
    UncertaintyLevel,
)


def _candidate(**over: object) -> RequirementCandidate:
    base: dict[str, object] = dict(
        normalized_text="shall be painted RAL 9005",
        raw_source="painted RAL 9005",
        requirement_type=RequirementType.OBLIGATION,
        uncertainty=UncertaintyLevel.CONFIRMED,
        clause_section="7.3",
        group_hint=None,
    )
    base.update(over)
    return RequirementCandidate(**base)  # type: ignore[arg-type]


def _ctx(**over: object) -> TrustedSourceContext:
    base: dict[str, object] = {
        "organization_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "document_version_id": uuid.uuid4(),
        "page_number": 1,
        "clause_number": None,
        "char_start": None,
        "char_end": None,
        "bbox": None,
        "ocr_confidence": 0.9,
        "location_type": LocationType.EXACT,
        "source_text": "The handrail shall be painted RAL 9005 matte.",
    }
    base.update(over)
    return TrustedSourceContext(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RequirementCandidate (model-owned: no trusted location fields)
# ---------------------------------------------------------------------------


class TestRequirementCandidate:
    def test_valid_candidate(self) -> None:
        c = _candidate()
        assert c.normalized_text == "shall be painted RAL 9005"
        assert c.requirement_type is RequirementType.OBLIGATION
        assert c.uncertainty is UncertaintyLevel.CONFIRMED

    def test_model_candidate_cannot_carry_a_page(self) -> None:
        # The boundary: a bare candidate has NO trusted-location fields, so
        # the model cannot attach or move a page/version.
        assert "page_number" not in RequirementCandidate.model_fields
        assert "document_version_id" not in RequirementCandidate.model_fields
        assert "char_start" not in RequirementCandidate.model_fields
        assert not (
            {"page_number", "document_version_id", "source_text", "bbox"}
            & set(RequirementCandidate.model_fields)
        )

    def test_extra_field_rejected(self) -> None:
        # Malformed structure (model trying to set page_number) -> rejected.
        with pytest.raises(ValidationError):
            RequirementCandidate(
                normalized_text="x",
                raw_source="x",
                requirement_type=RequirementType.PERMISSION,
                uncertainty=UncertaintyLevel.CONFIRMED,
                page_number=2,
            )

    @pytest.mark.parametrize("blank", ["  ", "", "\t\n"])
    def test_blank_normalized_text_rejected(self, blank: str) -> None:
        with pytest.raises(ValidationError):
            _candidate(normalized_text=blank)

    def test_blank_raw_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _candidate(raw_source="")

    def test_unknown_requirement_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementCandidate(
                normalized_text="x",
                raw_source="x",
                requirement_type="obligash",  # malformed enum
                uncertainty=UncertaintyLevel.CONFIRMED,
            )

    def test_unknown_uncertainty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementCandidate(
                normalized_text="x",
                raw_source="x",
                requirement_type=RequirementType.PERMISSION,
                uncertainty="maybe",
            )


# ---------------------------------------------------------------------------
# TrustedSourceContext (service-owned; built from a parsed DocumentPage)
# ---------------------------------------------------------------------------


class TestTrustedSourceContext:
    def test_required_fields_enforced(self) -> None:
        # document_version_id is mandatory; source_text is nullable.
        with pytest.raises(ValidationError):
            TrustedSourceContext(
                organization_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                # document_version_id intentionally omitted
            )

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _ctx(pages=3)

    def test_from_page_builds_trusted_window(self) -> None:
        org = uuid.uuid4()
        doc = uuid.uuid4()
        version = uuid.uuid4()
        page = SimpleNamespace(
            document_version_id=version,
            page_number=3,
            ocr_confidence=0.81,
            cleaned_text="Surface prep shall be done before painting RAL 9005.",
        )
        ctx = TrustedSourceContext.from_page(
            page, org, doc, clause_number="5.1"
        )
        assert ctx.organization_id == org
        assert ctx.document_id == doc
        assert ctx.document_version_id == version
        assert ctx.page_number == 3
        assert ctx.clause_number == "5.1"
        assert ctx.ocr_confidence == 0.81
        assert ctx.source_text == "Surface prep shall be done before painting RAL 9005."
        # location defaults to approximate when not specified.
        assert ctx.location_type is LocationType.APPROXIMATE

    def test_from_page_accepts_explicit_source_window(self) -> None:
        page = SimpleNamespace(
            document_version_id=uuid.uuid4(),
            page_number=2,
            ocr_confidence=None,
            cleaned_text="ignored default window",
        )
        ctx = TrustedSourceContext.from_page(
            page, uuid.uuid4(), uuid.uuid4(), source_text="explicit window text"
        )
        assert ctx.source_text == "explicit window text"
        assert ctx.ocr_confidence is None


# ---------------------------------------------------------------------------
# SourcedRequirementCandidate — the machine-enforced boundary
# ---------------------------------------------------------------------------


class TestSourcedBoundary:
    def test_confirmed_candidate_is_persistable(self) -> None:
        s = SourcedRequirementCandidate(candidate=_candidate(), source=_ctx())
        assert s.is_persistable() is True

    def test_source_text_required(self) -> None:
        # No trusted window text -> the citation boundary cannot be validated.
        ctx = _ctx(source_text=None)
        sourced = SourcedRequirementCandidate(
            candidate=_candidate(), source=ctx
        )
        with pytest.raises(CandidateValidationError):
            sourced.validate_source()
        assert sourced.is_persistable() is False

    def test_candidate_must_be_submitted_with_source(self) -> None:
        # A bare candidate has no trusted source -> not a SourcedCandidate.
        with pytest.raises(ValidationError):
            SourcedRequirementCandidate(candidate=_candidate())  # type: ignore[call-arg]

    def test_model_cannot_move_candidate_to_different_page(self) -> None:
        # The candidate cites text that only exists on page 2, but the trusted
        # window is page 1's text -> the boundary rejects the citation.
        ctx = _ctx(
            page_number=1,
            source_text="Only page one content lives here and nowhere else.",
        )
        cand = _candidate(
            raw_source="page two content",  # not present in page 1 window
        )
        sourced = SourcedRequirementCandidate(candidate=cand, source=ctx)
        with pytest.raises(CandidateValidationError):
            sourced.validate_source()
        assert sourced.is_persistable() is False

    def test_whitespace_tolerant_citation(self) -> None:
        # Insignificant whitespace differences are tolerated; the citation
        # is still verified against the trusted window.
        ctx = _ctx(
            source_text="The handrail shall be painted  RAL 9005 matte."
        )
        cand = _candidate(raw_source="painted   RAL 9005")
        s = SourcedRequirementCandidate(candidate=cand, source=ctx)
        assert s.is_persistable() is True

    def test_uncertain_is_not_persistable(self) -> None:
        cand = _candidate(uncertainty=UncertaintyLevel.UNCERTAIN)
        s = SourcedRequirementCandidate(candidate=cand, source=_ctx())
        assert s.is_persistable() is False

    def test_abstain_is_not_persistable(self) -> None:
        cand = _candidate(uncertainty=UncertaintyLevel.ABSTAIN)
        # An abstain candidate still must cite real text (no fabricated page),
        # but it is never persistable.
        s = SourcedRequirementCandidate(candidate=cand, source=_ctx())
        assert s.is_persistable() is False
