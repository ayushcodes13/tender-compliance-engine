"""Independent layout checks for the blank technical response sheet.

Cell equality alone can repeat a parsing mistake because the exporter and its
expected projection share row formatting code. This module checks source
features that must remain separate in the rendered DOCX.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from docx import Document

from tender_compliance_api.export.vendor_response_rows import (
    _OPEN_CIRCLE_MARKER,
    _SECTION_HEADINGS,
)
from tender_compliance_api.matrix.projection import MatrixRow

PresentationIssueCode = Literal[
    "response_table_missing",
    "section_heading_not_standalone",
    "open_circle_marker_leaked",
]


@dataclass(frozen=True)
class VendorResponsePresentationIssue:
    code: PresentationIssueCode
    detail: str


@dataclass(frozen=True)
class VendorResponsePresentationResult:
    status: Literal["passed", "failed"]
    checked_headings: int
    checked_open_circle_markers: int
    issues: tuple[VendorResponsePresentationIssue, ...]


def validate_vendor_response_presentation(
    rows: Sequence[MatrixRow], artifact_bytes: bytes
) -> VendorResponsePresentationResult:
    """Catch flattened source headings and OCR circle markers in the DOCX.

    The checks inspect the serialized file and use original source rows to
    decide which heading and marker invariants apply. They do not infer or
    rewrite technical wording.
    """
    document = Document(BytesIO(artifact_bytes))
    specification_cells: list[str] = []
    for table in document.tables:
        if not table.rows:
            continue
        headers = [" ".join(cell.text.split()).casefold() for cell in table.rows[0].cells]
        if "technical specification" in headers and "s.no." in headers:
            specification_index = headers.index("technical specification")
            specification_cells.extend(
                " ".join(row.cells[specification_index].text.split()) for row in table.rows[1:]
            )
            break

    issues: list[VendorResponsePresentationIssue] = []
    if not specification_cells:
        return VendorResponsePresentationResult(
            status="failed",
            checked_headings=0,
            checked_open_circle_markers=0,
            issues=(
                VendorResponsePresentationIssue(
                    "response_table_missing", "Technical Specification table missing"
                ),
            ),
        )

    source_text = "\n".join(row.raw_source or row.tender_requirement for row in rows)
    present_headings = [
        heading
        for heading in _SECTION_HEADINGS
        if re.search(rf"(?<!\w){re.escape(heading)}(?!\w)", source_text)
    ]
    standalone_heading_keys = {
        re.sub(r"[:\s]+$", "", cell).casefold() for cell in specification_cells
    }
    for heading in present_headings:
        if heading.casefold() not in standalone_heading_keys:
            issues.append(
                VendorResponsePresentationIssue("section_heading_not_standalone", heading)
            )

    source_open_circle_markers = sum(
        len(_OPEN_CIRCLE_MARKER.findall(row.raw_source or row.tender_requirement)) for row in rows
    )
    if source_open_circle_markers and any(
        _OPEN_CIRCLE_MARKER.search(value) for value in specification_cells
    ):
        issues.append(
            VendorResponsePresentationIssue(
                "open_circle_marker_leaked",
                "A source open-circle marker is still rendered as the letter o",
            )
        )

    return VendorResponsePresentationResult(
        status="failed" if issues else "passed",
        checked_headings=len(present_headings),
        checked_open_circle_markers=source_open_circle_markers,
        issues=tuple(issues),
    )
