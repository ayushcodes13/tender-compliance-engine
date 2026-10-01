"""Tests for CP29 deterministic candidate reconciliation (reconcile).

Pure-logic tests: no DB, no LLM.  Verifies dedup of verbatim/overlap
duplicates, flagging (not silent deletion) of identical text on distinct
pages, singleton handling, determinism, and the content-addressed group id.
"""

from __future__ import annotations

import uuid

from tender_compliance_api.extraction.reconcile import (
    DECISION_DEDUP,
    DECISION_FLAGGED,
    DECISION_SINGLETON,
    ReconciliationInput,
    reconcile,
)


def _cand(
    text: str,
    page_numbers: tuple[int, ...],
    candidate_id: uuid.UUID | None = None,
    chunk_id: str = "c1",
) -> ReconciliationInput:
    return ReconciliationInput(
        candidate_id=candidate_id or uuid.uuid4(),
        chunk_id=chunk_id,
        normalized_text=text,
        page_numbers=page_numbers,
        sources_json=[{"page_number": p} for p in page_numbers],
    )


# ---------------------------------------------------------------------------
# 1. Empty input -> no groups, nothing deduped.
# ---------------------------------------------------------------------------

def test_empty_input_is_noop() -> None:
    result = reconcile([])
    assert result.groups == []
    assert result.input_count == 0
    assert result.removed_count == 0
    assert result.kept_count == 0


# ---------------------------------------------------------------------------
# 2. Singleton: one candidate per text -> kept, not deduped.
# ---------------------------------------------------------------------------

def test_singleton_is_kept_and_singleton() -> None:
    c = _cand("The system shall encrypt data at rest.", (1,))
    result = reconcile([c])
    assert result.input_count == 1
    assert len(result.groups) == 1
    g = result.groups[0]
    assert g.decision == DECISION_SINGLETON
    assert g.kept == [c.candidate_id]
    assert g.removed == []


# ---------------------------------------------------------------------------
# 3. Overlap duplicate: identical text, same page -> dedup_exact, 1 removed.
# ---------------------------------------------------------------------------

def test_overlap_duplicate_is_deduped() -> None:
    a = _cand("The system shall encrypt data at rest.", (1,), chunk_id="c1")
    b = _cand("The system shall encrypt data at rest.", (1,), chunk_id="c2")
    result = reconcile([a, b])
    assert result.input_count == 2
    assert len(result.groups) == 1
    g = result.groups[0]
    assert g.decision == DECISION_DEDUP
    assert g.removed == [b.candidate_id]
    assert g.kept == [a.candidate_id]  # stable: first (chunk_id, id) order
    assert result.deduped_count == 1
    assert result.removed_count == 1


# ---------------------------------------------------------------------------
# 4. Identical text on distinct pages (header/footer bleed) -> flagged_review,
#    NOT silently deleted.
# ---------------------------------------------------------------------------

def test_identical_text_distinct_pages_is_flagged_not_deleted() -> None:
    a = _cand("CONFIDENTIAL - Tender Document", (1,), chunk_id="c1")
    b = _cand("CONFIDENTIAL - Tender Document", (2,), chunk_id="c2")
    c = _cand("CONFIDENTIAL - Tender Document", (3,), chunk_id="c3")
    result = reconcile([a, b, c])
    g = result.groups[0]
    assert g.decision == DECISION_FLAGGED
    assert g.removed == []  # nothing silently deleted
    assert set(g.kept) == {a.candidate_id, b.candidate_id, c.candidate_id}
    assert result.flagged_count == 1
    assert result.removed_count == 0


# ---------------------------------------------------------------------------
# 5. Two candidates share *one* of several pages (real overlap) -> dedup.
# ---------------------------------------------------------------------------

def test_partial_page_overlap_is_deduped() -> None:
    a = _cand("Req: 10 A rated cable.", (1, 2), chunk_id="c1")
    b = _cand("Req: 10 A rated cable.", (2, 3), chunk_id="c2")  # shares page 2
    result = reconcile([a, b])
    g = result.groups[0]
    assert g.decision == DECISION_DEDUP
    assert len(g.removed) == 1


# ---------------------------------------------------------------------------
# 6. Mixed document: one dedup group + a singleton + a flagged group.
# ---------------------------------------------------------------------------

def test_mixed_document_reconciliation() -> None:
    # dedup group: same obligation, same page (two windows overlapped)
    a = _cand("Shall operate below 30 dB(A).", (1,), chunk_id="c1")
    b = _cand("Shall operate below 30 dB(A).", (1,), chunk_id="c2")
    # singleton obligation
    c = _cand("Enclosure must be IP67 rated.", (2,), chunk_id="c3")
    # flagged group: identical header text on page 1 and 3
    d = _cand("Page header text", (1,), chunk_id="c4")
    e = _cand("Page header text", (3,), chunk_id="c5")

    result = reconcile([a, b, c, d, e])
    assert result.input_count == 5
    assert result.removed_count == 1  # b deduped
    assert result.flagged_count == 1
    assert result.singleton_count == 1
    decisions = {g.group_id: g for g in result.groups}
    assert len(decisions) == 3
    dedup = [g for g in result.groups if g.decision == DECISION_DEDUP][0]
    flagged = [g for g in result.groups if g.decision == DECISION_FLAGGED][0]
    singlet = [g for g in result.groups if g.decision == DECISION_SINGLETON][0]
    assert dedup.group_id == _expected_gid("Shall operate below 30 dB(A).")
    assert flagged.group_id == _expected_gid("Page header text")
    assert singlet.group_id == _expected_gid("Enclosure must be IP67 rated.")


# ---------------------------------------------------------------------------
# 7. Determinism: reordering inputs yields identical groups/decisions.
# ---------------------------------------------------------------------------

def test_reconcile_is_deterministic_regardless_of_input_order() -> None:
    a = _cand("X obligation", (1,), chunk_id="c1")
    b = _cand("X obligation", (1,), chunk_id="c2")
    c = _cand("Y obligation", (2,), chunk_id="c3")
    r1 = reconcile([a, b, c])
    r2 = reconcile([c, b, a])
    g1 = {g.group_id: (g.decision, tuple(g.kept), tuple(g.removed)) for g in r1.groups}
    g2 = {g.group_id: (g.decision, tuple(g.kept), tuple(g.removed)) for g in r2.groups}
    assert g1 == g2
    assert r1.summary() == r2.summary()


# ---------------------------------------------------------------------------
# 8. group_id is the content-addressed (sha256-truncated) normalized text.
# ---------------------------------------------------------------------------

def _expected_gid(text: str) -> str:
    import hashlib
    import re
    fp = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(fp.encode("utf-8")).hexdigest()[:16]


def test_group_id_is_content_addressed() -> None:
    c = _cand("The relay shall switch 10 A at 250 V.", (1,))
    result = reconcile([c])
    assert result.groups[0].group_id == _expected_gid(c.normalized_text)


# ---------------------------------------------------------------------------
# 9. Whitespace normalization buckets near-identical text together.
# ---------------------------------------------------------------------------

def test_whitespace_normalized_text_buckets_together() -> None:
    a = _cand("Line one.\n\n  Line two.", (1,), chunk_id="c1")
    b = _cand("Line one.   Line two.", (1,), chunk_id="c2")
    result = reconcile([a, b])
    assert len(result.groups) == 1
    g = result.groups[0]
    assert g.decision == DECISION_DEDUP


# ---------------------------------------------------------------------------
# 10. No source fragments -> cannot share a page -> flagged_review.
# ---------------------------------------------------------------------------

def test_candidate_without_source_fragments_is_flagged_when_duplicated() -> None:
    a = ReconciliationInput(
        candidate_id=uuid.uuid4(), chunk_id="c1",
        normalized_text="No source fragments here.", page_numbers=(),
        sources_json=None,
    )
    b = ReconciliationInput(
        candidate_id=uuid.uuid4(), chunk_id="c2",
        normalized_text="No source fragments here.", page_numbers=(),
        sources_json=None,
    )
    result = reconcile([a, b])
    g = result.groups[0]
    assert g.decision == DECISION_FLAGGED
    assert g.removed == []


# ---------------------------------------------------------------------------
# 11. distinct_text_distinct_pages: two different obligations same page ->
#     two singletons (no merge).
# ---------------------------------------------------------------------------

def test_distinct_requirements_same_page_are_both_kept() -> None:
    a = _cand("Shall encrypt data at rest.", (1,), chunk_id="c1")
    b = _cand("Shall weigh less than 2 kg.", (1,), chunk_id="c2")
    result = reconcile([a, b])
    assert result.input_count == 2
    assert len(result.groups) == 2
    assert all(g.decision == DECISION_SINGLETON for g in result.groups)
    assert result.removed_count == 0
