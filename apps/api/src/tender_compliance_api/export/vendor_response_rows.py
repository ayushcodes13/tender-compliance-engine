"""Source-preserving row hierarchy for the blank OEM response sheet."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from hashlib import sha256

from tender_compliance_api.matrix.projection import MatrixRow

_BULLET_MARKERS = r"[•●▪◦‣\uf0a7\uf0b7]"
_MARKER = re.compile(
    rf"(?m)(?:^[ \t]*(?P<line_marker>(?:\d+(?:\.\d+)*[.)]|[A-Za-z][.)]|"
    rf"{_BULLET_MARKERS}))|(?<=\s)(?P<inline_bullet>{_BULLET_MARKERS}))[ \t]*"
)
_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:[.)])?[ \t]+")
_INLINE_NUMBER = re.compile(
    r"(?<!\S)(?P<marker>\d{1,2}[.)])[ \t]+(?=[A-Z0-9])"
)
_LETTER = re.compile(r"^(?P<letter>[A-Za-z])[.)][ \t]+")
_BULLET = re.compile(r"^(?P<bullet>[•●▪◦‣\uf0a7\uf0b7])[ \t]*")
_DISPLAY_MARKER = re.compile(
    rf"^(?:\d+(?:\.\d+)*[.)]|[A-Za-z][.)]|{_BULLET_MARKERS})[ \t]+"
)


@dataclass(frozen=True)
class VendorResponseLine:
    """One independently answerable source fragment in the response sheet."""

    row_id: str
    serial: str
    item_text: str
    source_text: str
    level: int
    parent_requirement_id: str
    display_label: str

    @property
    def display_source_text(self) -> str:
        """Render source list markers through the response-sheet row labels."""
        text = self.source_text
        marker = _DISPLAY_MARKER.match(text)
        if marker:
            text = text[marker.end() :]
        return text

    @property
    def display_text(self) -> str:
        return "\n".join(
            part for part in (self.item_text, self.display_source_text) if part
        )

    @property
    def bookmark_name(self) -> str:
        """Stable invisible identity for rows whose visible a)/b) repeats."""
        return f"tce_row_{sha256(self.row_id.encode('utf-8')).hexdigest()[:32]}"


def _alphabetic_label(index: int) -> str:
    remainder = index + 1
    label = ""
    while remainder:
        remainder, digit = divmod(remainder - 1, 26)
        label = chr(ord("a") + digit) + label
    return f"{label})"


def _add_display_labels(lines: list[VendorResponseLine]) -> list[VendorResponseLine]:
    child_counts: dict[str, int] = {}
    labelled: list[VendorResponseLine] = []
    active_parent: str | None = None
    for line in lines:
        if line.level == 0:
            active_parent = line.serial
            child_counts[active_parent] = 0
            label = f"{line.serial})"
        else:
            parent = active_parent or line.serial.split(".", maxsplit=1)[0]
            index = child_counts.get(parent, 0)
            child_counts[parent] = index + 1
            label = _alphabetic_label(index)
        labelled.append(replace(line, display_label=label))
    return labelled


def _marked_fragments(text: str) -> list[tuple[str | None, str]]:
    """Split only at list markers that begin a source line.

    Raw marker-bearing fragments stay available for validation; the response
    sheet renders those structural markers as row labels. Whitespace separating
    list items is layout whitespace; whitespace inside a fragment is retained.
    """
    markers: list[tuple[int, int, str]] = []
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
        marker = match.group("line_marker") or match.group("inline_bullet")
        markers.append((match.start(), match.end(), marker))

    # Some PDF table cells flatten numbered entries onto one line. Split only
    # a sequential list beginning at 1; this avoids interpreting decimals or
    # isolated numeric values as response rows.
    inline_numbers = [
        match
        for match in _INLINE_NUMBER.finditer(text)
        if text[text.rfind("\n", 0, match.start()) + 1 : match.start()].strip()
    ]
    sequences: list[list[re.Match[str]]] = []
    for index, match in enumerate(inline_numbers):
        if match.group("marker").rstrip(".)") != "1":
            continue
        sequence = [match]
        expected = 2
        for candidate in inline_numbers[index + 1 :]:
            number = candidate.group("marker").rstrip(".)")
            if number == str(expected):
                sequence.append(candidate)
                expected += 1
            elif number.isdigit() and int(number) > expected:
                break
        if len(sequence) >= 2:
            sequences.append(sequence)
    if sequences:
        for match in max(sequences, key=len):
            markers.append((match.start(), match.end(), match.group("marker")))

    markers.sort(key=lambda marker: marker[0])
    if not markers:
        return [(None, text)] if text.strip() else []

    fragments: list[tuple[str | None, str]] = []
    prefix = text[: markers[0][0]]
    if prefix.strip():
        fragments.append((None, prefix.strip()))
    for index, (start, _marker_end, marker) in enumerate(markers):
        end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        fragment = text[start:end]
        if fragment.strip():
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
                display_label="",
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
        has_heading_prefix = bool(
            fragments[0][0] is None and fragments[0][1].rstrip().endswith(":")
        )
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
                    if has_heading_prefix:
                        child_serial = (
                            group
                            if group.startswith(f"{parent}.")
                            else f"{parent}.{group}"
                        )
                        add(row, child_serial, fragment, 1)
                        child_index += 1
                    else:
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

    return _add_display_labels(result)
