"""Blank technical-specification response sheet (CP68)."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from tender_compliance_api.matrix.projection import MatrixRow


def _set_cell_shading(cell: docx.table._Cell, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_margins(cell: docx.table._Cell) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for side, value in (("top", "90"), ("start", "100"), ("bottom", "90"), ("end", "100")):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), value)
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    properties.append(margins)


def build_vendor_response_docx(rows: Sequence[MatrixRow]) -> bytes:
    """Build the sample-aligned technical sheet with blank bidder response cells.

    The technical specification cell is the exact source quote carried by the
    canonical matrix projection. No review metadata, interpretation, or
    pre-filled compliance assessment is added to this response document.
    """
    document = docx.Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)

    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(12)
    title_run = title.add_run("Technical Specification Sheet")
    title_run.bold = True
    title_run.font.size = Pt(20)
    title_run.font.color.rgb = RGBColor(18, 32, 58)

    headers = (
        "S.No.",
        "Technical Specification",
        "Compliance (Yes / No)",
        "Any Deviation",
    )
    widths = (0.55, 6.35, 1.45, 1.45)
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False

    header_row = table.rows[0]
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    header_row._tr.get_or_add_trPr().append(repeat_header)
    for index, (header, width) in enumerate(zip(headers, widths, strict=True)):
        cell = header_row.cells[index]
        cell.width = Inches(width)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_shading(cell, "17365D")
        _set_cell_margins(cell)
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if index != 1 else WD_ALIGN_PARAGRAPH.LEFT
            )
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(255, 255, 255)

    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        # Keep the serial number and its full specification together when the
        # row fits on a page. Word still splits rows taller than a page.
        row_properties = table.rows[-1]._tr.get_or_add_trPr()
        prevent_split = OxmlElement("w:cantSplit")
        row_properties.append(prevent_split)
        values = (str(row.serial), row.tender_requirement, "", "")
        for index, (cell, value, width) in enumerate(zip(cells, values, widths, strict=True)):
            cell.width = Inches(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            _set_cell_margins(cell)
            if row_index % 2:
                _set_cell_shading(cell, "F3F6FA")
            cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                paragraph.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER if index in (0, 2, 3) else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(31, 41, 55)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
