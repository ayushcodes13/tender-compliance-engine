"""Post-render matrix validation must check every visible column."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import docx
import pytest
from docx import Document
from docx.oxml.ns import qn

from tender_compliance_api.export.expected import (
    final_matrix_docx,
    final_matrix_pdf,
    final_matrix_xlsx,
    phase1_matrix_xlsx,
    vendor_response_docx,
)
from tender_compliance_api.export.final_docx import build_final_matrix_docx
from tender_compliance_api.export.final_pdf import build_final_matrix_pdf
from tender_compliance_api.export.final_xlsx import (
    build_final_matrix_workbook,
    save_workbook_bytes,
)
from tender_compliance_api.export.validation import (
    RequirementCell,
    validate_generated_requirement_cells,
)
from tender_compliance_api.export.vendor_response_docx import build_vendor_response_docx
from tender_compliance_api.export.vendor_response_rows import response_sheet_lines
from tender_compliance_api.export.xlsx import build_matrix_workbook, save_matrix_workbook
from tender_compliance_api.matrix.projection import FinalMatrixRow, MatrixRow


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


def _final_row(text: str) -> FinalMatrixRow:
    return FinalMatrixRow(
        serial=1,
        requirement_id=uuid4(),
        tender_requirement=text,
        category="Performance",
        clause="4.2.1",
        source_page=3,
        mandatory=True,
        user_notes=None,
        review_status="unreviewed",
        normalized_text=text,
        raw_source=text,
        uncertainty="exact",
        ocr_warning=False,
        evidence_id=None,
        evidence_score=None,
        evidence_oem_document=None,
        evidence_oem_version=None,
        vendor_spec_parameter=None,
        vendor_spec_value=None,
        vendor_spec_unit=None,
        vendor_spec_lower_bound=None,
        vendor_spec_upper_bound=None,
        vendor_spec_source_text=None,
        vendor_spec_source_page=None,
        vendor_spec_extraction_method=None,
        vendor_spec_issues=None,
        assessment_status=None,
        assessment_suggested_status=None,
        assessment_reason_code=None,
        assessment_reason_text=None,
        assessment_is_confirmed=None,
        assessment_reviewer_id=None,
        assessment_reviewed_at=None,
        assessment_version=None,
        has_unresolved_conflict=False,
        clarification_statuses=[],
        deviation_statuses=[],
    )


def test_vendor_response_docx_keeps_each_specification_row_together() -> None:
    artifact = build_vendor_response_docx([_row(), replace(_row(), serial=2)])
    document = docx.Document(BytesIO(artifact))

    rows = document.tables[0].rows[1:]
    assert len(rows) == 2
    assert all(row._tr.find(qn("w:trPr")).find(qn("w:cantSplit")) is not None for row in rows)
    header_properties = document.tables[0].rows[0]._tr.find(qn("w:trPr"))
    assert header_properties is not None
    assert header_properties.find(qn("w:tblHeader")) is not None
    assert header_properties.find(qn("w:cantSplit")) is not None
    assert document.tables[0].rows[0].height.inches >= 0.35


def test_vendor_response_docx_has_no_boxed_cell_borders() -> None:
    document = docx.Document(BytesIO(build_vendor_response_docx([_row()])))
    table = document.tables[0]
    edges = ("top", "left", "start", "bottom", "right", "end", "insideH", "insideV")

    table_borders = table._tbl.tblPr.find(qn("w:tblBorders"))
    assert table_borders is not None
    assert all(
        table_borders.find(qn(f"w:{edge}")) is not None
        and table_borders.find(qn(f"w:{edge}")).get(qn("w:val")) == "nil"
        for edge in edges
    )
    for row in table.rows:
        for cell in row.cells:
            cell_borders = cell._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
            assert cell_borders is not None
            assert all(
                cell_borders.find(qn(f"w:{edge}")) is not None
                and cell_borders.find(qn(f"w:{edge}")).get(qn("w:val")) == "nil"
                for edge in edges
            )


def test_vendor_response_docx_renders_pdf_private_use_bullets_without_rewriting_text() -> None:
    source = "Accuracy: \uf0b7 better than ±0.5%\nPower supply: \uf0b7 380V"
    row = replace(_row(), tender_requirement=source, raw_source=source)
    document = docx.Document(BytesIO(build_vendor_response_docx([row])))
    cell = document.tables[0].rows[1].cells[1]

    assert cell.text == source
    marker_runs = [run for run in cell.paragraphs[0].runs if run.text == "\uf0b7"]
    assert len(marker_runs) == 2
    assert all(
        run._element.rPr.rFonts.get(qn("w:ascii")) == "Symbol"
        and run._element.rPr.rFonts.get(qn("w:hAnsi")) == "Symbol"
        for run in marker_runs
    )


def test_vendor_response_splits_private_use_bullets_after_a_section_heading() -> None:
    source = (
        "Universal Testing Machine incorporating the following features: "
        "\uf0b7 Auto ranging force readout with ±0.5% accuracy "
        "\uf0b7 Force sampling rate: 1000/s"
    )
    row = replace(_row(), tender_requirement=source, raw_source=source)

    lines = response_sheet_lines([row])

    assert [(line.serial, line.source_text, line.level) for line in lines] == [
        ("1", "Universal Testing Machine incorporating the following features:", 0),
        ("1.1", "\uf0b7 Auto ranging force readout with ±0.5% accuracy", 1),
        ("1.2", "\uf0b7 Force sampling rate: 1000/s", 1),
    ]


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


def test_docx_integrity_rejects_unverified_image_content_in_a_table_cell() -> None:
    from base64 import b64decode
    from io import BytesIO

    from docx import Document
    from docx.shared import Inches

    row_id = str(uuid4())
    requirement_text = "The pump shall deliver 12 L/min."
    headers = ["Requirement ID", "Tender Requirement", "Compliance"]
    document = Document()
    table = document.add_table(rows=2, cols=len(headers))
    for cell, header in zip(table.rows[0].cells, headers, strict=True):
        cell.text = header
    row = table.rows[1]
    row.cells[0].text = row_id
    row.cells[1].text = requirement_text
    # The cell's text matches, but the embedded image may contain additional or
    # substituted visible content which a text-only DOCX read cannot inspect.
    png = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j64sAAAAASUVORK5CYII="
    )
    row.cells[1].paragraphs[0].add_run().add_picture(BytesIO(png), width=Inches(0.01))
    output = BytesIO()
    document.save(output)

    result = validate_generated_requirement_cells(
        [RequirementCell(row_id, requirement_text)],
        output.getvalue(),
        export_format="docx",
        expected_headers=headers,
    )

    assert result.status == "failed"
    assert any(
        issue.row_id == row_id
        and issue.code == "unverified_visual_content"
        and issue.field == "Tender Requirement"
        for issue in result.issues
    )


def test_docx_integrity_checks_all_tables_with_compliance_headers() -> None:
    from io import BytesIO

    from docx import Document

    expected_id = str(uuid4())
    extra_id = str(uuid4())
    headers = ["Requirement ID", "Tender Requirement"]
    document = Document()
    for row_id, text in (
        (expected_id, "The pump shall deliver 12 L/min."),
        (extra_id, "The power supply shall be 230 V."),
    ):
        table = document.add_table(rows=2, cols=2)
        for cell, header in zip(table.rows[0].cells, headers, strict=True):
            cell.text = header
        table.rows[1].cells[0].text = row_id
        table.rows[1].cells[1].text = text
    output = BytesIO()
    document.save(output)

    result = validate_generated_requirement_cells(
        [RequirementCell(expected_id, "The pump shall deliver 12 L/min.")],
        output.getvalue(),
        export_format="docx",
        expected_headers=headers,
    )

    assert result.expected_rows == 1
    assert result.actual_rows == 2
    assert result.status == "failed"
    assert any(
        issue.row_id == extra_id and issue.code == "unexpected_row"
        for issue in result.issues
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


def test_post_render_validator_rejects_clipped_tender_text_in_every_export() -> None:
    full_text = "The pump shall deliver 12 L/min: " + (
        "under continuous operation without loss of pressure; " * 18
    )
    clipped_text = full_text[:-96]
    phase1_row = replace(
        _row(),
        tender_requirement=full_text,
        raw_source=full_text,
        normalized_text=full_text,
    )
    clipped_phase1_row = replace(
        phase1_row,
        tender_requirement=clipped_text,
        raw_source=clipped_text,
        normalized_text=clipped_text,
    )
    final_row = _final_row(full_text)
    clipped_final_row = replace(
        final_row,
        tender_requirement=clipped_text,
        raw_source=clipped_text,
        normalized_text=clipped_text,
    )

    cases = []
    headers, expected = phase1_matrix_xlsx([phase1_row])
    workbook, _checksum = build_matrix_workbook([clipped_phase1_row])
    cases.append(("xlsx", headers, expected, save_matrix_workbook(workbook)))

    headers, expected = vendor_response_docx([phase1_row])
    cases.append(
        (
            "docx",
            headers,
            expected,
            build_vendor_response_docx([clipped_phase1_row]),
        )
    )

    headers, expected = final_matrix_xlsx([final_row])
    workbook, _checksum = build_final_matrix_workbook([clipped_final_row])
    cases.append(("xlsx", headers, expected, save_workbook_bytes(workbook)))

    headers, expected = final_matrix_docx([final_row])
    cases.append(
        (
            "docx",
            headers,
            expected,
            build_final_matrix_docx([clipped_final_row]),
        )
    )

    headers, expected = final_matrix_pdf([final_row])
    cases.append(("pdf", headers, expected, build_final_matrix_pdf([clipped_final_row])))

    for export_format, expected_headers, expected_cells, artifact in cases:
        result = validate_generated_requirement_cells(
            expected_cells,
            artifact,
            export_format=export_format,
            expected_headers=expected_headers,
        )
        assert result.status == "failed", export_format
        assert any(
            issue.code == "changed_text"
            and issue.field == "tender requirement"
            for issue in result.issues
        ), (export_format, result.issues)


def test_post_render_validator_accepts_full_multiline_text_in_every_export() -> None:
    full_text = (
        "Temperature range shall be at least 450–1250°C, with ±2°C accuracy and ≥95% stability.\n"
        + "The measured value, range, and operating condition must remain visible; " * 22
        + "\nThe submitted equipment shall retain the stated values, units, and limits."
    )
    phase1_row = replace(
        _row(),
        tender_requirement=full_text,
        raw_source=full_text,
        normalized_text=full_text,
    )
    final_row = _final_row(full_text)

    cases = []
    headers, expected = phase1_matrix_xlsx([phase1_row])
    workbook, _checksum = build_matrix_workbook([phase1_row])
    cases.append(("xlsx", headers, expected, save_matrix_workbook(workbook)))

    headers, expected = vendor_response_docx([phase1_row])
    cases.append(
        (
            "docx",
            headers,
            expected,
            build_vendor_response_docx([phase1_row]),
        )
    )

    headers, expected = final_matrix_xlsx([final_row])
    workbook, _checksum = build_final_matrix_workbook([final_row])
    cases.append(("xlsx", headers, expected, save_workbook_bytes(workbook)))

    headers, expected = final_matrix_docx([final_row])
    cases.append(("docx", headers, expected, build_final_matrix_docx([final_row])))

    headers, expected = final_matrix_pdf([final_row])
    cases.append(("pdf", headers, expected, build_final_matrix_pdf([final_row])))

    for export_format, expected_headers, expected_cells, artifact in cases:
        result = validate_generated_requirement_cells(
            expected_cells,
            artifact,
            export_format=export_format,
            expected_headers=expected_headers,
        )
        assert result.status == "passed", (export_format, result.issues)
        assert result.expected_rows == result.actual_rows == 1


def test_vendor_response_sheet_separates_numbered_groups_and_lettered_items() -> None:
    heading = replace(
        _row(),
        serial=1,
        raw_source="12. Growth chamber",
        tender_requirement="12. Growth chamber",
    )
    first_item = replace(
        _row(),
        serial=2,
        raw_source="a) Cylindrical chamber with vacuum anneal.",
        tender_requirement="a) Cylindrical chamber with vacuum anneal.",
    )
    second_item = replace(
        _row(),
        serial=3,
        raw_source="b) Provision for 10 effusion cells.",
        tender_requirement="b) Provision for 10 effusion cells.",
    )

    lines = response_sheet_lines([heading, first_item, second_item])

    assert [(line.serial, line.source_text, line.level) for line in lines] == [
        ("12", "12. Growth chamber", 0),
        ("12.a", "a) Cylindrical chamber with vacuum anneal.", 1),
        ("12.b", "b) Provision for 10 effusion cells.", 1),
    ]
    assert [line.display_label for line in lines] == ["12)", "a)", "b)"]
    assert [line.display_text for line in lines] == [
        "Growth chamber",
        "Cylindrical chamber with vacuum anneal.",
        "Provision for 10 effusion cells.",
    ]
    headers, expected = vendor_response_docx([heading, first_item, second_item])
    artifact = build_vendor_response_docx([heading, first_item, second_item])
    result = validate_generated_requirement_cells(
        expected,
        artifact,
        export_format="docx",
        expected_headers=headers,
    )

    assert result.status == "passed", result.issues
    assert result.expected_rows == result.actual_rows == 3
    table = Document(BytesIO(artifact)).tables[0]
    assert len(table.rows) == 4
    assert [table.rows[index].cells[0].text for index in range(1, 4)] == [
        "12)", "a)", "b)"
    ]
    assert all(not table.rows[index].cells[2].text for index in range(1, 4))
    assert all(not table.rows[index].cells[3].text for index in range(1, 4))


def test_vendor_response_sheet_splits_bullets_without_changing_source_text() -> None:
    row = replace(
        _row(),
        raw_source=(
            "Universal Testing Machine\n"
            "• Auto ranging force readout having accuracy of better than ±0.5%\n"
            "• Force sampling rate: 1000/s"
        ),
        tender_requirement=(
            "Universal Testing Machine\n"
            "• Auto ranging force readout having accuracy of better than ±0.5%\n"
            "• Force sampling rate: 1000/s"
        ),
    )

    lines = response_sheet_lines([row])

    assert [line.level for line in lines] == [0, 1, 1]
    assert [line.serial for line in lines] == ["1", "1.1", "1.2"]
    assert [line.display_label for line in lines] == ["1)", "a)", "b)"]
    assert [line.source_text for line in lines] == [
        "Universal Testing Machine",
        "• Auto ranging force readout having accuracy of better than ±0.5%",
        "• Force sampling rate: 1000/s",
    ]
    assert [line.display_text for line in lines] == [
        "Universal Testing Machine",
        "Auto ranging force readout having accuracy of better than ±0.5%",
        "Force sampling rate: 1000/s",
    ]
    rendered = Document(BytesIO(build_vendor_response_docx([row])))
    assert rendered.sections[0].page_width.inches == pytest.approx(11.69, abs=0.01)
    assert rendered.sections[0].page_height.inches == pytest.approx(8.27, abs=0.01)


def test_bullet_rows_get_contiguous_numbers_under_their_source_parent() -> None:
    heading = replace(
        _row(), serial=3, raw_source="Scribing head", tender_requirement="Scribing head"
    )
    bullets = [
        replace(_row(), serial=index, raw_source=f"• Requirement {index}",
                tender_requirement=f"• Requirement {index}")
        for index in range(4, 7)
    ]

    lines = response_sheet_lines([heading, *bullets])

    assert [line.serial for line in lines] == ["3", "3.1", "3.2", "3.3"]
    assert [line.display_label for line in lines] == ["3)", "a)", "b)", "c)"]


def test_bullet_groups_start_at_their_own_requirement_number() -> None:
    unlabelled_group = replace(
        _row(),
        serial=2,
        raw_source="• First source item\n• Second source item",
        tender_requirement="• First source item\n• Second source item",
    )
    titled_group = replace(
        _row(),
        serial=3,
        raw_source="Accessories\n• First accessory\n• Second accessory",
        tender_requirement="Accessories\n• First accessory\n• Second accessory",
    )

    lines = response_sheet_lines([unlabelled_group, titled_group])

    assert [line.serial for line in lines] == [
        "2", "2.1", "3", "3.1", "3.2"
    ]
    assert [line.display_label for line in lines] == [
        "2)", "a)", "3)", "a)", "b)"
    ]
    assert len({line.bookmark_name for line in lines}) == len(lines)
    headers, expected = vendor_response_docx([unlabelled_group, titled_group])
    artifact = build_vendor_response_docx([unlabelled_group, titled_group])
    result = validate_generated_requirement_cells(
        expected, artifact, export_format="docx", expected_headers=headers
    )
    assert result.status == "passed", result.issues
    table = Document(BytesIO(artifact)).tables[0]
    assert [row.cells[0].text for row in table.rows[1:]] == [
        "2)", "a)", "3)", "a)", "b)"
    ]


def test_vendor_response_alphabetic_labels_continue_after_z() -> None:
    source = "Specification group\n" + "\n".join(
        f"• Requirement {index} at {100 + index} kN" for index in range(1, 29)
    )
    row = replace(_row(), raw_source=source, tender_requirement=source)

    lines = response_sheet_lines([row])

    assert lines[0].display_label == "1)"
    assert [line.display_label for line in lines[1:]][-3:] == ["z)", "aa)", "ab)"]
    assert lines[-1].source_text == "• Requirement 28 at 128 kN"
    assert lines[-1].display_text == "Requirement 28 at 128 kN"


def test_vendor_response_sheet_splits_inline_pdf_bullets_and_parameter_cell() -> None:
    row = replace(
        _row(),
        raw_source="Wafer Chuck (1 number) | • Vacuum-backed chuck • XY movement range: 25 mm",
        tender_requirement=(
            "Wafer Chuck (1 number) | • Vacuum-backed chuck • XY movement range: 25 mm"
        ),
    )

    lines = response_sheet_lines([row])

    assert [(line.serial, line.item_text, line.source_text, line.level) for line in lines] == [
        ("1", "Wafer Chuck (1 number)", "", 0),
        ("1.1", "", "• Vacuum-backed chuck", 1),
        ("1.2", "", "• XY movement range: 25 mm", 1),
    ]
    assert [line.display_label for line in lines] == ["1)", "a)", "b)"]
    assert [line.display_text for line in lines] == [
        "Wafer Chuck (1 number)",
        "Vacuum-backed chuck",
        "XY movement range: 25 mm",
    ]
    headers, expected = vendor_response_docx([row])
    result = validate_generated_requirement_cells(
        expected,
        build_vendor_response_docx([row]),
        export_format="docx",
        expected_headers=headers,
    )
    assert result.status == "passed", result.issues


def test_vendor_response_sheet_splits_flattened_sequential_numbered_items() -> None:
    source = (
        "Terms & Conditions: 1. 500% Overload capacity in both modes "
        "2. Universal Testing Machine shall perform cyclic testing with "
        "minimum 5000 cycles and 0.5% accuracy "
        "3. Online demonstration during Technical Evaluation"
    )
    row = replace(_row(), serial=8, raw_source=source, tender_requirement=source)

    lines = response_sheet_lines([row])

    assert [(line.serial, line.source_text, line.level) for line in lines] == [
        ("8", "Terms & Conditions:", 0),
        ("8.1", "1. 500% Overload capacity in both modes", 1),
        (
            "8.2",
            "2. Universal Testing Machine shall perform cyclic testing with "
            "minimum 5000 cycles and 0.5% accuracy",
            1,
        ),
        (
            "8.3",
            "3. Online demonstration during Technical Evaluation",
            1,
        ),
    ]
    assert [line.display_label for line in lines] == ["8)", "a)", "b)", "c)"]
    assert [line.display_text for line in lines] == [
        "Terms & Conditions:",
        "500% Overload capacity in both modes",
        "Universal Testing Machine shall perform cyclic testing with minimum "
        "5000 cycles and 0.5% accuracy",
        "Online demonstration during Technical Evaluation",
    ]


def test_post_render_validator_rejects_missing_and_duplicate_rows_in_every_export() -> None:
    phase1_row = _row()
    final_row = _final_row(phase1_row.raw_source)
    cases = []

    headers, expected = phase1_matrix_xlsx([phase1_row])
    cases.append(
        (
            "xlsx",
            headers,
            expected,
            lambda rows: save_matrix_workbook(build_matrix_workbook(rows)[0]),
            phase1_row,
        )
    )

    headers, expected = vendor_response_docx([phase1_row])
    cases.append(
        (
            "docx",
            headers,
            expected,
            lambda rows: build_vendor_response_docx(rows),
            phase1_row,
        )
    )

    headers, expected = final_matrix_xlsx([final_row])
    cases.append(
        (
            "xlsx",
            headers,
            expected,
            lambda rows: save_workbook_bytes(build_final_matrix_workbook(rows)[0]),
            final_row,
        )
    )

    headers, expected = final_matrix_docx([final_row])
    cases.append(
        ("docx", headers, expected, build_final_matrix_docx, final_row)
    )

    headers, expected = final_matrix_pdf([final_row])
    cases.append(("pdf", headers, expected, build_final_matrix_pdf, final_row))

    for export_format, expected_headers, expected_cells, build, row in cases:
        missing = validate_generated_requirement_cells(
            expected_cells,
            build([]),
            export_format=export_format,
            expected_headers=expected_headers,
        )
        assert missing.status == "failed", export_format
        assert any(issue.code == "missing_row" for issue in missing.issues), (
            export_format,
            missing.issues,
        )

        duplicated = validate_generated_requirement_cells(
            expected_cells,
            build([row, row]),
            export_format=export_format,
            expected_headers=expected_headers,
        )
        assert duplicated.status == "failed", export_format
        assert any(issue.code == "duplicate_row" for issue in duplicated.issues), (
            export_format,
            duplicated.issues,
        )
