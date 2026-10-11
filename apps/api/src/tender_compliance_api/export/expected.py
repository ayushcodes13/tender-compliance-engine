"""Expected rendered table values for the export integrity validator.

Values mirror the documented presentation contract of each exporter. Tender
wording remains verbatim; other fields are compared with their owning
projection fields after the export's intentional display formatting.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from tender_compliance_api.export.final_xlsx import (
    _ASSESSMENT_STATUS_LABELS,
    _REVIEW_STATUS_LABELS,
    FINAL_MATRIX_COLUMNS,
    _format_cell_value,
)
from tender_compliance_api.export.validation import RequirementCell
from tender_compliance_api.export.vendor_response_rows import response_sheet_lines
from tender_compliance_api.export.xlsx import MATRIX_COLUMNS
from tender_compliance_api.matrix.projection import FinalMatrixRow, MatrixRow


def _plain(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return str(float(value))
    if isinstance(value, (UUID, datetime)):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M UTC")
        return str(value)
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def phase1_matrix_xlsx(rows: Sequence[MatrixRow]) -> tuple[list[str], list[RequirementCell]]:
    headers = [label for _field, label in MATRIX_COLUMNS]
    expected: list[RequirementCell] = []
    for row in rows:
        fields: dict[str, str] = {}
        for field, label in MATRIX_COLUMNS:
            value = getattr(row, field)
            if field == "review_status":
                value = {
                    "unreviewed": "Unreviewed",
                    "reviewed": "Reviewed",
                    "needs_clarification": "Needs clarification",
                    "ocr_warning": "OCR warning",
                }.get(str(value), value)
            elif field == "mandatory":
                value = "" if value is None else ("Yes" if value else "No")
            fields[label] = _plain(value)
        expected.append(RequirementCell(str(row.requirement_id), row.raw_source, fields))
    return headers, expected


def final_matrix_xlsx(rows: Sequence[FinalMatrixRow]) -> tuple[list[str], list[RequirementCell]]:
    headers = [label for _field, label in FINAL_MATRIX_COLUMNS]
    expected: list[RequirementCell] = []
    for row in rows:
        fields: dict[str, str] = {}
        for field, label in FINAL_MATRIX_COLUMNS:
            value: object = getattr(row, field)
            if field == "review_status":
                value = _REVIEW_STATUS_LABELS.get(str(value), str(value))
            elif field in ("assessment_status", "assessment_suggested_status"):
                value = (
                    "" if value is None else _ASSESSMENT_STATUS_LABELS.get(str(value), str(value))
                )
            elif field == "mandatory":
                value = "" if value is None else ("Yes" if value else "No")
            elif field == "source_page":
                value = value if value else ""
            elif field in ("assessment_is_confirmed", "has_unresolved_conflict"):
                value = "Yes" if value else "No"
            elif field in ("clarification_statuses", "deviation_statuses"):
                statuses = cast(list[str], value)
                value = "; ".join(statuses) if statuses else ""
            else:
                value = _format_cell_value(value)
            fields[label] = str(value or "")
        expected.append(RequirementCell(str(row.requirement_id), row.raw_source, fields))
    return headers, expected


def final_matrix_docx(rows: Sequence[FinalMatrixRow]) -> tuple[list[str], list[RequirementCell]]:
    headers = [
        "S.No.",
        "Requirement ID",
        "Tender Requirement",
        "Assessment Status",
        "Vendor Spec",
        "Evidence ID",
        "Evidence Score",
        "Confirmed",
        "Conflict",
        "Clarifications",
        "Deviations",
    ]
    expected: list[RequirementCell] = []
    for row in rows:
        status = row.assessment_status or ""
        status = _ASSESSMENT_STATUS_LABELS.get(status, status) if status else ""
        vendor_spec = f"{_plain(row.vendor_spec_value)} {_plain(row.vendor_spec_unit)}".strip()
        confirmed = (
            "Yes"
            if row.assessment_is_confirmed
            else ("No" if row.assessment_is_confirmed is not None else "")
        )
        fields = {
            "S.No.": _plain(row.serial),
            "Requirement ID": _plain(row.requirement_id),
            "Tender Requirement": row.tender_requirement,
            "Assessment Status": status,
            "Vendor Spec": vendor_spec,
            "Evidence ID": _plain(row.evidence_id),
            "Evidence Score": _plain(row.evidence_score),
            "Confirmed": confirmed,
            "Conflict": "Yes" if row.has_unresolved_conflict else "No",
            "Clarifications": (
                "; ".join(row.clarification_statuses) if row.clarification_statuses else ""
            ),
            "Deviations": "; ".join(row.deviation_statuses) if row.deviation_statuses else "",
        }
        expected.append(RequirementCell(str(row.requirement_id), row.tender_requirement, fields))
    return headers, expected


def vendor_response_docx(rows: Sequence[MatrixRow]) -> tuple[list[str], list[RequirementCell]]:
    headers = [
        "S.No.",
        "Technical Specification",
        "Compliance (Yes / No)",
        "Any Deviation",
    ]
    expected: list[RequirementCell] = []
    for line in response_sheet_lines(rows):
        fields = {
            "S.No.": line.display_label,
            "Technical Specification": line.display_text,
            "Compliance (Yes / No)": "",
            "Any Deviation": "",
        }
        expected.append(RequirementCell(line.bookmark_name, line.display_text, fields))
    return headers, expected


def final_matrix_pdf(rows: Sequence[FinalMatrixRow]) -> tuple[list[str], list[RequirementCell]]:
    headers = (
        [
            "S.No.",
            "Requirement ID",
            "Tender Requirement",
            "Assessment",
            "V.Value",
            "V.Unit",
            "Evidence ID",
            "Confirmed",
            "Conflict",
        ]
        if rows
        else []
    )
    expected: list[RequirementCell] = []
    for row in rows:
        status = row.assessment_status
        if status is None and row.assessment_suggested_status is not None:
            status = row.assessment_suggested_status
        status_label = _ASSESSMENT_STATUS_LABELS.get(status, status) if status else ""
        fields = {
            "S.No.": _plain(row.serial),
            "Requirement ID": _plain(row.requirement_id),
            "Tender Requirement": row.tender_requirement,
            "Assessment": status_label,
            "V.Value": _plain(row.vendor_spec_value),
            "V.Unit": _plain(row.vendor_spec_unit),
            "Evidence ID": _plain(row.evidence_id)[:8],
            "Confirmed": "Y"
            if row.assessment_is_confirmed
            else ("N" if row.assessment_is_confirmed is not None else ""),
            "Conflict": "Y" if row.has_unresolved_conflict else "N",
        }
        expected.append(RequirementCell(str(row.requirement_id), row.tender_requirement, fields))
    return headers, expected
