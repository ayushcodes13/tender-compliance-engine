"""Structured extraction schemas and the trusted source-window boundary (CP25).

Phase 1 boundary rule (see AGENTS.md "Never fabricate" + CP25 guardrail):

A model-suggested :class:`RequirementCandidate` is **not** directly
persistable.  Only a :class:`SourcedRequirementCandidate` — a candidate
*plus* a service-attached :class:`TrustedSourceContext` that passes
machine validation — can graduate toward a domain requirement (CP30).

The model never controls version/page/window metadata: those live on
:class:`TrustedSourceContext`, which is constructed by the service from a
parsed :class:`~tender_compliance_api.db.models.DocumentPage` (or an
explicit source window).  A candidate's ``raw_source`` citation must be a
real substring of the trusted window text, so the model cannot relocate a
citation to a different page or document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    "LocationType",
    "RequirementCandidate",
    "RequirementType",
    "SourcedRequirementCandidate",
    "TrustedSourceContext",
    "UncertaintyLevel",
]
