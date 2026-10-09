"""Tests for CP30 candidate -> Requirement promotion (pure logic).

No DB / LLM: verifies promotion_key determinism and EXACT/APPROXIMATE anchor
resolution from a candidate's trusted ``sources_json``.  The DB integration
(round-trip, idempotency, human-review preservation) lives in
``test_extraction_pipeline.py`` (TestPromotionPersistence).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from tender_compliance_api.extraction.requirement import (
    PromotionInput,
    promotion_key,
    resolve_sources,
    to_promotion_input,
)


def _row(
    *,
    normalized_text: str = "The system shall encrypt data at rest.",
    raw_source: str = "shall encrypt data at rest",
    requirement_type: str = "obligation",
    clause_number: str | None = None,
    ocr_warning: bool = False,
    sources_json=None,
    reconciliation_group_id: str | None = "grp1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        chunk_id="c1",
        normalized_text=normalized_text,
        raw_source=raw_source,
        requirement_type=requirement_type,
        uncertainty="confirmed",
        clause_number=clause_number,
        ocr_warning=ocr_warning,
        sources_json=sources_json,
        reconciliation_group_id=reconciliation_group_id,
    )


# ---------------------------------------------------------------------------
# 1. promotion_key is deterministic.
# ---------------------------------------------------------------------------

def test_promotion_key_is_deterministic() -> None:
    key1 = promotion_key("  Encrypt  data. ", "obligation", None, (1, 2))
    key2 = promotion_key("Encrypt data.", "obligation", None, (1, 2))
    assert key1 == key2  # whitespace-normalized before hashing


def test_promotion_key_changes_when_text_changes() -> None:
    a = promotion_key("Encrypt data at rest.", "obligation", None, (1,))
    b = promotion_key("Encrypt data in transit.", "obligation", None, (1,))
    assert a != b


def test_promotion_key_changes_when_pages_change() -> None:
    a = promotion_key("Same text.", "obligation", None, (1,))
    b = promotion_key("Same text.", "obligation", None, (2,))
    assert a != b


def test_promotion_key_changes_when_clause_or_type_changes() -> None:
    text = "Same obligation."
    by_clause = promotion_key(text, "obligation", "1.2", (1,))
    no_clause = promotion_key(text, "obligation", None, (1,))
    by_type = promotion_key(text, "prohibition", "1.2", (1,))
    assert by_clause != no_clause
    assert by_clause != by_type


def test_promotion_key_is_short_hex() -> None:
    key = promotion_key("x", "obligation", None, (1,))
    assert len(key) == 16
    int(key, 16)  # valid hex


# ---------------------------------------------------------------------------
# 2. to_promotion_input parses sources_json page numbers.
# ---------------------------------------------------------------------------

def test_to_promotion_input_extracts_pages() -> None:
    row = _row(
        sources_json=[
            {"page_number": 1, "clause_number": "1.1", "source_text": "aaa"},
            {"page_number": 3, "clause_number": "1.2", "source_text": "ccc"},
            {"page_number": 1, "clause_number": "1.1", "source_text": "aaa"},
        ]
    )
    inp = to_promotion_input(row)
    assert isinstance(inp, PromotionInput)
    assert inp.page_numbers == (1, 3, 1)  # order preserved from sources
    # promotion_key uses sorted-unique pages
    assert inp.promotion_key == promotion_key(
        inp.normalized_text, inp.requirement_type, inp.clause_number, (1, 3)
    )


def test_to_promotion_input_handles_missing_sources() -> None:
    row = _row(sources_json=None)
    inp = to_promotion_input(row)
    assert inp.page_numbers == ()
    assert inp.promotion_key == promotion_key(
        inp.normalized_text, inp.requirement_type, None, ()
    )


# ---------------------------------------------------------------------------
# 3. resolve_sources: EXACT when raw_source is a literal substring.
# ---------------------------------------------------------------------------

def test_exact_anchor_resolved_from_literal_substring() -> None:
    src_text = "The system shall encrypt data at rest using AES-256."
    raw = "shall encrypt data at rest"
    sources = [
        {"page_number": 1, "clause_number": "1.1", "source_text": src_text}
    ]
    resolved = resolve_sources(raw, sources)
    assert len(resolved) == 1
    r = resolved[0]
    assert r.location_type == "exact"
    assert r.page_number == 1
    assert r.clause_number == "1.1"
    expected = src_text.find(raw)
    assert r.char_start == expected
    assert r.char_end == expected + len(raw)
    assert r.source_text == src_text


def test_exact_anchor_with_bbox_and_ocr_confidence_passthrough() -> None:
    src_text = "Voltage shall not exceed 230 V."
    raw = "230 V"
    sources = [
        {
            "page_number": 2,
            "clause_number": "2.3",
            "source_text": src_text,
            "bbox": {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0},
            "ocr_confidence": 0.97,
            "char_start": 5,
            "char_end": 30,
        }
    ]
    resolved = resolve_sources(raw, sources)
    r = resolved[0]
    assert r.location_type == "exact"
    assert r.bbox == {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0}
    assert r.ocr_confidence == 0.97
    # exact_start overwrites the fragment's approximate char_start/char_end
    assert r.char_start == src_text.find(raw)


def test_whitespace_difference_falls_back_to_approximate() -> None:
    # raw_source uses a single space; source_text has a newline where the
    # model cited it — not a literal substring, so we MUST NOT fabricate offsets.
    src_text = "encrypt\ndata at rest"
    raw = "encrypt data at rest"
    assert src_text.find(raw) == -1  # not literal
    resolved = resolve_sources(
        raw, [{"page_number": 1, "source_text": src_text, "char_start": 0}]
    )
    assert resolved[0].location_type == "approximate"
    # no exact offsets fabricated
    assert resolved[0].char_start == 0  # falls back to fragment's stored span


def test_no_source_text_falls_back_to_approximate() -> None:
    resolved = resolve_sources(
        "raw", [{"page_number": 1, "source_text": None, "char_start": 7}]
    )
    assert resolved[0].location_type == "approximate"


def test_multiple_fragments_resolve_independently() -> None:
    text1 = "First page requirement text."
    text2 = "Second page requirement text."
    raw = "requirement text"
    resolved = resolve_sources(
        raw,
        [
            {"page_number": 1, "source_text": text1},
            {"page_number": 2, "source_text": text2},
        ],
    )
    assert len(resolved) == 2
    assert all(r.location_type == "exact" for r in resolved)
    assert resolved[0].char_start == text1.find(raw)
    assert resolved[1].char_start == text2.find(raw)


def test_multi_page_window_quote_resolves_to_page_local_fragments() -> None:
    page_one = "Prefix: Lead words"
    page_two = "continued text. Suffix"
    window = "Lead words\ncontinued text."
    raw = "Lead words\ncontinued text."
    sources = [
        {
            "page_number": 4,
            "source_text": window,
            "window_char_start": 0,
            "window_char_end": len("Lead words"),
            "page_source_text": page_one,
            "char_start": 8,
            "char_end": len(page_one),
        },
        {
            "page_number": 5,
            "source_text": window,
            "window_char_start": len("Lead words\n"),
            "window_char_end": len(window),
            "page_source_text": page_two,
            "char_start": 0,
            "char_end": len("continued text."),
        },
    ]

    resolved = resolve_sources(raw, sources)

    assert [source.page_number for source in resolved] == [4, 5]
    assert [source.source_text for source in resolved] == [
        "Lead words",
        "continued text.",
    ]
    assert [(source.char_start, source.char_end) for source in resolved] == [
        (8, len(page_one)),
        (0, len("continued text.")),
    ]
    assert all(source.location_type == "exact" for source in resolved)


def test_multi_page_quote_with_line_wrap_resolves_to_page_with_text() -> None:
    page_one = "Earlier requirement text."
    page_two = "The source shall be fully \nintegrated with the MBE control software."
    window = f"{page_one}\n{page_two}"
    raw = "The source shall be fully integrated with the MBE control software."
    page_two_start = len(page_one) + 1
    sources = [
        {
            "page_number": 9,
            "source_text": window,
            "window_char_start": 0,
            "window_char_end": len(page_one),
            "page_source_text": page_one,
            "page_source_char_start": 0,
            "char_start": 0,
            "char_end": len(page_one),
        },
        {
            "page_number": 10,
            "source_text": window,
            "window_char_start": page_two_start,
            "window_char_end": len(window),
            "page_source_text": page_two,
            "page_source_char_start": 0,
            "char_start": 0,
            "char_end": len(page_two),
        },
    ]

    resolved = resolve_sources(raw, sources)

    assert len(resolved) == 1
    assert resolved[0].page_number == 10
    assert resolved[0].location_type == "exact"
    assert resolved[0].source_text == page_two
    assert resolved[0].char_start == page_two.index("The source")
    assert resolved[0].char_end == len(page_two)


def test_multi_page_duplicate_quote_does_not_claim_exact_page() -> None:
    page_one = "Required text appears here."
    page_two = "Required text appears here too."
    window = f"{page_one}\n{page_two}"
    raw = "Required text"
    sources = [
        {
            "page_number": page_number,
            "source_text": window,
            "window_char_start": start,
            "window_char_end": end,
            "page_source_text": page_text,
            "char_start": 0,
            "char_end": len(page_text),
        }
        for page_number, page_text, start, end in (
            (1, page_one, 0, len(page_one)),
            (2, page_two, len(page_one) + 1, len(window)),
        )
    ]

    resolved = resolve_sources(raw, sources)

    assert [source.page_number for source in resolved] == [1, 2]
    assert all(source.location_type == "approximate" for source in resolved)


def test_multi_page_resolution_uses_trusted_page_span_for_repeated_quote() -> None:
    page_one = "Repeated header. Trusted clause starts here."
    page_two = "Repeated header. Continued clause ends here."
    window = "Trusted clause starts here.\nContinued clause ends here."
    raw = "Trusted clause starts here.\nContinued clause ends here."
    sources = [
        {
            "page_number": 4,
            "source_text": window,
            "window_char_start": 0,
            "window_char_end": len("Trusted clause starts here."),
            "page_source_text": page_one,
            "char_start": page_one.index("Trusted"),
            "char_end": len(page_one),
        },
        {
            "page_number": 5,
            "source_text": window,
            "window_char_start": len("Trusted clause starts here.\n"),
            "window_char_end": len(window),
            "page_source_text": page_two,
            "char_start": page_two.index("Continued"),
            "char_end": len(page_two),
        },
    ]

    resolved = resolve_sources(raw, sources)

    assert [(source.char_start, source.char_end) for source in resolved] == [
        (page_one.index("Trusted"), len(page_one)),
        (page_two.index("Continued"), len(page_two)),
    ]
    assert all(source.location_type == "exact" for source in resolved)


def test_fragment_without_page_number_is_skipped() -> None:
    resolved = resolve_sources(
        "raw",
        [{"source_text": "raw here"}, {"page_number": 1, "source_text": "raw here"}],
    )
    assert len(resolved) == 1
    assert resolved[0].page_number == 1
