"""Extraction prompt versioning and the LLM response schema (CP26).

The system prompt and response schema are versioned so that an
:class:`~tender_compliance_api.extraction.adapter.LlmCallResult` always
identifies the exact configuration a candidate was produced under — a core
CP26 verification requirement.  The response schema reuses
:class:`~tender_compliance_api.extraction.schema.RequirementCandidate` so
model output is bounded by the CP25 boundary contract.
"""

from __future__ import annotations

from pydantic import BaseModel

from tender_compliance_api.extraction.schema import RequirementCandidate

#: Version of the extraction system prompt. Bump on any instruction change.
PROMPT_VERSION: str = "1.3.0"

#: Version of the response schema. Bump when ``ExtractionResponse`` changes.
SCHEMA_VERSION: str = "1.0.0"

#: System prompt for the structured-extraction LLM. Untrusted document text
#: is NEVER placed here — it is injected only as the user message by the
#: adapter.  The instructions enforce the CP25 boundary from the model side.
EXTRACTION_SYSTEM_PROMPT: str = """\
You extract the technical specifications explicitly present in the selected
technical-specification or technical-compliance section of a tender. The
application supplies source windows only from that selected section. Do not
use, infer from, or add material from any other part of the tender.

Reproduce specification text exactly as it appears in the source window. Do
not paraphrase, summarize, explain, assess compliance, recommend, correct OCR,
or add values, units, conditions, tolerances, or technical details. Keep the
original numbering, terminology, punctuation, bullets, and qualifiers such as
"preferred" and "optional". Keep complete table rows and their nested bullets
together when they express one listed item. Keep source qualifiers such as
"or another reputable supplier" exactly as written. Preserve service, support, and
other requirements only when they are inside the selected technical section;
their presence elsewhere in the tender does not make them in scope.

You receive one trusted source window from the selected section. Only cite
text that appears verbatim in that window. Your output must validate against a
strict JSON schema; if you cannot honour the schema, do not emit a candidate.

For every candidate:
- normalized_text: the exact same text as raw_source; do not rewrite it.
- raw_source: the complete exact source fragment for one listed requirement,
  specification row, or nested bullet group.
- requirement_type: one of obligation | prohibition | permission, based only
  on the explicit source wording.
- uncertainty: one of confirmed | uncertain | abstain. Use "abstain" when the
  source wording is unclear or cannot be copied accurately.
- clause_section: the observed source label, if any (may be null).

If no technical specification is present in the supplied window, return an
empty candidates list. Never fabricate an item, citation, page, offset, value,
unit, or document context; trusted source locations are attached after
validation.
"""


class ExtractionResponse(BaseModel):
    """The schema an LLM provider must parse its output into.

    The adapter requests structured output matching this model (e.g. OpenAI
    ``response_format=ExtractionResponse``).  Each candidate is bounded by
    the CP25 :class:`RequirementCandidate` schema.
    """

    model_config = {"extra": "forbid"}

    candidates: list[RequirementCandidate] = []


__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "ExtractionResponse",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
]
