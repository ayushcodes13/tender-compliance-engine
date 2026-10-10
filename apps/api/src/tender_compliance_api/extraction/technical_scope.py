"""Deterministic selection of tender technical-specification sections.

Only source text inside an explicitly titled technical-specification section
is eligible for Phase 1 extraction. This prevents product-related statements
in eligibility, general terms, and commercial sections from becoming sheet
rows simply because they sound like requirements.

Section detection is intentionally conservative. If a document has no
recognizable technical-specification heading, callers receive an empty
selection and must keep the extraction run in review/failure rather than scan
the whole tender as a fallback.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class _PageLike(Protocol):
    page_number: int
    cleaned_text: str | None


@dataclass(frozen=True)
class SourceTextRange:
    """Inclusive-start, exclusive-end offsets in one parsed page."""

    start: int
    end: int


@dataclass(frozen=True)
class TechnicalSectionSelection:
    """The selected ranges, and the heading that authorized them."""

    ranges_by_page: dict[int, tuple[SourceTextRange, ...]]
    headings: tuple[str, ...]

    @property
    def found(self) -> bool:
        return bool(self.ranges_by_page)


@dataclass(frozen=True)
class _Line:
    page_number: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class _Heading:
    line_index: int
    start_index: int
    text: str
    has_compliance_sheet: bool


_TECH_SPEC_RE = re.compile(r"\btechnical\s+(?:specifications?|requirements?)\b", re.I)
_SECTION_RE = re.compile(
    r"^\s*(?:[^.;!?]{0,50}?\s*/\s*)?section\s*[-–—]?\s*(?:[\divxlc]+)\b",
    re.I,
)
_ANNEXURE_RE = re.compile(
    r"^\s*\(?\s*(?:annexure|annex|appendix|form)\s*[-–—]?\s*\w+\b",
    re.I,
)
_PART_RE = re.compile(r"^\s*part\s*[-–—]?\s*([\divxlc]+)\b", re.I)
_OTHER_MAJOR_RE = re.compile(
    r"^\s*(?:general\s+terms\s+and\s+conditions|eligibility\s+criteria|"
    r"commercial\s+bid|price\s+schedule|bid\s+schedule|check\s*list)\b",
    re.I,
)
_NOTE_RE = re.compile(r"^\s*notes?\s*[:.)-]", re.I)
_TOC_PAGE_RE = re.compile(r"\b(?:pg\.?|page\s*#?)\s*\d+\b", re.I)


def _normalise_line(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(value.split())


def _lines(pages: Sequence[_PageLike]) -> list[_Line]:
    result: list[_Line] = []
    for page in sorted(pages, key=lambda item: item.page_number):
        text = page.cleaned_text or ""
        offset = 0
        for raw_line in text.splitlines(keepends=True):
            body = raw_line.rstrip("\r\n")
            if body.strip():
                result.append(
                    _Line(
                        page_number=page.page_number,
                        start=offset,
                        end=offset + len(raw_line),
                        text=body,
                    )
                )
            offset += len(raw_line)
    return result


def _is_heading_shape(line: str) -> bool:
    stripped = line.strip()
    if _SECTION_RE.search(stripped) or _ANNEXURE_RE.search(stripped):
        return True
    # Titles may be preceded by a translated label (for example, Hindi / English)
    # or by a qualifier such as "Additional". Keep this bounded to short label
    # lines without sentence punctuation so narrative references in eligibility
    # and commercial clauses do not open a technical section.
    match = _TECH_SPEC_RE.search(stripped)
    if match and len(stripped) <= 100 and not re.search(r"[.;!?]", stripped):
        prefix = stripped[: match.start()].strip()
        if not prefix or prefix.endswith("/") or prefix.casefold() == "additional":
            return True
    if re.search(r"[.;!?]", stripped):
        return False
    # Many tenders print this heading in all caps, sometimes with a colon.
    letters = [char for char in stripped if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def _find_headings(lines: list[_Line]) -> list[_Heading]:
    headings: list[_Heading] = []
    for index, line in enumerate(lines):
        normalized = _normalise_line(line.text)
        if not _TECH_SPEC_RE.search(normalized):
            continue
        if _TOC_PAGE_RE.search(normalized):
            continue
        if not _is_heading_shape(normalized):
            continue

        start_index = index
        # Keep a nearby section/annexure/part label with its descriptive title.
        if not (_SECTION_RE.match(normalized) or _ANNEXURE_RE.match(normalized)):
            for previous_index in range(max(0, index - 2), index):
                previous = _normalise_line(lines[previous_index].text)
                if lines[previous_index].page_number != line.page_number:
                    continue
                if (
                    _SECTION_RE.match(previous)
                    or _ANNEXURE_RE.match(previous)
                    or _PART_RE.match(previous)
                ):
                    start_index = min(start_index, previous_index)

        has_compliance_sheet = any(
            "compliance sheet" in _normalise_line(lines[nearby].text).casefold()
            for nearby in range(max(0, index - 3), index + 1)
            if lines[nearby].page_number == line.page_number
        )
        headings.append(
            _Heading(
                line_index=index,
                start_index=start_index,
                text=normalized,
                has_compliance_sheet=has_compliance_sheet,
            )
        )
    return headings


def _is_boundary(line: str) -> bool:
    return bool(
        _SECTION_RE.match(line)
        or _ANNEXURE_RE.match(line)
        or _PART_RE.match(line)
        or _OTHER_MAJOR_RE.match(line)
        or _NOTE_RE.match(line)
    )


def select_technical_specification_ranges(
    pages: Sequence[_PageLike],
) -> TechnicalSectionSelection:
    """Select explicit technical-specification sections from parsed pages.

    When a tender contains a separately labeled compliance sheet, prefer that
    section because it is the tender's own response layout. Otherwise, select
    the explicitly titled technical-specification/technical-requirements
    sections. Table text and nested bullets remain inside the selected ranges.
    """

    lines = _lines(pages)
    headings = _find_headings(lines)
    if not headings:
        return TechnicalSectionSelection(ranges_by_page={}, headings=())

    compliance_headings = [heading for heading in headings if heading.has_compliance_sheet]
    structural_headings = [
        heading
        for heading in headings
        if heading.start_index < heading.line_index
        or _SECTION_RE.match(_normalise_line(lines[heading.line_index].text))
        or _ANNEXURE_RE.match(_normalise_line(lines[heading.line_index].text))
    ]
    selected_headings = compliance_headings or structural_headings or headings
    selected_starts = {heading.start_index for heading in selected_headings}
    selected_ranges: dict[int, list[SourceTextRange]] = {}
    selected_titles: list[str] = []

    for heading in selected_headings:
        start_line_index = heading.start_index
        start_line = lines[start_line_index]
        current_part = next(
            (
                match.group(1).casefold()
                for line in lines[start_line_index : heading.line_index + 1]
                if (match := _PART_RE.match(_normalise_line(line.text)))
            ),
            None,
        )
        if current_part is None:
            # Some tenders put PART II after the "Technical Specification"
            # title; treat that first part label as belonging to this section.
            current_part_pending = True
        else:
            current_part_pending = False
        end_line_index = len(lines)
        for index in range(heading.line_index + 1, len(lines)):
            candidate = lines[index]
            normalized = _normalise_line(candidate.text)
            part_match = _PART_RE.match(normalized)
            if part_match:
                part_value = part_match.group(1).casefold()
                if current_part_pending:
                    current_part = part_value
                    current_part_pending = False
                    continue
                if current_part == part_value:
                    continue
            if not _is_boundary(normalized):
                continue
            # A separate technical heading is another selected section, not an
            # end marker for the current one.
            if index in {item.line_index for item in selected_headings}:
                continue
            # Ignore the section/annexure label that belongs to this heading.
            if index in selected_starts:
                continue
            end_line_index = index
            break

        end_line = lines[end_line_index] if end_line_index < len(lines) else None
        for index in range(start_line_index, end_line_index):
            line = lines[index]
            if line.page_number == start_line.page_number:
                start_offset = start_line.start if index == start_line_index else line.start
            else:
                start_offset = line.start
            if end_line is not None and line.page_number == end_line.page_number:
                end_offset = end_line.start
                if end_offset <= start_offset:
                    continue
            else:
                end_offset = line.end
            selected_ranges.setdefault(line.page_number, []).append(
                SourceTextRange(start=start_offset, end=end_offset)
            )

        selected_titles.append(heading.text)

    return TechnicalSectionSelection(
        ranges_by_page={
            page_number: tuple(_merge_ranges(ranges))
            for page_number, ranges in selected_ranges.items()
        },
        headings=tuple(selected_titles),
    )


def _merge_ranges(ranges: list[SourceTextRange]) -> list[SourceTextRange]:
    merged: list[SourceTextRange] = []
    for current in sorted(ranges, key=lambda item: item.start):
        if merged and current.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = SourceTextRange(
                start=previous.start,
                end=max(previous.end, current.end),
            )
        else:
            merged.append(current)
    return merged


__all__ = [
    "SourceTextRange",
    "TechnicalSectionSelection",
    "select_technical_specification_ranges",
]
