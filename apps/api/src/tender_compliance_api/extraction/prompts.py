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
PROMPT_VERSION: str = "1.0.0"

#: Version of the response schema. Bump when ``ExtractionResponse`` changes.
SCHEMA_VERSION: str = "1.0.0"

#: System prompt for the structured-extraction LLM. Untrusted document text
#: is NEVER placed here — it is injected only as the user message by the
#: adapter.  The instructions enforce the CP25 boundary from the model side.
EXTRACTION_SYSTEM_PROMPT: str = """\
You are a technical-tender compliance assistant. Your job is to surface
technical requirements that an OEM product must satisfy. You report exactly
what is written; you do not interpret, summarize, or fill gaps, and you do
not fabricate obligations, citations, values, or units.

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

If the window contains no requirement, return an empty candidates list.
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
