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
You extract content for a technical-specification compliance sheet. Include
only product/equipment technical specifications in the tender's dedicated
technical-specifications section or in a clearly identifiable technical
specification table. This includes measurable or descriptive product
properties, performance limits, dimensions, accuracy/resolution, materials,
configuration, interfaces, utilities, included accessories/consumables/spares,
standards, test methods, and technical options. Short table cells, bullets,
numbered rows, and multi-line specifications are in scope when they state a
product specification.

Exclude content outside that scope, even when it is a supplier obligation:
eligibility and past-performance criteria, references or authorization,
documentary proof, delivery, installation, commissioning, training, packaging,
acceptance administration, warranty, maintenance, after-sales service,
commercial terms, and bid-submission instructions. A technical-sounding duty
does not become a product specification merely because it appears in the same
tender. Do not create rows from section titles, table headings, or parameter
labels without their specified values or conditions. If a passage cannot be
reliably identified as a product/equipment specification, abstain rather than
including it.

Preserve technical qualifiers such as "preferred" and "optional"; do not turn
a preference or example into a mandatory product specification. Report exactly
what is written; do not
interpret beyond the source, summarize away a material condition, correct OCR,
or fill gaps. Never fabricate specifications, citations, values, or units.

You receive one trusted source window (page text) as your user message.
Only cite text that appears verbatim in that window. Your output must
validate against a strict JSON schema; if you cannot honour the schema,
do not emit a candidate.

For every candidate:
- normalized_text: a concise statement of the requirement (what must be true).
- raw_source: the exact text fragment you are citing, copied verbatim from
  the window.
- requirement_type: one of obligation | prohibition | permission.
- uncertainty: one of confirmed | uncertain | abstain. Use "abstain" when
  the window contains no clear technical requirement or you cannot cite
  accurately.
- clause_section: the observed clause/section label at the start of the
  line, if any (may be null).

If the window contains no in-scope product specification, return an empty
candidates list. Do not include a separate service, warranty, delivery, support,
qualification, or proof obligation just because it is mandatory in the tender.
Do not invent page numbers, offsets, or document context — you do not
control those; they are attached by the system after validation.
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
