"""Export module — XLSX, DOCX, and PDF generation (CP42, CP60).

CP42 provides Phase 1 matrix XLSX export.  CP60 extends this to the final
(CP59) projection in XLSX, DOCX, and PDF formats.
"""

from tender_compliance_api.export.xlsx import (
    COLUMN_WIDTHS,
    HEADER_FILL,
    HEADER_FONT,
    MATRIX_COLUMNS,
    build_matrix_workbook,
    save_matrix_workbook,
)

__all__ = [
    "COLUMN_WIDTHS",
    "HEADER_FILL",
    "HEADER_FONT",
    "MATRIX_COLUMNS",
    "build_matrix_workbook",
    "save_matrix_workbook",
]
