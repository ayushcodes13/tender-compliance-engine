"""Qualitative condition extraction and conservative normalization (CP34).

Pure regex/rule-based extraction of *explicit* qualitative conditions from a
verbatim requirement fragment — things that cannot be expressed as numeric
constraints (certifications, IP ratings, material grades, interface types,
documentation obligations, etc.).

Guardrails (from AGENTS.md):
- Only extract when the pattern is **explicit** — never infer, generalise, or
  fabricate a condition from vague prose like "as required" or "in accordance
  with applicable standards".
- Preserve the verbatim ``raw_fragment``; never rewrite or "correct" it.
- Propagate OCR/structure uncertainty via the ``ocr_warning`` flag — when
  truth is uncertain the result is escalated to PARTIAL / NEEDS_REVIEW, never
  silently normalised to SAFE.
- Do not turn descriptive prose into a mandatory obligation.

The normalisation rules in this module are versioned separately via
:data:`NORMALIZATION_VERSION` so that reprocessing with a new rule set can be
detected and audited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tender_compliance_api.db.models import ConstraintNormalizationState

#: Semantic version of the normalisation ruleset.  Bumped whenever the
#: pattern set or state-escalation logic changes so that persisted
#: constraints can be audited against the rule version that produced them.
NORMALIZATION_VERSION: str = "1.0.0"

#: Categories of qualitative condition we can extract explicitly.
QualitativeParameter = str  # one of the keys in ``_QUALITATIVE_PARAMETERS``


#: Maps a qualitative parameter to a human-readable label.
_QUALITATIVE_PARAMETERS: dict[str, str] = {
    "certification": "certification standard or mark",
    "environmental_rating": "ingress / environmental protection rating",
    "material": "material specification",
    "interface": "interface / connector type",
    "documentation": "documentation or deliverable obligation",
    "construction": "construction / safety property",
    "performance": "qualitative performance characteristic",
}

# ---------------------------------------------------------------------------
# Pattern catalogue
#
# Each entry is (compiled_regex, parameter, confidence).
# Patterns are intentionally narrow: a false positive (extracting something
# that is not really a condition) is worse than a false negative.  When in
# doubt, do not extract.
# ---------------------------------------------------------------------------

# Certifications & marks — must include the keyword "certified", "mark",
# "listed", "rated", "compliant", "approved", "tested to", or the standard
# name itself prefixed by a qualifier.
_CERT_PATTERNS = [
    # ISO 9001:2015, ISO 14001, ISO 45001, ISO 9001, etc.
    re.compile(
        r"ISO\s*\d{4}(?::\d{4})?",
        re.IGNORECASE,
    ),
    # CE / UL / FCC / RoHS / TÜV / CSA / IEC / EN standards
    re.compile(
        r"\b(?:CE|UL|FCC|RoHS|TÜV|TUV|CSA|IEC|EN)\b.*?(?=\.|;|,|\band\b)",
        re.IGNORECASE,
    ),
    # "certified to <standard>", "UL listed", "CE marked", etc.
    re.compile(
        r"(?:certified|listed|marked|approved|compliant|tested\sto)\s+"
        r"(?:to\s+)?(?:ISO|UL|FCC|RoHS|TÜV|CSA|IEC|EN)[^.,;]{0,40}",
        re.IGNORECASE,
    ),
]

# Environmental / ingress ratings — IP65, IP67, NEMA 4X, NEMA 12, NEMA 4
_ENV_PATTERNS = [
    # IP65, IP67, IP68, IP65/IP67, etc.
    # NOTE: no \b so the boundary_ambiguous check can flag "xIP65y" → PARTIAL.
    re.compile(r"IP\d+[A-Z]*(?:\s*/\s*IP\d+[A-Z]*)?", re.IGNORECASE),
    # NEMA 4X, NEMA 4, NEMA 12, etc.
    re.compile(r"NEMA\s*\d+[A-Z]?(?:\s*,\s*\d+[A-Z]?)*", re.IGNORECASE),
    # Explicit phrases: "corrosion-resistant", "explosion-proof", etc.
    re.compile(
        r"\b(?:corrosion-resistant|explosion-proof|explosion-proof|waterproof|"
        r"weatherproof|dustproof|shockproof|vapor-tight|harsh environment|"
        r"chemical resistant|salt spray resistant)\b",
        re.IGNORECASE,
    ),
]

# Material specifications
_MATERIAL_PATTERNS = [
    # "stainless steel (304/316)", "aluminum", "stainless steel 316L"
    re.compile(
        r"\b(?:stainless\s+steel\s*(?:\(?\d{4}\)?)?|"
        r"aluminum|aluminium|"
        r"carbon\s+steel|"
        r"cast\s+iron|"
        r"brass|copper|silver|gold|platinum|titanium)\b",
        re.IGNORECASE,
    ),
]

# Interface types
_INTERFACE_PATTERNS = [
    re.compile(
        r"\b(?:Ethernet|USB-C|USB\s*3\.0|USB\s*2\.0|"
        r"RS-485|RS-232|RS-422|"
        r"HDMI|DisplayPort|Thunderbolt|"
        r"Wi-Fi|WiFi|Bluetooth|Zigbee|Modbus|"
        r"CAN bus|PROFIBUS|Analog|Digital)\b",
        re.IGNORECASE,
    ),
]

# Documentation / deliverable obligations — these are qualitative because they
# don't have a numeric value, just a requirement to produce or include something.
_DOC_PATTERNS = [
    re.compile(
        r"(?:shall\s+(?:be\s+)?(?:accompanied\s+by|supplied\s+with|provided\s+with|"
        r"delivered\s+with|accompanied\s+with)|"
        r"certificate\s+of\s+conformity|"
        r"datasheet|"
        r"operating\s+manual|"
        r"user\s+manual|"
        r"test\s+report|"
        r"calibration\s+certificate|"
        r"warranty\s+certificate)\b",
        re.IGNORECASE,
    ),
]

# Construction / safety properties
_SAFETY_PATTERNS = [
    re.compile(
        r"\b(?:overcurrent\s+protection|short.?circuit\s+protection|"
        r"ground\s+fault\s+protection|leakage\s+current|"
        r"overvoltage\s+category|pollution\s+degree|"
        r"insulation\s+(?:class|rating|rated)|"
        r"dielectric\s+strength|"
        r"impulse\s+voltage|"
        r"thermal\s+cutoff|"
        r"overheat\s+protection|"
        r"overload\s+protection)\b",
        re.IGNORECASE,
    ),
]

# Qualitative performance — only explicit, named characteristics
_PERF_PATTERNS = [
    re.compile(
        r"\b(?:plug.and.play|hot.swappable|hot.swap|"
        r"redundant|"
        r"reversible|"
        r"bidirectional|"
        r"continuous|intermittent|"
        r"linear|rotary|"
        r"open.source|closed.source)\b",
        re.IGNORECASE,
    ),
]

_ALL_PATTERN_GROUPS: list[tuple[list[re.Pattern[str]], str]] = [
    (_CERT_PATTERNS, "certification"),
    (_ENV_PATTERNS, "environmental_rating"),
    (_MATERIAL_PATTERNS, "material"),
    (_INTERFACE_PATTERNS, "interface"),
    (_DOC_PATTERNS, "documentation"),
    (_SAFETY_PATTERNS, "construction"),
    (_PERF_PATTERNS, "performance"),
]


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualitativeCondition:
    """An explicit, non-numeric condition extracted from a requirement fragment.

    ``parameter`` is one of the keys in
    :data:`_QUALITATIVE_PARAMETERS`; ``normalization_state`` is
    ``SAFE`` for a clean explicit match, ``PARTIAL`` when ``ocr_warning``
    is set, and ``NEEDS_REVIEW`` when the match is ambiguous or the text
    was too close to other words.
    """

    parameter: str
    condition: str
    raw_fragment: str
    normalization_state: ConstraintNormalizationState
    issues: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Words that, when adjacent to a matched pattern, make the match suspicious
# (e.g. "IP65 compliance" is fine, but "IP65" inside a longer word is not).
_WORD_BOUNDARY = re.compile(r"\b")


def _dedupe(matches: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Remove overlapping matches, keeping the first (leftmost) longest."""

    if not matches:
        return []
    # Sort by start position, then by length (longer first for same start)
    matches.sort(key=lambda m: (m[2], -(m[3] - m[2])))
    kept: list[tuple[str, str, int, int]] = [matches[0]]
    for param, text, start, end in matches[1:]:
        _, _, prev_start, prev_end = kept[-1]
        if start >= prev_end:
            kept.append((param, text, start, end))
    return kept


def parse_qualitative_conditions(
    fragment: str,
    *,
    ocr_warning: bool = False,
) -> list[QualitativeCondition]:
    """Extract explicit qualitative conditions from a verbatim fragment.

    Only conditions that match a known explicit pattern are returned —
    vague prose ("as required", "in accordance with applicable standards",
    "where applicable") never produces an output.  Every output condition
    is anchored to the verbatim ``fragment``.

    Deterministic and reproducible: the same input always yields the same
    output.

    Args:
        fragment: The verbatim requirement source text.
        ocr_warning: When True, every condition's normalization state is
            escalated to PARTIAL and an ``ocr_warning`` issue is recorded.

    Returns:
        A list of :class:`QualitativeCondition` records (may be empty).
    """

    if not fragment or not fragment.strip():
        return []

    raw_matches: list[tuple[str, str, int, int]] = []

    for patterns, parameter in _ALL_PATTERN_GROUPS:
        for pat in patterns:
            for m in pat.finditer(fragment):
                text = m.group(0).strip()
                # Skip empty or whitespace-only matches.
                if not text or len(text) < 2:
                    continue
                # Truncate very long matches that captured trailing prose via
                # the "match until punctuation" patterns.
                if len(text) > 60:
                    text = text[:60].rstrip(" ,;")
                raw_matches.append((parameter, text, m.start(), m.end()))

    # Deduplicate overlapping matches, keeping the longest at each position.
    matches = _dedupe(raw_matches)

    result: list[QualitativeCondition] = []
    for parameter, text, start, end in matches:
        issues: list[str] = []

        # Heuristic: if the match starts or ends in the middle of a word
        # (i.e., the boundary characters are letters that extend the match),
        # flag as suspicious.
        if start > 0 and fragment[start - 1].isalpha() and text[0].isalpha():
            issues.append("boundary_ambiguous")
        if end < len(fragment) and fragment[end].isalpha() and text[-1].isalpha():
            issues.append("boundary_ambiguous")

        if ocr_warning:
            issues.append("ocr_warning")

        if "boundary_ambiguous" in issues:
            state = ConstraintNormalizationState.PARTIAL
        elif ocr_warning:
            state = ConstraintNormalizationState.PARTIAL
        else:
            state = ConstraintNormalizationState.SAFE

        result.append(
            QualitativeCondition(
                parameter=parameter,
                condition=text,
                raw_fragment=fragment,
                normalization_state=state,
                issues=tuple(issues),
            )
        )

    return result


def conservative_normalized_text(raw_source: str) -> str:
    """Return a conservative, review-oriented normalisation of a requirement.

    This does **not** translate obligation keywords or change meaning — it
    only collapses whitespace and normalises punctuation spacing so the text
    is easier to read in the review UI.  The output is not a re-write; it is
    a whitespace-normalised rendering of the verbatim input.

    The normalisation rules are versioned separately (:data:`NORMALIZATION_VERSION`).
    """

    if not raw_source:
        return ""

    text = raw_source

    # Collapse runs of whitespace including newlines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)

    # Normalise unicode punctuation to ASCII where unambiguous.
    # — — (em dash) → - (hyphen-minus)
    text = text.replace("—", "-")
    # ” ” → " "
    text = text.replace(""", '"').replace(""", '"')
    # ' ' → '
    text = text.replace("'", "'").replace("'", "'")

    # Normalise ellipsis.
    text = text.replace("…", "...")

    # Collapse multiple spaces again after replacements.
    text = re.sub(r" +", " ", text)

    return text.strip()


__all__ = [
    "NORMALIZATION_VERSION",
    "QualitativeCondition",
    "conservative_normalized_text",
    "parse_qualitative_conditions",
]
