"""Concrete Pydantic schemas for the extraction boundary (CP25).

See :mod:`tender_compliance_api.extraction` for the boundary contract.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from tender_compliance_api.db.models import DocumentPage


class CandidateValidationError(ValueError):
    """A candidate failed the model->persistable boundary check.

    Raised when a :class:`SourcedRequirementCandidate` is constructed in a
    state that violates the trusted-source contract (e.g. a cited fragment
    that does not actually appear in the trusted window text).
    """


class RequirementType(StrEnum):
    """Deontic categorization of a requirement (strict; rejects unknown)."""

    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"


class UncertaintyLevel(StrEnum):
    """Tri-state confidence the model has in a candidate (mandatory).

    ``CONFIRMED`` candidates that pass the source boundary are persistable.
    ``UNCERTAIN`` candidates are routed for human review (CP35).  ``ABSTAIN``
    candidates are model self-rejections (CP28) and are not persistable.
    """

    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    ABSTAIN = "abstain"


class LocationType(StrEnum):
    """Whether a source anchor is exact (known offsets) or approximate."""

    EXACT = "exact"
    APPROXIMATE = "approximate"


_WS = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Collapse internal whitespace to single spaces and strip ends.

    Used so the citation-substring check is robust to insignificant
    whitespace differences between model output and the cleaned page text,
    while remaining deterministic.
    """

    return _WS.sub(" ", text).strip()


class RequirementCandidate(BaseModel):
    """A model-proposed requirement candidate.

    This is the *only* shape an upstream model (CP26) may emit.  It carries
    **no trusted source metadata** — version, page, offsets, and bbox are
    deliberately absent so the model cannot relocate a citation.  A bare
    candidate is not persistable; see :class:`SourcedRequirementCandidate`.
    """

    model_config = ConfigDict(extra="forbid")

    normalized_text: str
    raw_source: str
    requirement_type: RequirementType
    uncertainty: UncertaintyLevel
    # Nullable (not omitted): "when available" fields are explicitly None.
    clause_section: str | None = None
    group_hint: str | None = None

    @field_validator("normalized_text", "raw_source")
    @classmethod
    def _non_empty_str(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty, non-blank string")
        return value

    @property
    def has_trusted_location(self) -> bool:
        """Always False on a bare candidate (no trusted location is allowed)."""
        return False


class TrustedSourceContext(BaseModel):
    """Trusted, service-attached source location + window text.

    Every field is set by the application from parsed artifacts; the model
    never sees or controls these.  ``source_text`` is the trusted window the
    candidate's ``raw_source`` is checked against.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    page_number: int | None = None
    clause_number: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    window_char_start: int | None = None
    window_char_end: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    ocr_confidence: float | None = None
    location_type: LocationType = LocationType.APPROXIMATE
    source_text: str | None = None
    page_source_text: str | None = None

    @classmethod
    def from_page(
        cls,
        page: DocumentPage,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        clause_number: str | None = None,
        source_text: str | None = None,
        location_type: LocationType = LocationType.APPROXIMATE,
    ) -> TrustedSourceContext:
        """Build the trusted context from a parsed :class:`DocumentPage`.

        ``source_text`` defaults to the page's deterministic ``cleaned_text``
        (CP23); pass an explicit multi-page window for cross-page citations
        (CP27).  ``clause_number`` is the service-authoritative clause
        (from clause structure, not model claim) and defaults to ``None``
        until clause detection is wired.
        """

        return cls(
            organization_id=organization_id,
            document_id=document_id,
            document_version_id=page.document_version_id,
            page_number=page.page_number,
            clause_number=clause_number,
            # OCR confidence is a parser/OCR-level signal, never a model claim.
            ocr_confidence=getattr(page, "ocr_confidence", None),
            source_text=(
                source_text if source_text is not None else page.cleaned_text
            ),
            location_type=location_type,
        )


class SourcedRequirementCandidate(BaseModel):
    """The machine-enforced boundary between model suggestion and persistence.

    A required pairing of a :class:`RequirementCandidate` (model output) with
    a :class:`TrustedSourceContext` (service-set).  The *structural* boundary
    is enforced at construction: the candidate carries no page/version fields
    (so the model cannot relocate a citation), and a ``source`` is mandatory.

    The *citation* boundary — that ``raw_source`` actually appears in the
    trusted window text — is enforced by :meth:`validate_source` and the
    :meth:`is_persistable` gate.  Only instances that pass both can become a
    persisted requirement (CP30).
    """

    model_config = ConfigDict(extra="forbid")

    candidate: RequirementCandidate
    source: TrustedSourceContext

    def validate_source(self) -> None:
        """Enforce the citation-substring boundary.

        Raises :class:`CandidateValidationError` when the trusted window text
        is missing or the candidate's ``raw_source`` (whitespace-normalized)
        is not present in it.  This is the literal CP25 guarantee: a model
        cannot move a candidate to a different page/document by citing text
        that does not appear in the trusted source window.
        """

        if self.source.source_text is None:
            raise CandidateValidationError(
                "source.source_text is required to validate the candidate "
                "against the trusted window"
            )

        cited = _normalize_ws(self.candidate.raw_source)
        window = _normalize_ws(self.source.source_text)
        if cited not in window:
            raise CandidateValidationError(
                "candidate.raw_source is not present in the trusted source text "
                "(model cannot relocate a citation to another page/document)"
            )

    def is_persistable(self) -> bool:
        """Whether this candidate may be persisted as a requirement.

        Only ``CONFIRMED`` candidates that pass the source boundary
        (:meth:`validate_source`) are persistable.  ``UNCERTAIN`` is routed
        to human review (CP35); ``ABSTAIN`` is discarded by CP28.
        """
        if self.candidate.uncertainty is not UncertaintyLevel.CONFIRMED:
            return False
        try:
            self.validate_source()
        except CandidateValidationError:
            return False
        return True
