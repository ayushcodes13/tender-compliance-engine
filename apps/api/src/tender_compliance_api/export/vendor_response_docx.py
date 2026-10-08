"""Tender-derived blank vendor response sheet (CP68).

The document presents reviewed tender requirements for an OEM to answer. It
does not infer or populate compliance, deviations, or evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from tender_compliance_api.matrix.projection import MatrixRow


def build_vendor_response_docx(
    rows: Sequence[MatrixRow],
    *,
    tender_name: str,
    document_version: int,
    generated_at: datetime | None = None,
) -> bytes:
    """Build a blank response template from the canonical Phase 1 rows."""
    if generated_at is None:
        generated_at = datetime.now(UTC)

    document = docx.Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)

    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(10)
    title_run = title.add_run("Tender Vendor Response Sheet")
    title_run.bold = True
    title_run.font.size = Pt(24)
    title_run.font.color.rgb = RGBColor(0, 0, 0)
    for label, value in (
        ("Tender document", tender_name),
        ("Tender document version", str(document_version)),
        ("Generated", generated_at.strftime("%Y-%m-%d %H:%M UTC")),
    ):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.add_run(f"{label}: ").bold = True
        paragraph.add_run(value)
    document.add_paragraph(
        "The OEM should complete the compliance and deviation/remarks columns. "
        "Review status and source locations are included to support verification."
    )

    headers = (
        "S.No.",
        "Tender requirement",
        "Clause",
        "Source page",
        "Review status",
        "OEM compliance (Yes / No / Partial)",
        "Deviation / remarks",
    )
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    widths = (0.45, 5.3, 0.7, 0.6, 0.95, 1.3, 1.2)
    header_row_properties = table.rows[0]._tr.get_or_add_trPr()
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    header_row_properties.append(repeat_header)
    for index, (header, width) in enumerate(zip(headers, widths, strict=True)):
        cell = table.rows[0].cells[index]
        cell.text = header
        cell.width = Inches(width)
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(8)

    for row in rows:
        cells = table.add_row().cells
        values = (
            str(row.serial),
            row.tender_requirement,
            row.clause or "",
            str(row.source_page) if row.source_page is not None else "",
            row.review_status.replace("_", " ").title(),
            "",
            "",
        )
        for index, (cell, value, width) in enumerate(
            zip(cells, values, widths, strict=True)
        ):
            cell.text = value
            cell.width = Inches(width)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(2)
                for run in paragraph.runs:
                    run.font.size = Pt(8)
            if index in (0, 3, 4, 5):
                for paragraph in cell.paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
