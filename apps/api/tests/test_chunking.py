"""Tests for CP27: source-window chunking.

Covers:
- Single window when text fits; no spurious overflow.
- ``max_chars`` splits text and carries bounded overlap from the previous
  window's tail.
- Tables stay atomic (never split mid-table) and their header is recorded.
- Nested clause headers build a preserved hierarchy path.
- A requirement spanning multiple pages retains a source fragment for every
  contributing page (never detached from a location).
- chunk IDs are stable/deterministic across rebuilds.
- No data loss: an atomic segment larger than ``max_chars`` is emitted whole.
- No fabrication: source pages are real inputs (no synthetic page numbers /
  version ids), per the AGENTS "never fabricate" rule.
"""

from __future__ import annotations

import uuid

import pytest

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction.chunking import (
    SourceWindow,
    build_source_windows,
)
from tender_compliance_api.extraction.schema import (
    LocationType,
    TrustedSourceContext,
)

_ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DOC = uuid.UUID("00000000-0000-0000-0000-000000000002")
_VERSION = uuid.UUID("00000000-0000-0000-0000-000000000003")


def _page(n: int, text: str) -> DocumentPage:
    return DocumentPage(
        document_version_id=_VERSION,
        page_number=n,
        extracted_text=text if text else None,
        cleaned_text=text if text else None,
        ocr_needed=0,
        ocr_confidence=None,
    )


# ---------------------------------------------------------------------------
# Basic windowing
# ---------------------------------------------------------------------------


class TestBasicWindowing:
    def test_single_window_when_text_fits(self) -> None:
        text = "The handrail shall be painted RAL 9005 matte."
        windows = build_source_windows(
            [_page(1, text)], organization_id=_ORG, document_id=_DOC
        )
        assert len(windows) == 1
        w = windows[0]
        assert isinstance(w, SourceWindow)
        assert w.chunk_id.startswith("cw-")
        assert w.text == text
        assert w.overlap is None  # first window
        assert w.hierarchy == ()
        assert w.table_context == ()

        # Single source fragment anchored to the real page with exact offsets.
        assert len(w.sources) == 1
        src = w.sources[0]
        assert src.page_number == 1
        assert src.location_type is LocationType.EXACT
        assert src.document_version_id == _VERSION
        assert src.organization_id == _ORG
        assert src.document_id == _DOC
        assert src.char_start == 0
        assert src.char_end == len(text)
        assert src.source_text == text  # trusted window == window content

    def test_empty_pages_return_empty(self) -> None:
        assert build_source_windows([], organization_id=_ORG, document_id=_DOC) == []
        assert (
            build_source_windows([_page(1, "")], organization_id=_ORG, document_id=_DOC)
            == []
        )
        assert (
            build_source_windows([_page(1, None)], organization_id=_ORG, document_id=_DOC)  # type: ignore[arg-type]
            == []
        )

    def test_invalid_args_raise(self) -> None:
        pages = [_page(1, "x")]
        with pytest.raises(ValueError, match="max_chars must be positive"):
            build_source_windows(
                pages, organization_id=_ORG, document_id=_DOC, max_chars=0
            )
        with pytest.raises(ValueError, match="overlap_chars must be non-negative"):
            build_source_windows(
                pages, organization_id=_ORG, document_id=_DOC, overlap_chars=-1
            )
        with pytest.raises(ValueError, match="overlap_chars must be < max_chars"):
            build_source_windows(
                pages, organization_id=_ORG, document_id=_DOC,
                max_chars=10, overlap_chars=10,
            )


# ---------------------------------------------------------------------------
# Bounded overlap across windows
# ---------------------------------------------------------------------------


def _four_paragraphs() -> list[DocumentPage]:
    # Each ~30 chars, blank-line separated so each is its own segment; four
    # paragraphs force a split at max_chars=70.
    return [
        _page(
            1,
            "The handrail shall be painted RAL 9005.\n\n"
            "Surface preparation is mandatory.\n\n"
            "No substitutions are allowed.\n\n"
            "Finishing must occur on site.",
        )
    ]


class TestBoundedOverlap:
    def test_splits_with_bounded_overlap(self) -> None:
        pages = _four_paragraphs()
        windows = build_source_windows(
            pages, organization_id=_ORG, document_id=_DOC,
            max_chars=70, overlap_chars=5,
        )
        assert len(windows) >= 2

        # Every window respects the cap (no atomic segment exceeds it here).
        assert all(len(w.text) <= 70 for w in windows)

        # The second window's overlap is the previous window's bounded tail.
        second = windows[1]
        assert second.overlap is not None
        assert second.overlap == windows[0].text[-5:]
        assert len(second.overlap) == 5

        # The overlap is bounded — never the whole previous window.
        assert len(second.overlap) < len(windows[0].text)


# ---------------------------------------------------------------------------
# Atomic structure: tables + clause hierarchy
# ---------------------------------------------------------------------------


class TestAtomicStructure:
    def test_tables_never_split(self) -> None:
        text = (
            "1.2 Scope\n"
            "This section covers painting.\n\n"
            "Param | Value\n"
            "Color | RAL 9005\n"
            "Finish | Matt\n"
            "Mounting | Wall"
        )
        pages = [_page(1, text)]
        # Force splits around the table without breaking it.
        windows = build_source_windows(
            pages, organization_id=_ORG, document_id=_DOC,
            max_chars=25, overlap_chars=5,
        )
        table_window = [w for w in windows if "Param | Value" in w.text]
        assert len(table_window) == 1
        w = table_window[0]
        # All table rows survive together in one window (no mid-table split).
        assert "Color | RAL 9005" in w.text
        assert "Mounting | Wall" in w.text
        assert "Finish | Matt" in w.text
        assert w.table_context == ("Param | Value",)

    def test_nested_clauses_build_hierarchy(self) -> None:
        text = (
            "1 General\n"
            "General provisions apply.\n\n"
            "1.2 Scope\n"
            "Only section 1.2 applies.\n\n"
            "1.2.3 Sub-scope\n"
            "This is the deepest clause here."
        )
        pages = [_page(1, text)]
        windows = build_source_windows(
            pages, organization_id=_ORG, document_id=_DOC,
            max_chars=4000, overlap_chars=50,
        )
        # Single window captures the deepest active clause path.
        w = windows[0]
        assert w.hierarchy == ("1", "1.2", "1.2.3")

    def test_hierarchy_tracks_per_window(self) -> None:
        text = (
            "1 General\n"
            "General body.\n\n"
            "1.2 Scope\n"
            "Scope body.\n\n"
            "1.2.3 Deep\n"
            "Deep body."
        )
        # Tight cap forces 1.2 out of the first window.
        windows = build_source_windows(
            pages=[_page(1, text)], organization_id=_ORG, document_id=_DOC,
            max_chars=35, overlap_chars=5,
        )
        assert len(windows) >= 2
        # First window's deepest active clause is "1" or "1.2" (never "1.2.3").
        assert windows[0].hierarchy[-1] in ("1", "1.2")
        assert windows[0].hierarchy[-1] != "1.2.3"
        # The latest window must include the deepest clause reached.
        deepest = max(w.hierarchy[-1] for w in windows if w.hierarchy)
        assert deepest == "1.2.3"


# ---------------------------------------------------------------------------
# Multi-page windows + provenance integrity
# ---------------------------------------------------------------------------


class TestMultiPageWindows:
    def test_spanning_windows_retain_every_page(self) -> None:
        pages = [
            _page(1, "1 Scope\nThe handrail shall be painted RAL 9005."),
            _page(2, "Continued: the paint must be matte and durable."),
        ]
        windows = build_source_windows(
            pages, organization_id=_ORG, document_id=_DOC,
            max_chars=4000, overlap_chars=5,
        )
        w = windows[0]
        # Both contributing pages have a source fragment — the requirement is
        # never detached from either page.
        page_numbers = [s.page_number for s in w.sources]
        assert page_numbers == [1, 2]
        assert len(w.sources) == 2
        # Exact offsets are scoped to each page's own cleaned text.
        p1, p2 = w.sources
        assert p1.document_version_id == _VERSION
        assert p2.document_version_id == _VERSION
        assert p1.char_end <= len(pages[0].cleaned_text or "")
        assert p2.char_end <= len(pages[1].cleaned_text or "")
        assert p1.window_char_start == 0
        assert p1.window_char_end == len("1 Scope\nThe handrail shall be painted RAL 9005.")
        assert p2.window_char_start == p1.window_char_end + 1
        assert p2.window_char_end == len(w.text)
        assert p1.page_source_text == (pages[0].cleaned_text or "")[p1.char_start:p1.char_end]
        assert p2.page_source_text == (pages[1].cleaned_text or "")[p2.char_start:p2.char_end]
        assert p1.page_source_char_start == p1.char_start
        assert p2.page_source_char_start == p2.char_start
        # Both fragments reference the shared trusted window text.
        for src in w.sources:
            assert src.source_text == w.text
            assert src.location_type is LocationType.EXACT

    def test_stable_chunk_ids_across_rebuild(self) -> None:
        pages = [
            _page(1, "1 Scope\nBody one.\n\n1.2 Detail\nDetail body."),
            _page(2, "More detail continuing here.\nEven more content."),
        ]
        first = build_source_windows(pages, organization_id=_ORG, document_id=_DOC)
        second = build_source_windows(pages, organization_id=_ORG, document_id=_DOC)
        assert [w.chunk_id for w in first] == [w.chunk_id for w in second]
        assert [w.text for w in first] == [w.text for w in second]
        # Distinct windows get distinct ids.
        assert len({w.chunk_id for w in first}) == len(first)


# ---------------------------------------------------------------------------
# No-fabrication / no-data-loss
# ---------------------------------------------------------------------------


class TestNoFabrication:
    def test_sources_are_real_pages_only(self) -> None:
        pages = [_page(1, "A requirement here."), _page(5, "Another requirement.")]
        windows = build_source_windows(pages, organization_id=_ORG, document_id=_DOC)
        seen = {s.page_number for w in windows for s in w.sources}
        # No synthetic page numbers appear — only {1, 5}.
        assert seen == {1, 5}
        # Version id is taken from the page, never a constant.
        for w in windows:
            for s in w.sources:
                assert s.document_version_id == _VERSION

    def test_atomic_segment_may_exceed_max_chars(self) -> None:
        # A single huge paragraph must not be split (no data loss).
        big = "x" * 300
        windows = build_source_windows(
            [_page(1, big)], organization_id=_ORG, document_id=_DOC,
            max_chars=50, overlap_chars=5,
        )
        assert len(windows) == 1
        # The oversized atomic segment is emitted whole.
        assert "x" * 300 in windows[0].text
        assert len(windows[0].text) > 50


# ---------------------------------------------------------------------------
# Mixed: tables + multi-clause + overlap in one document
# ---------------------------------------------------------------------------


class TestMixedDocument:
    def test_clause_table_and_overlap_together(self) -> None:
        text = (
            "1 General\n"
            "General provisions.\n"
            "1.1 Sub\n"
            "Sub provisions.\n\n"
            "| Header | Value |\n"
            "| A | 1 |\n"
            "| B | 2 |\n"
        )
        pages = [_page(1, text), _page(2, "2 Other\nOther body text here.")]
        windows = build_source_windows(
            pages, organization_id=_ORG, document_id=_DOC,
            max_chars=40, overlap_chars=5,
        )
        assert len(windows) >= 2
        # Table stays atomic within the window that contains it.
        table_window = [w for w in windows if "Header | Value" in w.text]
        assert len(table_window) == 1
        assert "| B | 2 |" in table_window[0].text
        # Overlap is bounded and chained.
        for w in windows[1:]:
            assert w.overlap is not None
            assert len(w.overlap) == 5


class TestTrustedSourceContextType:
    def test_trusted_source_context_is_required_type(self) -> None:
        pages = [_page(1, "Body text only.")]
        windows = build_source_windows(pages, organization_id=_ORG, document_id=_DOC)
        assert isinstance(windows[0].sources[0], TrustedSourceContext)
