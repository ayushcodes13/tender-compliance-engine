"""Deterministic numeric/operator/unit parsing for constraints (CP33).

Pure, rule-based, **no LLM** (AGENTS guardrail: "Do not use an LLM as the final
authority for simple math parsing").  Given a requirement's verbatim
``raw_fragment``, extract the *obvious* mathematical structure — comparison
operators, ranges, percentages, scientific notation, units, and tolerances —
into typed :class:`ParsedConstraint` records, escalating anything ambiguous to
``PARTIAL`` / ``NEEDS_REVIEW`` rather than silently correcting it.

Design principles (from the checkpoint + AGENTS):

- **Never fabricate.** A number with no recognizable comparison operator (e.g.
  "RAL 9005") yields no constraint. A corrupted/ambiguous number yields no
  ``numeric_value`` (the lexical form is still preserved).
- **Preserve the lexical source form.** ``raw_value_lexical`` keeps the exact
  matched substring; parsed floats are derived from it, never the other way
  around.
- **Deterministic & conservative.** Decimal/thousands separators are only
  accepted when unambiguous; otherwise the value is flagged and left None.
- **Keep distinctions.** Ranges, tolerances, units, and per-constraint
  parameters are separate fields — never collapsed.
- **Escalate ambiguity.** OCR noise, ambiguous separators, unknown units, or
  corrupted glyphs mark the constraint ``PARTIAL`` or ``NEEDS_REVIEW`` so CP34
  / human review can resolve them.

The :func:`normalize_requirement_constraints` service method wires this parser to a
persisted :class:`~tender_compliance_api.db.models.Requirement` (tenant-scoped).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from tender_compliance_api.db.models import ConstraintNormalizationState

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class ConstraintOperator(enum.StrEnum):
    """Canonical comparison-operator symbols parsed from requirement text."""

    EQUALS = "="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    BETWEEN = "between"
    NOT_EQUAL = "!="


#: Surface forms -> canonical operator.  Order within each list is irrelevant
#: (matching is longest-surface-first via :func:`_op_alternation`).
_OP_SURFACE: dict[ConstraintOperator, list[str]] = {
    ConstraintOperator.LESS_THAN_OR_EQUAL: [
        "<=", "≤", "less than or equal to", "at most",
        "no more than", "not exceed", "does not exceed",
        "must not exceed", "shall not exceed",
        "not exceeding", "does not exceed",
        "not greater than", "no greater than",
    ],
    ConstraintOperator.GREATER_THAN_OR_EQUAL: [
        ">=", "≥", "greater than or equal to", "at least", "no less than",
        "not less than", "no lower than",
    ],
    ConstraintOperator.LESS_THAN: [
        "<", "less than", "below", "under", "fewer than", "lower than",
    ],
    ConstraintOperator.GREATER_THAN: [
        ">", "greater than", "more than", "above", "exceeds", "exceed", "over",
    ],
    ConstraintOperator.EQUALS: ["=", "equal to", "equals", "equal"],
    ConstraintOperator.NOT_EQUAL: ["!=", "≠", "not equal to", "other than"],
}


def _op_alternation() -> str:
    """Regex alternation of every operator surface form, longest first."""

    forms: list[str] = []
    for surfaces in _OP_SURFACE.values():
        forms.extend(surfaces)
    forms.sort(key=len, reverse=True)
    return "|".join(re.escape(s) for s in forms)


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

# Permissive raw number token (validated in `_parse_number`): optional sign,
# digits with optional comma/period grouping and internal spaces, optional
# decimal part, optional exponent.
_TOK_NUM = r"[-+]?(?:\d[\d,.\s]*\d|\d)(?:\.\d+)?(?:[eE][-+]?\d+)?|[-+]?\.\d+(?:[eE][-+]?\d+)?"

#: A unit token: degree-units, percent, or a short latin-letter run.
_UnitToken = re.compile(r"°[CFcf]|%|µ?[a-zA-Z²³µ°]+")


@dataclass(frozen=True)
class _ParsedNumber:
    """Result of validating a raw number token."""

    value: float | None  # None when ambiguous / OCR-corrupted (escalated)
    lexical: str  # verbatim matched substring
    state: ConstraintNormalizationState
    issues: tuple[str, ...]


def _parse_number(token: str, ocr_warning: bool) -> _ParsedNumber:
    """Parse a raw number token conservatively (see module docstring)."""

    lexical = token
    s = token.strip()
    if not s:
        return _ParsedNumber(
            None, lexical, ConstraintNormalizationState.PARTIAL, ("empty_number",)
        )

    has_comma = "," in s
    has_dot = "." in s
    has_space = re.search(r"\d\s+\d", s) is not None

    # Reject tokens containing letters (OCR corruption like "2O" or "Zkg" that
    # leaked into the number span), except the single 'e'/'E' of scientific
    # notation — those are validated by the float() parse below.
    core = s[1:] if s[0] in "+-" else s
    if re.search(r"[A-DF-Za-df-z]", core) and not re.fullmatch(
        r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|[-+]?\.\d+(?:[eE][-+]?\d+)?", s
    ):
        return _ParsedNumber(
            None, lexical, ConstraintNormalizationState.NEEDS_REVIEW,
            ("ocr_corrupted_number",),
        )

    if has_comma and has_dot:
        if s.rfind(".") > s.rfind(","):
            cleaned = s.replace(",", "")  # US/UK form, e.g. 1,234.5
        else:
            return _ParsedNumber(
                None, lexical, ConstraintNormalizationState.PARTIAL,
                ("ambiguous_decimal_thousands_separator",),
            )
    elif has_comma:
        parts = s.split(",")
        if all(len(p) == 3 for p in parts[1:]) and len(parts[0]) in (1, 2, 3):
            cleaned = s.replace(",", "")  # 1,234
        else:
            return _ParsedNumber(
                None, lexical, ConstraintNormalizationState.PARTIAL,
                ("ambiguous_comma_separator",),
            )
    elif has_space:
        parts = re.split(r"\s+", s.strip())
        if (
            all(p.isdigit() for p in parts)
            and all(len(p) == 3 for p in parts[1:])
            and len(parts[0]) in (1, 2, 3)
        ):
            cleaned = "".join(parts)  # 1 000 -> 1000
        else:
            return _ParsedNumber(
                None, lexical, ConstraintNormalizationState.PARTIAL,
                ("ambiguous_space_separator",),
            )
    else:
        cleaned = s

    try:
        value = float(cleaned)
    except ValueError:
        return _ParsedNumber(
            None, lexical, ConstraintNormalizationState.NEEDS_REVIEW,
            ("unparseable_number",),
        )

    issues: list[str] = []
    if ocr_warning:
        issues.append("ocr_warning")
    return _ParsedNumber(
        value=value,
        lexical=lexical,
        state=ConstraintNormalizationState.PARTIAL if ocr_warning else
        ConstraintNormalizationState.SAFE,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# Units & parameters
# ---------------------------------------------------------------------------

#: Units recognized as quantitative (unit -> physical quantity / parameter).
_UNIT_QUANTITY: dict[str, str] = {
    "kg": "mass", "g": "mass", "mg": "mass", "t": "mass",
    "ton": "mass", "tonne": "mass", "lb": "mass", "lbs": "mass", "oz": "mass",
    "°c": "temperature", "°f": "temperature", "c": "temperature", "f": "temperature",
    "°": "angle",
    "bar": "pressure", "kpa": "pressure", "mpa": "pressure", "pa": "pressure",
    "psi": "pressure", "atm": "pressure",
    "m": "length", "mm": "length", "cm": "length", "km": "length",
    "in": "length", "inch": "length", "inches": "length",
    "ft": "length", "mile": "length",
    "v": "voltage", "volts": "voltage", "kv": "voltage", "mv": "voltage",
    "a": "current", "amps": "current", "amp": "current", "ma": "current",
    "hz": "frequency", "khz": "frequency", "mhz": "frequency", "ghz": "frequency",
    "s": "time", "sec": "time", "seconds": "time",
    "ms": "time", "millisecond": "time", "milliseconds": "time",
    "minute": "time", "minutes": "time", "min": "time",
    "h": "time", "hour": "time", "hours": "time",
    "%": "percentage",
    "rad": "angle", "degrees": "angle",
}

#: Common measurement nouns preceding a unit-less number (parameter hint).
_NOUN_PARAM: dict[str, str] = {
    "weight": "mass", "weigh": "mass", "mass": "mass",
    "temperature": "temperature", "temp": "temperature",
    "pressure": "pressure",
    "length": "length", "distance": "length", "height": "length",
    "voltage": "voltage", "volts": "voltage",
    "current": "current", "amperes": "current", "amps": "current",
    "frequency": "frequency",
    "speed": "length/time", "velocity": "length/time",
    "time": "time", "duration": "time",
    "angle": "angle",
    "ratio": "percentage", "concentration": "percentage",
    "accuracy": "accuracy", "resolution": "resolution", "precision": "precision",
}

# Max length for a trailing unit token (longer runs are prose, not a unit).
_MAX_UNIT_LEN = 4


def _is_real_unit(token: str | None) -> str | None:
    """Return the unit token if it is short enough to be a real unit, else None.

    Long latin-letter runs after a number are almost always following prose
    ("seconds", "later", "mass") and must not be mistaken for a unit.
    A single "e" or "E" is rejected because it is the marker of scientific
    notation (e.g. ``1.2e-3``), not a unit — without this, the range matcher
    backtracks and mis-parses the exponent as a range separator.
    """

    if not token or len(token) > _MAX_UNIT_LEN:
        return None
    if token.lower() == "e":
        return None
    return token


def _quantity_for_unit(unit: str | None) -> str | None:
    """Map a recognized unit to its physical quantity (the constraint parameter)."""

    if unit is None:
        return None
    return _UNIT_QUANTITY.get(unit.lower())


def _parameter_from_noun(fragment: str, num_pos: int) -> str | None:
    """Best-effort parameter noun preceding a number (when no unit)."""

    before = fragment[:num_pos]
    tokens = re.findall(r"[A-Za-z]+(?:'[a-z]+)?", before)
    for tok in reversed(tokens[-4:]):
        if tok.lower() in _NOUN_PARAM:
            return _NOUN_PARAM[tok.lower()]
    return None


# ---------------------------------------------------------------------------
# Parsed constraint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedConstraint:
    """A single normalized constraint derived from a raw fragment (CP33).

    ``raw_fragment`` is the verbatim source text this constraint was parsed from
    (never synthesized).  ``raw_value_lexical`` preserves the exact number
    substring as it appeared in the source; ``numeric_value`` and the bounds are
    derived from it and are ``None`` when the value was ambiguous/OCR-corrupted
    (never a fabricated guess).
    """

    parameter: str
    operator: str
    numeric_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    unit: str | None
    tolerance: float | None
    raw_fragment: str
    raw_value_lexical: str
    normalization_state: ConstraintNormalizationState
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Tolerance:
    value: float
    lexical: str


# Range separators used between two numbers (allows "5-10", "5 to 10", "5..10").
_RANGE_SEP = r"\s*(?:and|through|to|–|-|\.\.)\s*"

# A number token plus an optional trailing unit (named groups reused by matchers).
_NUM_UNIT = rf"(?P<num>{_TOK_NUM})\s*(?:(?P<unit>{_UnitToken.pattern})?)"

# Comparison:  <op> <number> [unit].  The lookbehind prevents matching operator
# words / symbols that are embedded in other words (e.g. "exceed" inside
# "exceeds" is handled by alternation order; "transform" must not yield "from").
_CMP_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<op>{_op_alternation()})\s*{_NUM_UNIT}",
    re.IGNORECASE,
)

# Between / from X to Y [unit] — unit may attach to either bound or trail.
# "range of" is included so that "a temperature range of -10 °C to +55 °C"
# is captured (the minus sign on the lower bound is preserved because the
# number immediately follows the keyword, unlike bare _SPAN_RE which uses \b).
_BETWEEN_RE = re.compile(
    rf"\b(?:between|from|range\s+of)\s+(?P<lo>{_TOK_NUM})"
    rf"(?:\s*(?P<unit0>{_UnitToken.pattern}))?"
    rf"\s+(?:and|through|to|–|-|\.\.)\s+"
    rf"(?P<hi>{_TOK_NUM})"
    rf"(?:\s*(?P<unit1>{_UnitToken.pattern}))?"
    rf"(?:\s+(?P<unit>{_UnitToken.pattern}))?",
    re.IGNORECASE,
)

# Bare range:  A [unit] (and|to|–|-|..) B [unit]  — unit required somewhere
# (otherwise the numbers are likely page/clause refs, not measurements).
_SPAN_RE = re.compile(
    rf"\b(?P<lo>{_TOK_NUM})"
    rf"(?:\s*(?P<unit0>{_UnitToken.pattern}))?"
    rf"{_RANGE_SEP}"
    rf"(?:\s*(?P<unit1>{_UnitToken.pattern}))?\s*"
    rf"(?P<hi>{_TOK_NUM})"
    rf"\s*(?:(?P<unit>{_UnitToken.pattern}))?",
    re.IGNORECASE,
)

# Tolerance suffix: ± N | +/- N | "tolerance of N"  (leading \s* and optional
# punctuation so it matches after a unit like "kg ± 0.1" or "mm, ± 0.5").
_TOL_RE = re.compile(
    rf"\s*[，,]?\s*(?:±|tolerance\s+(?:of\s+)?)\s*(?P<tol>{_TOK_NUM})",
    re.IGNORECASE,
)

# Standalone tolerance specification: ±N [unit] at the start of a requirement
# (e.g. "the tolerance shall be ±2 %") with no preceding comparison operator.
# The lookbehind prevents matching ± that is already consumed as a tolerance
# suffix of a comparison/range constraint (those are handled by _TOL_RE above).
_TOL_STANDALONE_RE = re.compile(
    rf"(?<![⑊\d])(?:±|\+/-)\s*(?P<num>{_TOK_NUM})\s*"
    rf"(?:(?P<unit>{_UnitToken.pattern}))?",
    re.IGNORECASE,
)


def _canonicalize_op(surface: str) -> ConstraintOperator | None:
    """Map an operator surface form to its canonical operator."""

    low = surface.lower()
    for op, surfaces in _OP_SURFACE.items():
        if any(s.lower() == low for s in surfaces):
            return op
    return None


def _extract_tolerance(
    fragment: str, pos: int, ocr_warning: bool
) -> tuple[_Tolerance | None, tuple[int, int] | None]:
    """Match an optional ± tolerance immediately at ``pos``.

    Returns ``(tolerance, span)`` where ``span`` is the matched region so
    callers can register it in the ``used`` list (preventing the standalone
    tolerance extractor from re-matching the same ± token).
    """

    m = _TOL_RE.match(fragment, pos)
    if not m:
        return None, None
    parsed = _parse_number(m.group("tol"), ocr_warning)
    if parsed.value is None:
        return None, None
    return _Tolerance(value=parsed.value, lexical=parsed.lexical), m.span()


def _resolve_state(
    num: _ParsedNumber, ocr_warning: bool, extra: tuple[str, ...]
) -> ConstraintNormalizationState:
    """Escalate the numeric state per issue severity (never downgrade)."""

    if num.state is ConstraintNormalizationState.NEEDS_REVIEW:
        return ConstraintNormalizationState.NEEDS_REVIEW
    if ocr_warning and num.state is ConstraintNormalizationState.SAFE:
        return ConstraintNormalizationState.PARTIAL
    if extra:
        return ConstraintNormalizationState.PARTIAL
    return num.state


def _build(
    parameter: str,
    operator: ConstraintOperator,
    num: _ParsedNumber,
    *,
    lower: float | None = None,
    upper: float | None = None,
    unit: str | None,
    tolerance: _Tolerance | None,
    raw_fragment: str,
    raw_value_lexical: str,
    ocr_warning: bool,
    extra_issues: tuple[str, ...] = (),
) -> ParsedConstraint:
    """Assemble a ParsedConstraint, escalating state per issue severity."""

    issues: list[str] = list(num.issues) + list(extra_issues)
    if unit and _quantity_for_unit(unit) is None:
        issues.append("unknown_unit")
    if tolerance is not None:
        issues.append("tolerance")

    state = _resolve_state(num, ocr_warning, tuple(issues))
    value = num.value if operator is not ConstraintOperator.BETWEEN else None

    return ParsedConstraint(
        parameter=parameter,
        operator=operator.value,
        numeric_value=value,
        lower_bound=lower,
        upper_bound=upper,
        unit=unit,
        tolerance=tolerance.value if tolerance else None,
        raw_fragment=raw_fragment,
        raw_value_lexical=raw_value_lexical,
        normalization_state=state,
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_constraint(
    fragment: str,
    *,
    ocr_warning: bool = False,
) -> list[ParsedConstraint]:
    """Parse a verbatim requirement fragment into structured constraints.

    Returns zero or more :class:`ParsedConstraint` records.  A number with no
    recognizable comparison operator (e.g. "RAL 9005") yields **no** constraint —
    nothing is fabricated.  Ambiguous/OCR-corrupted numbers yield a constraint
    with ``numeric_value=None`` and ``PARTIAL``/``NEEDS_REVIEW`` state, still
    anchored to the verbatim ``raw_fragment``.

    Deterministic and reproducible: the same input always yields the same output.
    """

    if not fragment or not fragment.strip():
        return []

    used: list[tuple[int, int]] = []
    out: list[ParsedConstraint] = []

    # Ranges first (consumed spans exclude numbers from comparison parsing).
    for rx in (_BETWEEN_RE, _SPAN_RE):
        for m in rx.finditer(fragment):
            start, end = m.span()
            if any(s < end and e > start for s, e in used):
                continue
            used.append((start, end))
            lo_tok = m.group("lo")
            hi_tok = m.group("hi")
            # Guard against scientific-notation backtracking: when the regex
            # engine backtracks _TOK_NUM to drop its exponent, the exponent
            # letter "e"/"E" is left in unit0 and the "-" is consumed as a
            # range separator.  Detect this and skip the spurious range.
            unit0_tok = m.group("unit0")
            if unit0_tok and unit0_tok.lower() == "e":
                used.pop()
                continue
            unit = (
                _is_real_unit(m.group("unit"))
                or _is_real_unit(unit0_tok)
                or _is_real_unit(m.group("unit1"))
            )
            # A range without any unit is probably page/clause numbering, not a
            # measurement — refuse to fabricate a constraint from it (AGENTS:
            # never invent a requirement/citation).  Leave the span unconsumed.
            if unit is None:
                used.pop()
                continue
            qty = _quantity_for_unit(unit)
            # A range with a unit that is not a recognized measurement unit
            # (e.g. "Date", "Page", "as", "T") is almost certainly a false
            # positive from document metadata (reference numbers, page labels).
            # Refuse to fabricate a constraint from it (AGENTS: never invent
            # a requirement/citation).  Leave the span unconsumed.
            if qty is None:
                used.pop()
                continue
            # A hyphen-separated single-letter "unit" following a large number
            # is almost certainly a material/grade designation (e.g. "6061-T6",
            # "316L"), not a measurement range.  Refuse to fabricate.
            unit1_tok = m.group("unit1")
            sep_start = m.end("lo")
            if unit0_tok:
                sep_start = m.end("unit0")
            sep_text = fragment[sep_start:m.start("hi")]
            if unit1_tok and len(unit1_tok) == 1 and "-" in sep_text:
                used.pop()
                continue
            parameter = qty
            lo_num = _parse_number(lo_tok, ocr_warning)
            hi_num = _parse_number(hi_tok, ocr_warning)
            # Pick the "worse" state of the two bounds.
            if (
                lo_num.state is ConstraintNormalizationState.NEEDS_REVIEW
                or hi_num.state is ConstraintNormalizationState.NEEDS_REVIEW
            ):
                num_state = ConstraintNormalizationState.NEEDS_REVIEW
            elif (
                lo_num.state is ConstraintNormalizationState.PARTIAL
                or hi_num.state is ConstraintNormalizationState.PARTIAL
            ):
                num_state = ConstraintNormalizationState.PARTIAL
            else:
                num_state = ConstraintNormalizationState.SAFE
            num = _ParsedNumber(
                value=None,
                lexical=f"{lo_num.lexical}..{hi_num.lexical}",
                state=num_state,
                issues=lo_num.issues + hi_num.issues,
            )
            tol, tol_span = _extract_tolerance(fragment, end, ocr_warning)
            if tol_span is not None:
                used.append(tol_span)
            c = _build(
                parameter=parameter,
                operator=ConstraintOperator.BETWEEN,
                num=num,
                lower=lo_num.value,
                upper=hi_num.value,
                unit=unit,
                tolerance=tol,
                raw_fragment=fragment,
                raw_value_lexical=num.lexical,
                ocr_warning=ocr_warning,
            )
            out.append(c)

    # Single-value comparisons in whatever remains.
    for m in _CMP_RE.finditer(fragment):
        start, end = m.span()
        if any(s < end and e > start for s, e in used):
            continue
        op = _canonicalize_op(m.group("op").strip())
        if op is None:
            continue
        num_tok = m.group("num")
        unit_tok = m.group("unit")
        unit = _is_real_unit(unit_tok)

        # Detect OCR corruption: a digit immediately followed by a single
        # letter that is not a recognized unit (e.g. "8O" from "80").
        # _TOK_NUM stops at letters, so the OCR-corrupted number is split
        # into num="8" + unit="O".  _is_real_unit("O") returns "O" (single
        # char is short enough to "look" like a unit), but _quantity_for_unit
        # returns None because "O" is not a known quantity.  Re-parse the
        # merged token to catch the corruption.
        raw_value_lexical = num_tok
        if (
            unit_tok
            and len(unit_tok) == 1
            and unit is not None
            and _quantity_for_unit(unit) is None
            and m.start("unit") == m.end("num")  # no space between num and unit
        ):
            merged_tok = num_tok + unit_tok
            merged = _parse_number(merged_tok, ocr_warning)
            if merged.value is None:
                # OCR-corrupted number.  Try to find a real unit after it.
                after_pos = end  # end of the full _CMP_RE match (num + unit)
                after_text = fragment[after_pos:].lstrip()
                offset = len(fragment[after_pos:]) - len(after_text)
                um = _UnitToken.match(after_text)
                if um:
                    real_unit = _is_real_unit(um.group())
                    if real_unit is not None:
                        unit = real_unit
                        end = after_pos + offset + um.end()  # extend span
                        raw_value_lexical = merged_tok
                else:
                    unit = None
                    raw_value_lexical = merged_tok
                num = merged
                qty = _quantity_for_unit(unit)
                parameter = qty if qty is not None else (
                    _parameter_from_noun(fragment, m.start("num")) or "value"
                )
                tol, tol_span = _extract_tolerance(fragment, end, ocr_warning)
                if tol_span is not None:
                    used.append(tol_span)
                c = _build(
                    parameter=parameter,
                    operator=op,
                    num=num,
                    unit=unit,
                    tolerance=tol,
                    raw_fragment=fragment,
                    raw_value_lexical=raw_value_lexical,
                    ocr_warning=ocr_warning,
                    extra_issues=(),
                )
                out.append(c)
                used.append((start, end))
                continue
        # Normal (non-corrupted) path
        num = _parse_number(num_tok, ocr_warning)
        qty = _quantity_for_unit(unit)
        # Prefer a noun-derived parameter when it is more specific than the
        # unit-derived quantity.  E.g. "accuracy ≥ 0.5 %" → parameter "accuracy"
        # (not "percentage"), so the comparison engine can distinguish accuracy
        # from resolution even when both share the % unit.
        noun_param = _parameter_from_noun(fragment, m.start("num"))
        if qty is not None and noun_param is not None and noun_param != qty:
            parameter = noun_param
        else:
            parameter = qty if qty is not None else (noun_param or "value")
        tol, tol_span = _extract_tolerance(fragment, end, ocr_warning)
        if tol_span is not None:
            used.append(tol_span)
        cmp_extra: tuple[str, ...] = ()
        if unit and not qty:
            cmp_extra = ("unknown_unit",)
        c = _build(
            parameter=parameter,
            operator=op,
            num=num,
            unit=unit,
            tolerance=tol,
            raw_fragment=fragment,
            raw_value_lexical=raw_value_lexical,
            ocr_warning=ocr_warning,
            extra_issues=cmp_extra,
        )
        out.append(c)
        used.append((start, end))

    # Standalone tolerance: ±N [unit] with no preceding comparison operator.
    # E.g. "the voltage tolerance shall be ±2 %" extracts as an exact constraint
    # with value=2, unit="%", tolerance=2.
    for m in _TOL_STANDALONE_RE.finditer(fragment):
        start, end = m.span()
        if any(s < end and e > start for s, e in used):
            continue
        used.append((start, end))
        num_tok = m.group("num")
        unit_tok = m.group("unit")
        unit = _is_real_unit(unit_tok)
        qty = _quantity_for_unit(unit)
        # Only accept if the unit is recognized — otherwise this ± pattern is
        # likely noise, not a tolerance specification.
        if unit is not None and qty is None:
            continue
        num = _parse_number(num_tok, ocr_warning)
        parameter = qty if qty is not None else (
            _parameter_from_noun(fragment, m.start("num")) or "value"
        )
        tol = _Tolerance(value=num.value, lexical=num.lexical) if num.value is not None else None
        tol_extra: tuple[str, ...] = ("tolerance",)
        c = _build(
            parameter=parameter,
            operator=ConstraintOperator.EQUALS,
            num=num,
            unit=unit,
            tolerance=tol,
            raw_fragment=fragment,
            raw_value_lexical=num.lexical,
            ocr_warning=ocr_warning,
            extra_issues=tol_extra,
        )
        out.append(c)

    return out


__all__ = [
    "ConstraintOperator",
    "ParsedConstraint",
    "parse_constraint",
]