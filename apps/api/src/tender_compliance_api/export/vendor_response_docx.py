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

from tender_compliance_api.export.vendor_response_rows import response_sheet_lines
from tender_compliance_api.matrix.projection import MatrixRow


def _set_cell_shading(cell: docx.table._Cell, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _remove_table_borders(table: docx.table.Table) -> None:
    """Keep the response columns aligned without printing a box around each cell."""
    edges = (
        "top",
        "left",
        "start",
        "bottom",
        "right",
        "end",
        "insideH",
        "insideV",
    )

    table_properties = table._tbl.tblPr
    table_borders = table_properties.find(qn("w:tblBorders"))
    if table_borders is None:
        table_borders = OxmlElement("w:tblBorders")
        table_properties.append(table_borders)
    for edge in edges:
        border = table_borders.find(qn(f"w:{edge}"))
        if border is None:
            border = OxmlElement(f"w:{edge}")
            table_borders.append(border)
        border.set(qn("w:val"), "nil")

    # Explicit cell-level nil borders override borders inherited from Word's
    # table styles, including when a DOCX is opened in another office suite.
    for row in table.rows:
        for cell in row.cells:
            cell_properties = cell._tc.get_or_add_tcPr()
            cell_borders = cell_properties.find(qn("w:tcBorders"))
            if cell_borders is None:
                cell_borders = OxmlElement("w:tcBorders")
                cell_properties.append(cell_borders)
            for edge in edges:
                border = cell_borders.find(qn(f"w:{edge}"))
                if border is None:
                    border = OxmlElement(f"w:{edge}")
                    cell_borders.append(border)
                border.set(qn("w:val"), "nil")


def _set_cell_margins(cell: docx.table._Cell) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for side, value in (("top", "60"), ("start", "100"), ("bottom", "60"), ("end", "100")):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), value)
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    properties.append(margins)


def _set_source_text(cell: docx.table._Cell, value: str) -> None:
    """Keep source text intact while rendering PDF private-use bullets.

    Some tender PDFs map the visible bullet glyph to U+F0B7. The document
    content stream is source-faithful, but ordinary body fonts often lack that
    private-use character and silently render it as blank space. Isolate only
    those marker characters in a Symbol-font run so they remain visible while
    the stored text remains unchanged for source validation.
    """
    cell.text = ""
    paragraph = cell.paragraphs[0]
    parts = value.split("\uf0b7")
    for index, part in enumerate(parts):
        if part:
            paragraph.add_run(part)
        if index < len(parts) - 1:
            marker = paragraph.add_run("\uf0b7")
            marker.font.name = "Symbol"
            properties = marker._element.get_or_add_rPr()
            fonts = properties.rFonts
            if fonts is None:
                fonts = OxmlElement("w:rFonts")
                properties.insert(0, fonts)
            for font_type in ("ascii", "hAnsi", "eastAsia", "cs"):
                fonts.set(qn(f"w:{font_type}"), "Symbol")


def build_vendor_response_docx(rows: Sequence[MatrixRow]) -> bytes:
    """Build the sample-aligned technical sheet with blank bidder response cells.

    The technical specification cell is the exact source quote carried by the
    canonical matrix projection. No review metadata, interpretation, or
    pre-filled compliance assessment is added to this response document.
    """
    document = docx.Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    # A4 landscape gives the technical column enough width for long tender
    # clauses while remaining the standard sheet size for the supplied bids.
    section.page_width = Inches(11.69)
    section.page_height = Inches(8.27)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    section.top_margin = Inches(0.4)
    section.bottom_margin = Inches(0.4)

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
    widths = (0.7, 6.45, 1.55, 1.55)
    table = document.add_table(rows=1, cols=len(headers))
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
                WD_ALIGN_PARAGRAPH.LEFT if index == 1 else WD_ALIGN_PARAGRAPH.CENTER
            )
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(255, 255, 255)

    for row_index, line in enumerate(response_sheet_lines(rows)):
        cells = table.add_row().cells
        # Keep each row together when it fits on a page. Word still splits
        # rows taller than a page.
        row_properties = table.rows[-1]._tr.get_or_add_trPr()
        prevent_split = OxmlElement("w:cantSplit")
        row_properties.append(prevent_split)
        source_text = "\n".join(
            part for part in (line.item_text, line.source_text) if part
        )
        values = (line.serial, source_text, "", "")
        for index, (cell, value, width) in enumerate(zip(cells, values, widths, strict=True)):
            cell.width = Inches(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            _set_cell_margins(cell)
            if line.level == 0:
                _set_cell_shading(cell, "E8EEF6")
            elif row_index % 2:
                _set_cell_shading(cell, "F3F6FA")
            if index == 1:
                _set_source_text(cell, value)
            else:
                cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                if index == 1 and line.level > 0:
                    paragraph.paragraph_format.left_indent = Inches(0.22)
                paragraph.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER
                    if index in (0, 2, 3)
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in paragraph.runs:
                    if line.level == 0:
                        run.bold = True
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(31, 41, 55)

    _remove_table_borders(table)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
