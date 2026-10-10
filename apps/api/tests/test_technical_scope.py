"""The tender extractor is bounded to an explicitly titled technical section."""

from __future__ import annotations

import uuid

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction.chunking import build_source_windows
from tender_compliance_api.extraction.technical_scope import (
    select_technical_specification_ranges,
)

_ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DOC = uuid.UUID("00000000-0000-0000-0000-000000000002")
_VERSION = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _page(number: int, text: str) -> DocumentPage:
    return DocumentPage(
        document_version_id=_VERSION,
        page_number=number,
        extracted_text=text,
        cleaned_text=text,
        ocr_needed=0,
    )


def _window_text(pages: list[DocumentPage]) -> str:
    scope = select_technical_specification_ranges(pages)
    windows = build_source_windows(
        pages,
        organization_id=_ORG,
        document_id=_DOC,
        included_ranges_by_page=scope.ranges_by_page,
    )
    return "\n".join(window.text for window in windows)


def test_toc_and_other_tender_sections_are_excluded_but_full_spec_section_is_kept() -> None:
    page = _page(
        1,
        "Section 4 Specifications Technical specifications Pg. 10\n"
        "Section 2 Eligibility Criteria Pg. 3\n"
        "Section 3 - Terms and Conditions\n"
        "The bidder shall submit audited financial statements.\n\n"
        "Section 4 - Technical specifications\n"
        "Technical requirements of the Diamond Scriber for III-V\n"
        "Parameter | Required Specification\n"
        "Wafer Chuck (1 number)\n"
        "Vacuum-backed chuck should handle samples from 10 mm to 4 inches.\n"
        "Other requirements\n"
        "Training for users by company personnel immediately after installation.\n"
        "Section 5 - Technical Bid\n"
        "The bidder must provide company registration details.\n",
    )

    selected = _window_text([page])

    assert "Section 4 - Technical specifications" in selected
    assert "Wafer Chuck (1 number)" in selected
    assert "Vacuum-backed chuck should handle samples from 10 mm to 4 inches." in selected
    # The examples retain these rows when they appear inside the technical section.
    assert "Training for users by company personnel immediately after installation." in selected
    assert "audited financial statements" not in selected
    assert "company registration details" not in selected
    assert "Pg. 10" not in selected


def test_existing_compliance_sheet_is_preferred_over_repeated_spec_narrative() -> None:
    pages = [
        _page(
            1,
            "TECHNICAL SPECIFICATION:\n"
            "Narrative copy of the MBE specification.\n"
            "Commercial terms\n"
            "Payment is due within 30 days.\n",
        ),
        _page(
            2,
            "ANNEXURE-I\n"
            "COMPLIANCE SHEET\n"
            "TECHNICAL SPECIFICATION\n"
            "Technical Parameters | Remark | Compliance Y/N\n"
            "12. Growth chamber\n"
            "Base pressure better than <2x10-10 Torr.\n"
            "Other important requirements\n"
            "Vendor shall provide the stated operating documentation.\n"
            "ANNEXURE-II\n"
            "Declaration sheet\n",
        ),
    ]

    selected = _window_text(pages)

    assert "COMPLIANCE SHEET" in selected
    assert "12. Growth chamber" in selected
    assert "<2x10-10 Torr" in selected
    assert "Other important requirements" in selected
    assert "Narrative copy" not in selected
    assert "Payment is due" not in selected
    assert "Declaration sheet" not in selected


def test_part_boundary_and_notes_after_the_technical_matrix_are_excluded() -> None:
    pages = [
        _page(
            1,
            "SECTION V\n"
            "Technical Specification\n"
            "PART - II\n"
            "S.no | Technical Specification | Qty\n"
            "1 Universal Testing Machine (300 kN)\n"
            "Force sampling rate: 1000/s\n"
            "Additional Technical Specifications\n"
            "Minimum 5,000 cycles.\n"
            "Terms & Conditions:\n"
            "Online demonstration is required.\n"
            "Note:\n"
            "Bidder should submit acceptance against every column.\n"
            "PART - III\n"
            "Unpriced Technical Bid\n",
        )
    ]

    selected = _window_text(pages)

    assert "PART - II" in selected
    assert "Force sampling rate: 1000/s" in selected
    assert "Minimum 5,000 cycles." in selected
    assert "Online demonstration is required." in selected
    assert "Bidder should submit acceptance" not in selected
    assert "Unpriced Technical Bid" not in selected


def test_no_explicit_technical_section_returns_no_ranges() -> None:
    pages = [_page(1, "The bidder shall submit a datasheet with the offer.")]

    scope = select_technical_specification_ranges(pages)

    assert scope.found is False
    assert scope.ranges_by_page == {}
    assert _window_text(pages) == ""


def test_selected_windows_keep_original_page_offsets_and_never_bridge_excluded_text() -> None:
    page = _page(
        4,
        "Eligibility Criteria\n"
        "Minimum turnover of 1 crore.\n"
        "TECHNICAL SPECIFICATION:\n"
        "Range: 10-20 mm.\n"
        "Section 5 - General Terms\n"
        "Bidder must provide a declaration.\n",
    )
    scope = select_technical_specification_ranges([page])
    windows = build_source_windows(
        [page],
        organization_id=_ORG,
        document_id=_DOC,
        included_ranges_by_page=scope.ranges_by_page,
    )

    assert len(windows) == 1
    window = windows[0]
    assert "Minimum turnover" not in window.text
    assert "Range: 10-20 mm." in window.text
    assert "Bidder must provide a declaration" not in window.text
    source = window.sources[0]
    assert source.source_text == window.text
    assert page.cleaned_text[source.char_start : source.char_end].strip() == window.text.strip()
