"""Final compliance matrix XLSX writer (CP60).

Extends the Phase 1 XLSX writer to project the final (Phase 2) compliance
matrix — adding vendor response, evidence, assessment, and review-state
columns on top of the original tender columns.  Uses the same canonical
``project_final_matrix_rows`` projection so UI and export share one source
of truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Font, PatternFill  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]

from tender_compliance_api.matrix.projection import FinalMatrixRow

# Canonical column headers (CP41 Phase 1 + CP59 Phase 2).
FINAL_MATRIX_COLUMNS: list[tuple[str, str]] = [
    # Phase 1 columns
    ("serial", "S.No."),
    ("requirement_id", "Requirement ID"),
    ("tender_requirement", "Tender Requirement"),
    ("category", "Category"),
    ("clause", "Clause"),
    ("source_page", "Source Page"),
    ("mandatory", "Mandatory"),
    ("user_notes", "User Notes"),
    ("review_status", "Review Status"),
    # Phase 2: Vendor Response
    ("vendor_spec_parameter", "Vendor Spec Parameter"),
    ("vendor_spec_value", "Vendor Spec Value"),
    ("vendor_spec_unit", "Vendor Spec Unit"),
    ("vendor_spec_source_text", "Vendor Spec Source Text"),
    # Phase 2: Evidence
    ("evidence_id", "Evidence ID"),
    ("evidence_score", "Evidence Score"),
    ("evidence_oem_document", "Evidence Source (OEM Doc)"),
    ("evidence_oem_version", "Evidence Version"),
    # Phase 2: Assessment
    ("assessment_status", "Assessment Status"),
    ("assessment_suggested_status", "Suggested Status"),
    ("assessment_reason_code", "Assessment Reason Code"),
    ("assessment_reason_text", "Assessment Reason Text"),
    ("assessment_is_confirmed", "Confirmed by Human"),
    ("assessment_reviewer_id", "Reviewer ID"),
    ("assessment_reviewed_at", "Reviewed At"),
    ("assessment_version", "Assessment Version"),
    # Phase 2: Review State Summary
    ("has_unresolved_conflict", "Has Unresolved Conflict"),
    ("clarification_statuses", "Clarification Statuses"),
    ("deviation_statuses", "Deviation Statuses"),
]

# Column widths (characters).
COLUMN_WIDTHS: dict[str, float] = {
    "S.No.": 6,
    "Requirement ID": 38,
    "Tender Requirement": 60,
    "Category": 20,
    "Clause": 16,
    "Source Page": 12,
    "Mandatory": 10,
    "User Notes": 40,
    "Review Status": 18,
    "Vendor Spec Parameter": 22,
    "Vendor Spec Value": 14,
    "Vendor Spec Unit": 12,
    "Vendor Spec Source Text": 45,
    "Evidence ID": 38,
    "Evidence Score": 12,
    "Evidence Source (OEM Doc)": 28,
    "Evidence Version": 14,
    "Assessment Status": 20,
    "Suggested Status": 18,
    "Assessment Reason Code": 22,
    "Assessment Reason Text": 50,
    "Confirmed by Human": 18,
    "Reviewer ID": 38,
    "Reviewed At": 24,
    "Assessment Version": 18,
    "Has Unresolved Conflict": 24,
    "Clarification Statuses": 24,
    "Deviation Statuses": 20,
}

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)

# Readable labels for review status.
_REVIEW_STATUS_LABELS: dict[str, str] = {
    "unreviewed": "Unreviewed",
    "reviewed": "Reviewed",
    "needs_clarification": "Needs clarification",
    "ocr_warning": "OCR warning",
}

# Readable labels for assessment status.
_ASSESSMENT_STATUS_LABELS: dict[str, str] = {
    "compliant": "Compliant",
    "non_compliant": "Non-Compliant",
    "partial": "Partial",
    "not_demonstrated": "Not Demonstrated",
    "conflict": "Conflict",
    "human_review_required": "Human Review Required",
}


def _format_cell_value(value: object) -> str:
    """Convert a cell value to a displayable string.  ``None`` → empty string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def build_final_matrix_workbook(
    rows: Sequence[FinalMatrixRow],
    *,
    project_name: str | None = None,
    document_id: UUID | None = None,
    version_number: int | None = None,
    generated_at: datetime | None = None,
    actor_id: UUID | None = None,
    requirement_count: int | None = None,
) -> tuple[Workbook, str]:
    """Build an XLSX workbook from final matrix rows (CP59/CP60).

    Returns ``(workbook, sha256)`` where ``sha256`` is the checksum of the
    written bytes — computed from the actual workbook output, not trusted
    from any provider.
    """
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Final Compliance Matrix"

    if generated_at is None:
        generated_at = datetime.now(UTC)

    # --- Metadata header rows (above the table) ---
    ws.insert_rows(0, 5)
    ws["A1"] = "Project"
    ws["B1"] = project_name or "—"
    ws["A2"] = "Document ID"
    ws["B2"] = str(document_id) if document_id else "—"
    ws["A3"] = "Version"
    ws["B3"] = str(version_number) if version_number else "—"
    ws["A4"] = "Generated"
    ws["B4"] = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    ws["A5"] = "Generated by"
    ws["B5"] = str(actor_id) if actor_id else "system"

    header_row = 7
    ws.freeze_panes = f"A{header_row}"

    # --- Table header ---
    for col_idx, (_field, label) in enumerate(FINAL_MATRIX_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.value = label
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(col_idx)].width = COLUMN_WIDTHS[label]

    # --- Data rows ---
    for row_idx, matrix_row in enumerate(rows, start=header_row + 1):
        for col_idx, (field, _) in enumerate(FINAL_MATRIX_COLUMNS, start=1):
            value: object
            if field == "review_status":
                value = _REVIEW_STATUS_LABELS.get(
                    matrix_row.review_status, matrix_row.review_status
                )
            elif field == "assessment_status":
                if matrix_row.assessment_status is None:
                    value = ""
                else:
                    value = _ASSESSMENT_STATUS_LABELS.get(
                        matrix_row.assessment_status,
                        matrix_row.assessment_status,
                    )
            elif field == "assessment_suggested_status":
                if matrix_row.assessment_suggested_status is None:
                    value = ""
                else:
                    value = _ASSESSMENT_STATUS_LABELS.get(
                        matrix_row.assessment_suggested_status,
                        matrix_row.assessment_suggested_status,
                    )
            elif field == "mandatory":
                if matrix_row.mandatory is None:
                    value = ""
                else:
                    value = "Yes" if matrix_row.mandatory else "No"
            elif field == "source_page":
                value = matrix_row.source_page if matrix_row.source_page else ""
            elif field in ("assessment_is_confirmed", "has_unresolved_conflict"):
                value = "Yes" if getattr(matrix_row, field) else "No"
            elif field == "clarification_statuses":
                clars = matrix_row.clarification_statuses
                value = "; ".join(clars) if clars else ""
            elif field == "deviation_statuses":
                devs = matrix_row.deviation_statuses
                value = "; ".join(devs) if devs else ""
            else:
                value = getattr(matrix_row, field)
                value = _format_cell_value(value)

            cell = ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            if field in ("tender_requirement", "user_notes",
                         "vendor_spec_source_text", "assessment_reason_text"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- Auto-filter on the header row ---
    last_col_letter = get_column_letter(len(FINAL_MATRIX_COLUMNS))
    filter_range = f"A{header_row}:{last_col_letter}{header_row}"
    ws.auto_filter.ref = filter_range

    # --- Summary row below data ---
    data_end_row = header_row + len(rows)
    summary_row = data_end_row + 2
    ws.cell(row=summary_row, column=1, value="Total requirements:")
    ws.cell(row=summary_row, column=2, value=requirement_count or len(rows))
    ws.cell(row=summary_row + 1, column=1, value="Exported:")
    ws.cell(row=summary_row + 1, column=2, value=generated_at.strftime("%Y-%m-%d %H:%M"))

    # Compute SHA-256 of the workbook bytes.
    import hashlib
    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    checksum = hashlib.sha256(buf.getvalue()).hexdigest()
    buf.seek(0)

    from openpyxl import load_workbook
    wb = load_workbook(buf)
    return wb, checksum


def save_workbook_bytes(wb: Workbook) -> bytes:
    """Serialize the workbook to bytes (for storage)."""
    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
