"""Post-render integrity checks for tender-derived requirement cells.

This module checks the artifact bytes produced by an exporter, rather than
assuming the projection passed to the exporter is what the client received.
Whitespace may vary because spreadsheet/document layouts wrap lines; every
non-whitespace character in the tender requirement must remain unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

import pymupdf
from docx import Document
from openpyxl import load_workbook  # type: ignore[import-untyped]

ValidationStatus = Literal["passed", "failed"]
ExportFormatName = Literal["xlsx", "docx", "pdf"]


@dataclass(frozen=True)
class RequirementCell:
    row_id: str
    text: str


@dataclass(frozen=True)
class CellIssue:
    row_id: str
    code: Literal[
        "missing_row",
        "missing_text",
        "changed_text",
        "unexpected_row",
        "duplicate_row",
    ]


@dataclass(frozen=True)
class ExportIntegrityResult:
    status: ValidationStatus
    expected_rows: int
    actual_rows: int
    issues: tuple[CellIssue, ...]


@dataclass(frozen=True)
class SourceQuoteIssue:
    row_id: str
    code: Literal["source_text_unavailable", "source_quote_not_found"]


def _content_key(value: str) -> str:
    """Normalize layout whitespace only; preserve all letters and symbols."""
    return re.sub(r"\s+", " ", value).strip()


def _docx_cells(data: bytes) -> list[RequirementCell]:
    document: Any = Document(BytesIO(data))
    for table in document.tables:
        if not table.rows:
            continue
        headers = [_content_key(cell.text).casefold() for cell in table.rows[0].cells]
        if "requirement id" in headers and "tender requirement" in headers:
            id_idx = headers.index("requirement id")
            text_idx = headers.index("tender requirement")
            return [
                RequirementCell(
                    row_id=_content_key(row.cells[id_idx].text),
                    text=row.cells[text_idx].text,
                )
                for row in table.rows[1:]
                if len(row.cells) > max(id_idx, text_idx)
            ]
        if "s.no." in headers and "tender requirement" in headers:
            id_idx = headers.index("s.no.")
            text_idx = headers.index("tender requirement")
            return [
                RequirementCell(
                    row_id=_content_key(row.cells[id_idx].text),
                    text=row.cells[text_idx].text,
                )
                for row in table.rows[1:]
                if len(row.cells) > max(id_idx, text_idx)
            ]
    return []


def _xlsx_cells(data: bytes) -> list[RequirementCell]:
    workbook: Any = load_workbook(
        BytesIO(data), read_only=True, data_only=True
    )
    try:
        for sheet in workbook.worksheets:
            for row_number, values in enumerate(
                sheet.iter_rows(min_row=1, max_row=20, values_only=True),
                start=1,
            ):
                headers = [
                    _content_key(str(value or "")).casefold() for value in values
                ]
                if "requirement id" not in headers or "tender requirement" not in headers:
                    continue
                id_idx = headers.index("requirement id")
                text_idx = headers.index("tender requirement")
                return [
                    RequirementCell(
                        row_id=_content_key(str(data_row[id_idx] or "")),
                        text=str(data_row[text_idx] or ""),
                    )
                    for data_row in sheet.iter_rows(
                        min_row=row_number + 1, values_only=True
                    )
                    if len(data_row) > max(id_idx, text_idx)
                    and isinstance(data_row[id_idx], str)
                    and re.fullmatch(
                        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                        data_row[id_idx],
                    ) is not None
                ]
        return []
    finally:
        workbook.close()


def _pdf_text_pages(data: bytes) -> list[str]:
    document: Any = pymupdf.open(  # type: ignore[no-untyped-call]
        stream=data, filetype="pdf"
    )
    try:
        return [
            document.load_page(page_number).get_text(sort=True)
            for page_number in range(document.page_count)
        ]
    finally:
        document.close()


def validate_generated_requirement_cells(
    expected: Sequence[RequirementCell],
    artifact_bytes: bytes,
    export_format: ExportFormatName,
) -> ExportIntegrityResult:
    """Verify every expected row and tender requirement in rendered bytes.

    PDF rows are validated by their complete requirement text and stable
    requirement IDs in the extracted PDF text layer. DOCX/XLSX rows are
    matched by their row identity and checked cell by cell.
    """
    issues: list[CellIssue] = []
    if export_format == "pdf":
        pages = _pdf_text_pages(artifact_bytes)
        # The first page contains document metadata, including its document
        # UUID. Requirement IDs appear only in the subsequent data pages.
        artifact_text = _content_key("\n".join(pages[1:]))
        row_ids = [_content_key(row_id) for row_id in re.findall(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            artifact_text,
        )]
        expected_ids = [row.row_id for row in expected]
        for row in expected:
            if row.row_id not in artifact_text:
                issues.append(CellIssue(row.row_id, "missing_row"))
            elif not _content_key(row.text) or _content_key(row.text) not in artifact_text:
                issues.append(CellIssue(row.row_id, "missing_text"))
            elif row_ids.count(row.row_id) > 1:
                issues.append(CellIssue(row.row_id, "duplicate_row"))
        for extra_id in sorted(set(row_ids) - set(expected_ids)):
            issues.append(CellIssue(extra_id, "unexpected_row"))
        return ExportIntegrityResult(
            status="failed" if issues else "passed",
            expected_rows=len(expected),
            actual_rows=len(set(row_ids)),
            issues=tuple(issues),
        )

    actual = _xlsx_cells(artifact_bytes) if export_format == "xlsx" else _docx_cells(artifact_bytes)
    actual_by_id = {row.row_id: row for row in actual}
    for row in expected:
        emitted = actual_by_id.get(row.row_id)
        if emitted is None:
            issues.append(CellIssue(row.row_id, "missing_row"))
        elif not _content_key(emitted.text):
            issues.append(CellIssue(row.row_id, "missing_text"))
        elif _content_key(emitted.text) != _content_key(row.text):
            issues.append(CellIssue(row.row_id, "changed_text"))
    expected_id_set = {row.row_id for row in expected}
    actual_ids = {row.row_id for row in actual}
    for extra_id in sorted(actual_ids - expected_id_set):
        issues.append(CellIssue(extra_id, "unexpected_row"))
    seen_ids: set[str] = set()
    for row in actual:
        if row.row_id in seen_ids:
            issues.append(CellIssue(row.row_id, "duplicate_row"))
        seen_ids.add(row.row_id)
    return ExportIntegrityResult(
        status="failed" if issues else "passed",
        expected_rows=len(expected),
        actual_rows=len(actual),
        issues=tuple(issues),
    )


def validate_source_quote_presence(
    expected: Sequence[RequirementCell],
    authorized_sources: Mapping[str, Sequence[str]],
) -> tuple[SourceQuoteIssue, ...]:
    """Check source wording only inside the pages authorized for each row."""
    issues: list[SourceQuoteIssue] = []
    for row in expected:
        sources = [text for text in authorized_sources.get(row.row_id, ()) if text]
        if not sources:
            issues.append(SourceQuoteIssue(row.row_id, "source_text_unavailable"))
            continue
        quote = _content_key(row.text)
        combined_sources = [_content_key(text) for text in sources]
        if not quote or not any(quote in source for source in combined_sources):
            issues.append(SourceQuoteIssue(row.row_id, "source_quote_not_found"))
    return tuple(issues)


__all__ = [
    "CellIssue",
    "ExportIntegrityResult",
    "RequirementCell",
    "SourceQuoteIssue",
    "validate_generated_requirement_cells",
    "validate_source_quote_presence",
]
