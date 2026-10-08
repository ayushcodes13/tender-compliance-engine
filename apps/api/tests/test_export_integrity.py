"""Post-render matrix validation must check every visible column."""

from __future__ import annotations

from uuid import uuid4

from tender_compliance_api.export.expected import final_matrix_pdf, phase1_matrix_xlsx
from tender_compliance_api.export.final_pdf import build_final_matrix_pdf
from tender_compliance_api.export.validation import validate_generated_requirement_cells
from tender_compliance_api.export.xlsx import build_matrix_workbook, save_matrix_workbook
from tender_compliance_api.matrix.projection import MatrixRow


def _row() -> MatrixRow:
    return MatrixRow(
        serial=1,
        requirement_id=uuid4(),
        tender_requirement="The pump shall deliver 12 L/min.",
        category="Performance",
        clause="4.2.1",
        source_page=3,
        mandatory=True,
        user_notes="Reviewer note",
        review_status="unreviewed",
        normalized_text="The pump shall deliver 12 L/min.",
        raw_source="The pump shall deliver 12 L/min.",
        uncertainty="exact",
        ocr_warning=False,
    )


def test_export_integrity_catches_mutated_non_source_cell() -> None:
    row = _row()
    expected_headers, expected = phase1_matrix_xlsx([row])
    workbook, _checksum = build_matrix_workbook([row])
    workbook.active["H8"] = "Different note"
    data = save_matrix_workbook(workbook)

    result = validate_generated_requirement_cells(
        expected,
        data,
        export_format="xlsx",
        expected_headers=expected_headers,
    )

    assert result.status == "failed"
    assert any(
        issue.code == "changed_cell" and issue.field == "User Notes" for issue in result.issues
    )


def test_export_integrity_catches_missing_column_header() -> None:
    row = _row()
    expected_headers, expected = phase1_matrix_xlsx([row])
    workbook, _checksum = build_matrix_workbook([row])
    workbook.active["H7"] = None
    data = save_matrix_workbook(workbook)

    result = validate_generated_requirement_cells(
        expected,
        data,
        export_format="xlsx",
        expected_headers=expected_headers,
    )

    assert result.status == "failed"
    assert any(
        issue.code == "missing_column" and issue.field == "user notes" for issue in result.issues
    )


def test_pdf_integrity_checks_all_columns_with_wrapped_tender_text() -> None:
    row = type(
        "PdfRow",
        (),
        {
            "serial": 1,
            "requirement_id": uuid4(),
            "tender_requirement": "The pump shall meet this requirement: "
            + ("deliver 12 L/min under continuous operation; " * 12),
            "assessment_status": None,
            "assessment_suggested_status": None,
            "vendor_spec_value": None,
            "vendor_spec_unit": None,
            "evidence_id": None,
            "assessment_is_confirmed": None,
            "has_unresolved_conflict": False,
        },
    )()
    expected_headers, expected = final_matrix_pdf([row])
    artifact = build_final_matrix_pdf([row])

    result = validate_generated_requirement_cells(
        expected,
        artifact,
        export_format="pdf",
        expected_headers=expected_headers,
    )

    assert result.status == "passed", result.issues
    assert result.expected_rows == result.actual_rows == 1
