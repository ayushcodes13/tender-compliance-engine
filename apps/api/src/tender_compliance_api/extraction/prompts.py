"""Extraction prompt versioning and the LLM response schema (CP26).

The system prompt and response schema are versioned so that an
:class:`~tender_compliance_api.extraction.adapter.LlmCallResult` always
identifies the exact configuration a candidate was produced under — a core
CP26 verification requirement.  The response schema reuses
:class:`~tender_compliance_api.extraction.schema.RequirementCandidate` so
model output is bounded by the CP25 boundary contract.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from tender_compliance_api.extraction.schema import RequirementCandidate

#: Version of the extraction system prompt. Bump on any instruction change.
PROMPT_VERSION: str = "1.10.0"

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
  on the explicit source wording. A product specification listed in the
  selected section is an obligation even when phrased as a descriptive
  equipment feature rather than with "shall" or "must".
- uncertainty: one of confirmed | uncertain | abstain. Use "confirmed" when
  the fragment is clearly legible and belongs to a listed specification or
  technical subsection. Use "uncertain" only when source wording or its
  relationship to the listed row is ambiguous. Use "abstain" only when it
  cannot be copied accurately; never emit partial fragments as candidates.
- group_hint: preserve the response-sheet row label or parent subsection
  heading that groups this fragment. Sibling details that belong in one
  response-sheet row must use the same parent label and be emitted together.

Preserve the row boundaries shown by the source and the supplied examples:
- A standalone numbered heading such as "1. Growth chamber" is its own row
  when it appears separately. Do not attach its following lettered rows to it.
- Under a section heading, separately lettered specification rows (a), b),
  c), etc.) are separate candidates. Never merge sibling lettered rows,
  including under headings such as "Technical Parameters" or "Other
  important requirements".
- Keep the full text belonging to one labeled row together, including wrapped
  lines and unlabeled continuation paragraphs up to the next peer row label.
  Do not split one row just because it has multiple sentences or paragraphs.
- Preserve grouped bullets as one candidate when the examples show a named
  parent row grouping them. This includes accessory/model lists grouped under
  labels such as "Grips and Fixtures", "Additional Testing Systems", and
  "Extensometer and Measurement", plus the grouped "Other requirements" and
  grouped technical/terms subsections in the supplied examples. Keep every
  nested item and exact source phrase in that group.
- In the Universal Testing Machine example, keep the unnumbered feature bullets
  under "Universal Testing Machine (300 kN)" together, including keyboard
  entry and power supply details. Under "Accessories and Attachments", keep
  Wide Frame Option, Dual Station Configuration, and Load Cells together in
  one grouped candidate. Keep HG300D-200, LC50kN, PR9+SJ1, Win Test Analysis,
  and VE-XS1/M5+RCE-25 as the five following named grouped candidates. Keep the
  contents of "Additional Technical Specifications" and "Terms & Conditions"
  together in their respective candidates as the sample does.
- In the diamond-scriber example, keep each named instrument/accessory row
  intact and combine the nested bullets under the single "Other requirements"
  row as shown in the supplied response sheet.
- A heading and its children are separate rows when the examples show the
  heading as a standalone row. Do not combine all items under headings such
  as "Utilities/spares" or "Sources/Manufactures" merely because they share
  a section.
- If an item continues on the next page without a new peer row label, keep
  the continuation with that item when the source text is contiguous and the
  boundary is unambiguous. Never fill missing wording from context in another
  window.
- clause_section: the observed source label, if any (may be null).

If no technical specification is present in the supplied window, return an
empty candidates list. Never fabricate an item, citation, page, offset, value,
unit, or document context; trusted source locations are attached after
validation.
"""

_LETTERED_ROW_RE = re.compile(r"(?m)^\s*[a-z]\)\s+\S", re.I)
_BULLET_RE = re.compile(r"(?m)^\s*[•▪◦-]\s+\S")


def system_prompt_for_source_window(source_text: str) -> str:
    """Add a deterministic row-grouping instruction from visible source form.

    The supplied examples use two real structures: individually lettered
    specification rows (Example 2), and grouped bullet/table rows under named
    parents (Examples 1 and 3). Do not ask the model to reconcile both patterns
    with a single grouping rule.
    """
    lettered_rows = _LETTERED_ROW_RE.findall(source_text)
    bullet_rows = _BULLET_RE.findall(source_text)
    if len(lettered_rows) >= 2:
        return (
            EXTRACTION_SYSTEM_PROMPT
            + "\nROW STRUCTURE FOR THIS SOURCE WINDOW:\n"
            + "The window contains multiple explicit lettered sibling rows. "
            "Emit the standalone numbered/section heading as its own row when "
            "present, then exactly one candidate per lettered row. Do not merge "
            "sibling letters. Keep wrapped/unlabeled continuations and nested "
            "bullets with their lettered parent up to the next peer letter."
        )
    if len(bullet_rows) >= 2:
        return (
            EXTRACTION_SYSTEM_PROMPT
            + "\nROW STRUCTURE FOR THIS SOURCE WINDOW:\n"
            + "The window contains a grouped bullet or table-style specification. "
            "Follow named parent rows and source table groupings from the supplied "
            "examples. Keep related unnumbered bullets together under their "
            "parent row; do not emit one candidate per bullet when the bullets "
            "form one grouped response-sheet row. Preserve separate named groups."
        )
    return EXTRACTION_SYSTEM_PROMPT


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
    "system_prompt_for_source_window",
]
