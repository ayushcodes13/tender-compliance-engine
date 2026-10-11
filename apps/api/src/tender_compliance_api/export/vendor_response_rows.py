"""Source-preserving row hierarchy for the blank OEM response sheet."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from tender_compliance_api.matrix.projection import MatrixRow

_BULLET_MARKERS = r"[•●▪◦‣\uf0a7\uf0b7]"
_MARKER = re.compile(
    rf"(?m)(?:^[ \t]*(?P<line_marker>(?:\d+(?:\.\d+)*[.)]|[A-Za-z][.)]|"
    rf"{_BULLET_MARKERS}))|(?<=\s)(?P<inline_bullet>{_BULLET_MARKERS}))[ \t]*"
)
_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:[.)])?[ \t]+")
_LETTER = re.compile(r"^(?P<letter>[A-Za-z])[.)][ \t]+")
_BULLET = re.compile(r"^(?P<bullet>[•●▪◦‣\uf0a7\uf0b7])[ \t]*")


@dataclass(frozen=True)
class VendorResponseLine:
    """One independently answerable source fragment in the response sheet."""

    row_id: str
    serial: str
    item_text: str
    source_text: str
    level: int
    parent_requirement_id: str


def _marked_fragments(text: str) -> list[tuple[str | None, str]]:
    """Split only at list markers that begin a source line.

    The marker stays in the fragment, so every source character remains in the
    OEM-facing specification cell. Whitespace separating list items is layout
    whitespace; whitespace inside an unsplit source value is retained.
    """
    matches = []
    for match in _MARKER.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        label = text[line_start : match.start()].rstrip()
        if (
            match.group("inline_bullet") == "\uf0b7"
            and len(label) <= 24
            and label.endswith(":")
        ):
            # Some PDF text layers put the private-use bullet between a short
            # field label and its value (for example, "Power supply: • 380V").
            # Keep that label/value pair together as one technical parameter.
            continue
        matches.append(match)
    if not matches:
        return [(None, text)] if text.strip() else []

    fragments: list[tuple[str | None, str]] = []
    prefix = text[: matches[0].start()]
    if prefix.strip():
        fragments.append((None, prefix.strip()))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fragment = text[match.start() : end]
        if fragment.strip():
            marker = match.group("line_marker") or match.group("inline_bullet")
            fragments.append((marker, fragment.strip()))
    return fragments


def _split_parameter_column(text: str) -> tuple[str, str]:
    """Separate the parser's table-cell delimiter into two source columns."""
    cells = re.split(r"\s+\|\s+", text, maxsplit=1)
    if len(cells) == 2 and cells[0].strip() and cells[1].strip():
        return cells[0].strip(), cells[1]
    return "", text


def response_sheet_lines(rows: Sequence[MatrixRow]) -> list[VendorResponseLine]:
    """Expand source-backed parent items and nested list items into rows.

    A source-numbered heading establishes the active parent for following
    lettered items. Bullets within a single source quote are split into their
    own answer rows. Generated serials identify rows in this form; source
    numbering and wording remain visible in ``source_text``.
    """
    result: list[VendorResponseLine] = []
    active_source_parent: str | None = None
    active_child_index = 0
    serial_owner: dict[str, str] = {}

    def unique_serial(proposed: str, fallback: int, owner_id: str) -> str:
        if proposed not in serial_owner:
            serial_owner[proposed] = owner_id
            return proposed
        if serial_owner[proposed] == owner_id:
            # Preserve duplicates from the canonical projection so the
            # post-render integrity gate can detect rather than disguise them.
            return proposed
        candidate = str(fallback)
        suffix = 2
        while candidate in serial_owner:
            candidate = f"{fallback}.{suffix}"
            suffix += 1
        serial_owner[candidate] = owner_id
        return candidate

    def add(
        row: MatrixRow,
        proposed: str,
        fragment: str,
        level: int,
        item_text: str = "",
    ) -> None:
        serial = unique_serial(proposed, row.serial, str(row.requirement_id))
        result.append(
            VendorResponseLine(
                row_id=f"{row.requirement_id}:{serial}",
                serial=serial,
                item_text=item_text,
                source_text=fragment,
                level=level,
                parent_requirement_id=str(row.requirement_id),
            )
        )

    for row in rows:
        source = row.raw_source or row.tender_requirement
        item_text, source = _split_parameter_column(source)
        source_number = ""
        if re.fullmatch(r"\d+(?:\.\d+)*[.)]?", item_text):
            source_number = re.sub(r"[.)]$", "", item_text)
            item_text = ""
        fragments = _marked_fragments(source)
        first = fragments[0][1] if fragments else ""
        first_number = _NUMBER.match(first)
        first_letter = _LETTER.match(first)
        first_bullet = _BULLET.match(first)

        if first_number:
            active_source_parent = first_number.group("number")
            active_child_index = 0
        elif source_number:
            active_source_parent = source_number
            active_child_index = 0

        if not fragments:
            continue

        has_nested_items = len(fragments) > 1
        if len(fragments) == 1 and item_text and first_bullet:
            parent = source_number or str(row.serial)
            add(row, parent, "", 0, item_text)
            active_source_parent = parent
            add(row, f"{parent}.1", fragments[0][1], 1)
            continue

        if (
            has_nested_items
            and first_bullet
            and not item_text
            and not source_number
            and not re.search(r":[ \t]*$", first)
        ):
            # A numbered source row may contain only bullets and no heading.
            # Make its first fillable specification the numbered row itself;
            # later bullets are child rows. Do not invent an empty parent row.
            parent = str(row.serial)
            add(row, parent, fragments[0][1], 0)
            for child_index, (_marker, fragment) in enumerate(fragments[1:], start=1):
                add(row, f"{parent}.{child_index}", fragment, 1)
            active_source_parent = parent
            active_child_index = len(fragments) - 1
            continue

        if has_nested_items:
            parent = (
                source_number
                or (
                    str(row.serial)
                    if item_text or first_bullet or fragments[0][0] is None
                    else active_source_parent
                )
                or str(row.serial)
            )
            if item_text and first_bullet:
                add(row, parent, "", 0, item_text)
                active_source_parent = parent
            child_index = 0
            for fragment_index, (marker, fragment) in enumerate(fragments):
                bullet_heading = bool(
                    marker
                    and _BULLET.fullmatch(marker)
                    and re.search(r":[ \t]*$", fragment)
                )
                if bullet_heading:
                    serial = str(row.serial) if fragment_index == 0 else parent
                    add(row, serial, fragment, 0, item_text if fragment_index == 0 else "")
                    parent = serial
                    active_source_parent = parent
                    active_child_index = 0
                    continue

                if fragment_index == 0 and marker is None:
                    add(row, parent, fragment or item_text, 0, item_text)
                    active_source_parent = parent
                    active_child_index = 0
                    continue

                if marker is None:
                    add(row, parent, fragment or item_text, 0, item_text)
                    active_source_parent = parent
                    active_child_index = 0
                    continue

                letter = _LETTER.match(fragment)
                numeric = _NUMBER.match(fragment)
                if letter:
                    child_key = letter.group("letter").lower()
                    add(row, f"{parent}.{child_key}", fragment, 1)
                elif numeric:
                    group = numeric.group("number")
                    add(row, group, fragment, 0)
                    active_source_parent = group
                    parent = group
                    child_index = 0
                else:
                    child_index += 1
                    add(row, f"{parent}.{child_index}", fragment, 1)
            active_child_index = child_index
            if item_text or first_bullet or fragments[0][0] is None:
                active_source_parent = parent
            continue

        fragment = fragments[0][1]
        if first_letter and active_source_parent:
            child_key = first_letter.group("letter").lower()
            add(row, f"{active_source_parent}.{child_key}", fragment, 1)
        elif first_bullet and active_source_parent:
            active_child_index += 1
            add(row, f"{active_source_parent}.{active_child_index}", fragment, 1)
        else:
            marker_number = (
                first_number.group("number") if first_number else source_number
            )
            serial = marker_number or str(row.serial)
            add(row, serial, fragment or item_text, 0, item_text)
            active_source_parent = serial
            active_child_index = 0

    return result
