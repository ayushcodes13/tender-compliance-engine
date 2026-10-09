"""Post-render integrity checks for generated compliance-sheet cells.

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
    fields: Mapping[str, str] | None = None
    source_page: int | None = None


@dataclass(frozen=True)
class CellIssue:
    row_id: str
    code: Literal[
        "missing_row",
        "missing_text",
        "changed_text",
        "unexpected_row",
        "duplicate_row",
        "missing_column",
        "unexpected_column",
        "changed_cell",
        "unverified_visual_content",
    ]
    field: str | None = None


@dataclass(frozen=True)
class ExportIntegrityResult:
    status: ValidationStatus
    expected_rows: int
    actual_rows: int
    issues: tuple[CellIssue, ...]


@dataclass(frozen=True)
class SourceQuoteIssue:
    row_id: str
    code: Literal[
        "source_text_unavailable",
        "source_quote_not_found",
        "ocr_visual_verification_required",
    ]


@dataclass(frozen=True)
class AuthorizedSourceFragment:
    """A source excerpt tied to one page of the authorized document version."""

    page_number: int | None
    text: str
    page_local: bool = True
    char_start: int | None = None


def _content_key(value: str) -> str:
    """Normalize layout whitespace only; preserve all letters and symbols."""
    return re.sub(r"\s+", " ", value).strip()


def _source_quote_key(value: str) -> str:
    """Normalize layout and standalone list markers for source quote checks.

    Some PDF text extractors expose Word's private-use bullet glyph even when
    the generated DOCX stores that marker as list formatting. Only a marker at
    the start of a line is presentation; bullets inside wording stay literal.
    """
    without_list_markers = re.sub(
        r"(?m)^[ \t]*[•\u2022\u2023\u25e6\u25aa\u25cf\uf0a7\uf0b7][ \t]+",
        "",
        value,
    )
    return _content_key(without_list_markers)


def _docx_table(
    data: bytes,
) -> tuple[list[str], list[dict[str, str]], list[CellIssue]]:
    document: Any = Document(BytesIO(data))
    output_headers: list[str] = []
    rows: list[dict[str, str]] = []
    docx_issues: list[CellIssue] = []
    for table in document.tables:
        if not table.rows:
            continue
        headers = [_content_key(cell.text).casefold() for cell in table.rows[0].cells]
        if not any(h in headers for h in ("requirement id", "s.no.")):
            continue
        if "tender requirement" not in headers:
            continue
        original_headers = [_content_key(cell.text) for cell in table.rows[0].cells]
        if not output_headers:
            output_headers = original_headers
        else:
            known = {header.casefold() for header in output_headers}
            current = {header.casefold() for header in original_headers}
            docx_issues.extend(
                CellIssue("", "missing_column", header)
                for header in sorted(known - current)
            )
            docx_issues.extend(
                CellIssue("", "unexpected_column", header)
                for header in sorted(current - known)
            )
        id_index = (
            headers.index("requirement id")
            if "requirement id" in headers
            else headers.index("s.no.")
        )
        for row in table.rows[1:]:
            row_id = _content_key(row.cells[id_index].text)
            rows.append(
                {
                    original_headers[index]: cell.text
                    for index, cell in enumerate(row.cells)
                    if index < len(original_headers)
                }
            )
            for index, cell in enumerate(row.cells):
                if index >= len(original_headers):
                    continue
                if cell._tc.xpath(".//w:drawing | .//w:pict"):
                    docx_issues.append(
                        CellIssue(
                            row_id=row_id,
                            code="unverified_visual_content",
                            field=original_headers[index],
                        )
                    )
    return output_headers, rows, docx_issues


def _xlsx_table(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    workbook: Any = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            for row_number, values in enumerate(
                sheet.iter_rows(min_row=1, max_row=20, values_only=True),
                start=1,
            ):
                headers = [_content_key(str(value or "")).casefold() for value in values]
                has_identity = any(header in headers for header in ("requirement id", "s.no."))
                if not has_identity or "tender requirement" not in headers:
                    continue
                original_headers = [_content_key(str(value or "")) for value in values]
                id_idx = (
                    headers.index("requirement id")
                    if "requirement id" in headers
                    else headers.index("s.no.")
                )
                rows: list[dict[str, str]] = []
                for data_row in sheet.iter_rows(min_row=row_number + 1, values_only=True):
                    if len(data_row) <= id_idx:
                        continue
                    identity = str(data_row[id_idx] or "")
                    if (
                        "requirement id" in headers
                        and re.fullmatch(
                            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                            identity,
                        )
                        is None
                    ):
                        continue
                    if "requirement id" not in headers and re.fullmatch(r"\d+", identity) is None:
                        continue
                    rows.append(
                        {
                            original_headers[index]: str(value or "")
                            for index, value in enumerate(data_row)
                            if index < len(original_headers)
                        }
                    )
                return original_headers, rows
        return [], []
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


def _pdf_table(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Read PDF table cells by their rendered column and row coordinates."""
    from tender_compliance_api.export.final_pdf import _COLUMNS, _FOOTER_H, _MARGIN

    document: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    try:
        column_starts: list[float] = []
        current_x = _MARGIN
        for _field, _header, width in _COLUMNS:
            column_starts.append(current_x)
            current_x += width
        headers: list[str] = []
        rows: list[dict[str, str]] = []
        for page_number in range(1, document.page_count):
            page = document.load_page(page_number)
            words = page.get_text("words", sort=False)
            if page_number == 1:
                headers = page.get_text("text").splitlines()[: len(_COLUMNS)]
            id_index = next(
                index
                for index, (field, _header, _width) in enumerate(_COLUMNS)
                if field == "requirement_id"
            )
            id_left = column_starts[id_index]
            id_right = id_left + _COLUMNS[id_index][2]
            row_blocks = [
                word
                for word in words
                if id_left <= float(word[0]) < id_right
                and re.fullmatch(
                    r"\s*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s*",
                    str(word[4]),
                )
            ]
            row_blocks.sort(key=lambda word: float(word[1]))
            row_starts = [float(word[1]) for word in row_blocks]
            for row_index, _id_word in enumerate(row_blocks):
                top = row_starts[row_index] - 1
                bottom = (
                    row_starts[row_index + 1] - 1
                    if row_index + 1 < len(row_starts)
                    else float(page.rect.height) - _MARGIN - _FOOTER_H
                )
                values: dict[str, str] = {}
                for column_index, (_field, header, width) in enumerate(_COLUMNS):
                    left = column_starts[column_index]
                    right = left + width
                    cell_words = [
                        word
                        for word in words
                        if left <= float(word[0]) < right and top <= float(word[1]) < bottom
                    ]
                    cell_words.sort(key=lambda word: (float(word[1]), float(word[0])))
                    values[header] = " ".join(
                        str(word[4]).strip() for word in cell_words if str(word[4]).strip()
                    )
                rows.append(values)
        return headers, rows
    finally:
        document.close()


def validate_generated_requirement_cells(
    expected: Sequence[RequirementCell],
    artifact_bytes: bytes,
    export_format: ExportFormatName,
    expected_headers: Sequence[str] = (),
) -> ExportIntegrityResult:
    """Verify every expected row and tender requirement in rendered bytes.

    All formats are checked for their expected table columns and row identities.
    DOCX/XLSX/PDF rows are matched by row identity and every displayed value is
    compared with its owning projection field. Tender wording is additionally
    checked against the authorized source version and page by the caller.
    """
    issues: list[CellIssue] = []
    if export_format == "pdf":
        actual_headers, actual_fields = _pdf_table(artifact_bytes)
        visual_issues: list[CellIssue] = []
    elif export_format == "xlsx":
        actual_headers, actual_fields = _xlsx_table(artifact_bytes)
        visual_issues = []
    else:
        actual_headers, actual_fields, visual_issues = _docx_table(artifact_bytes)
    issues.extend(visual_issues)

    def header_key(value: str) -> str:
        return _content_key(value).casefold()

    expected_header_keys = {header_key(value) for value in expected_headers}
    actual_header_keys = [header_key(value) for value in actual_headers]
    actual_header_set = set(actual_header_keys)
    if expected_header_keys:
        for missing_header in sorted(expected_header_keys - actual_header_set):
            issues.append(CellIssue("", "missing_column", missing_header))
        for extra_header in sorted(actual_header_set - expected_header_keys):
            issues.append(CellIssue("", "unexpected_column", extra_header))

    identity_header = "requirement id" if "requirement id" in actual_header_set else "s.no."
    actual: list[RequirementCell] = []
    for field_row in actual_fields:
        normalized = {header_key(key): value for key, value in field_row.items()}
        row_id = _content_key(normalized.get(identity_header, ""))
        text = normalized.get("tender requirement", "")
        actual.append(
            RequirementCell(
                row_id=row_id,
                text=text,
                fields=normalized,
            )
        )
    actual_by_id = {row.row_id: row for row in actual}
    for expected_row in expected:
        emitted = actual_by_id.get(expected_row.row_id)
        if emitted is None:
            issues.append(CellIssue(expected_row.row_id, "missing_row"))
        elif not _content_key(emitted.text):
            issues.append(CellIssue(expected_row.row_id, "missing_text"))
        elif _content_key(emitted.text) != _content_key(expected_row.text):
            issues.append(CellIssue(expected_row.row_id, "changed_text", "tender requirement"))
        if emitted is not None and expected_row.fields:
            emitted_fields = emitted.fields or {}
            for field, expected_value in expected_row.fields.items():
                if header_key(field) == "tender requirement":
                    continue
                actual_value = emitted_fields.get(header_key(field))
                if actual_value is None or _content_key(actual_value) != _content_key(
                    expected_value
                ):
                    issues.append(CellIssue(expected_row.row_id, "changed_cell", field))
    expected_id_set = {row.row_id for row in expected}
    actual_ids = {row.row_id for row in actual}
    for extra_id in sorted(actual_ids - expected_id_set):
        issues.append(CellIssue(extra_id, "unexpected_row"))
    seen_ids: set[str] = set()
    for actual_row in actual:
        if actual_row.row_id in seen_ids:
            issues.append(CellIssue(actual_row.row_id, "duplicate_row"))
        seen_ids.add(actual_row.row_id)
    return ExportIntegrityResult(
        status="failed" if issues else "passed",
        expected_rows=len(expected),
        actual_rows=len(actual),
        issues=tuple(issues),
    )


def validate_source_quote_presence(
    expected: Sequence[RequirementCell],
    authorized_sources: Mapping[
        str, Sequence[str | AuthorizedSourceFragment]
    ],
) -> tuple[SourceQuoteIssue, ...]:
    """Check exact quotes on one page or across ordered contiguous page fragments."""
    issues: list[SourceQuoteIssue] = []
    for row in expected:
        raw_sources = [
            source
            for source in authorized_sources.get(row.row_id, ())
            if (source.text if isinstance(source, AuthorizedSourceFragment) else source)
        ]
        sources = [
            source
            if isinstance(source, AuthorizedSourceFragment)
            else AuthorizedSourceFragment(page_number=None, text=source)
            for source in raw_sources
        ]
        if not sources:
            issues.append(SourceQuoteIssue(row.row_id, "source_text_unavailable"))
            continue
        quote = _source_quote_key(row.text)
        exact_sources = sources
        all_full_matches = [
            source
            for source in exact_sources
            if quote in _source_quote_key(source.text)
        ]
        full_matches = [
            source
            for source in all_full_matches
            if row.source_page is None or source.page_number == row.source_page
        ]
        # A full window copied onto several page anchors is not page-specific
        # evidence for a cross-page quote. New anchors carry the exact page
        # fragments instead; legacy single-page records remain compatible.
        full_match_pages = {source.page_number for source in all_full_matches}
        full_match_texts = {
            _content_key(source.text) for source in all_full_matches
        }
        full_match_is_page_specific = (
            any(source.page_number is None for source in full_matches)
            or len(full_match_pages) <= 1
            or len(full_match_texts) > 1
        )
        found = bool(quote and full_matches and full_match_is_page_specific)

        if not found and quote:
            page_fragments = [
                source
                for source in exact_sources
                if source.page_number is not None and source.page_local
            ]
            page_fragments.sort(
                key=lambda source: (
                    source.page_number,
                    source.char_start if source.char_start is not None else -1,
                )
            )
            runs: list[list[AuthorizedSourceFragment]] = []
            for source in page_fragments:
                previous_page = runs[-1][-1].page_number if runs else None
                if not runs or source.page_number != (previous_page or 0) + 1:
                    runs.append([source])
                else:
                    runs[-1].append(source)
            found = any(
                quote == _source_quote_key("\n".join(source.text for source in run))
                and (row.source_page is None or run[0].page_number == row.source_page)
                for run in runs
            )

        if not found:
            issues.append(SourceQuoteIssue(row.row_id, "source_quote_not_found"))
    return tuple(issues)


__all__ = [
    "CellIssue",
    "AuthorizedSourceFragment",
    "ExportIntegrityResult",
    "RequirementCell",
    "SourceQuoteIssue",
    "validate_generated_requirement_cells",
    "validate_source_quote_presence",
]
