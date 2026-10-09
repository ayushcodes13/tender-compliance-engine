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
PROMPT_VERSION: str = "1.2.0"

#: Version of the response schema. Bump when ``ExtractionResponse`` changes.
SCHEMA_VERSION: str = "1.0.0"

#: System prompt for the structured-extraction LLM. Untrusted document text
#: is NEVER placed here — it is injected only as the user message by the
#: adapter.  The instructions enforce the CP25 boundary from the model side.
EXTRACTION_SYSTEM_PROMPT: str = """\
You are a technical-tender compliance assistant. Surface every distinct,
explicit requirement that an OEM/supplier response sheet must address. This
includes product performance and configuration, equipment and accessories,
materials, interfaces, standards, tests, consumables and spares, as well as
supplier-delivered installation, integration, commissioning, training,
warranty, service, delivery/acceptance, and documentation requirements.
Also include explicit supplier capability requirements that the response sheet
must address, including prior supply/installation/commissioning experience,
minimum counts of similar systems, references, authorization, and requested
supporting evidence such as purchase orders, certificates, and reports. These
remain in scope when they appear under bidder/vendor qualification headings.
Include concise requirements from tables, bullets, numbered lists, and
multi-line clauses. A short or non-sentence table cell can still be a
requirement when its meaning is clear from the source window.

Stay within the tender's explicit scope: do not add procurement-process
instructions, generic bidder identity or ownership declarations,
bid-submission formatting, or evaluation criteria. Include a qualification
or eligibility clause only when the tender explicitly requires the supplier
to provide a capability, past-performance, authorization, reference, or
supporting-evidence response that belongs in the tender response sheet.
Preserve qualifiers such as "preferred", "optional", named examples, and
"or another reputable supplier"; do not turn a preference or example into a
mandatory brand or specification. Report exactly what is written; do not
interpret beyond the source, summarize away a material condition, correct OCR,
or fill gaps. Never fabricate obligations, citations, values, or units.

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

If the window contains no requirement that the supplier response must address,
return an empty candidates list. Do not omit a clear requirement merely because
it describes a service, an included item, a warranty/support condition, or a
permitted alternative rather than a numeric product specification.
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
