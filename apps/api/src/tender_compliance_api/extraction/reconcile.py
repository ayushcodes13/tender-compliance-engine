"""Deterministic candidate reconciliation (CP29).

Operates on the persisted :class:`ExtractionCandidate` rows that CP28 wrote
for a document version.  The goal: prevent repeated/overlapping source
windows from flooding the compliance matrix with duplicate rows, **without**
aggressively merging requirements that merely share wording.

Dedup signals (deterministic — no fuzzy/semantic similarity):

- **Verbatim / overlap duplicate.** Two candidates with *identical*
  whitespace-normalized ``normalized_text`` whose trusted source spans share
  at least one page are treated as the same requirement emitted twice (the
  classic overlap-duplicate: the chunker's bounded ``overlap`` tail lets a
  boundary-spanning obligation surface in two adjacent windows).  All but the
  first (in stable ``(chunk_id, candidate_id)`` order) are suppressed
  (``deduped=True``) — kept for audit but not promotable to a requirement.

- **Identical text, distinct pages.** Same normalized text but *disjoint*
  page spans (e.g. a document header/footer re-emitted as a "requirement" on
  several pages).  Per the AGENTS guardrail this is **not** proof the rows are
  one requirement, so nothing is silently deleted: every member is kept and
  flagged for human review (``flagged_review``), sharing a stable
  ``reconciliation_group_id`` so CP30/CP35 can review them together.

- **Singleton.** One candidate for a given text → ``singleton``.

The function is pure (no DB/IO) so the deduplication logic is unit-testable
in isolation; persistence of the decisions is the caller's concern
(:meth:`DocumentService.reconcile_version_candidates`).

Phase 1 only: this records *deduplication* decisions, not vendor-compliance
statuses or evidence.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# ``similar`` here means *character-identical after whitespace normalization*.
# We never use fuzzy/semantic similarity for dedup (AGENTS guardrail:
# "similar wording alone is not proof two requirements are the same").
_WS_RE = re.compile(r"\s+")

#: Stable, deterministic group id length (truncated sha256 of the normalized
#: fingerprint).  Deterministic so re-running reconciliation on the same
#: candidates yields the same ids.
_GROUP_ID_LEN = 16

#: Reconciliation decisions.  Stored on ExtractionCandidate rows.
DECISION_DEDUP = "dedup_exact"
DECISION_FLAGGED = "flagged_review"
DECISION_SINGLETON = "singleton"


def _normalize_ws(text: str) -> str:
    """Collapse whitespace to single spaces and strip — the dedup fingerprint."""

    return _WS_RE.sub(" ", text).strip()


def _group_id(fingerprint: str) -> str:
    """Stable, content-addressed group id from the whitespace-normalized text."""

    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:_GROUP_ID_LEN]


def _page_set(candidates_page_numbers: tuple[int, ...]) -> frozenset[int]:
    return frozenset(candidates_page_numbers)


def _any_pair_shares_page(page_sets: list[frozenset[int]]) -> bool:
    """True when any two candidates' source spans share at least one page."""

    for i in range(len(page_sets)):
        for j in range(i + 1, len(page_sets)):
            if page_sets[i] & page_sets[j]:
                return True
    return False


@dataclass(frozen=True)
class ReconciliationInput:
    """A persisted candidate's reconciliation surface (DB-agnostic).

    Built by the service from ``ExtractionCandidate`` rows; constructed directly
    in unit tests.
    """

    candidate_id: uuid.UUID
    chunk_id: str
    normalized_text: str
    page_numbers: tuple[int, ...]
    sources_json: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ReconciliationGroup:
    """One fingerprint bucket and the action taken on it."""

    group_id: str
    decision: str
    kept: list[uuid.UUID]  # candidate ids retained (promotable in CP30)
    removed: list[uuid.UUID]  # candidate ids suppressed (deduped, audit-only)
    reason: str | None
    page_sets: tuple[frozenset[int], ...]
    member_chunks: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationResult:
    """Aggregate outcome of reconciling one version's candidates."""

    groups: list[ReconciliationGroup]
    input_count: int
    deduped_count: int
    flagged_count: int
    singleton_count: int

    @property
    def removed_count(self) -> int:
        return sum(len(g.removed) for g in self.groups)

    @property
    def kept_count(self) -> int:
        return sum(len(g.kept) for g in self.groups)

    def summary(self) -> dict[str, Any]:
        return {
            "input": self.input_count,
            "groups": len(self.groups),
            "deduped": self.deduped_count,
            "flagged": self.flagged_count,
            "singleton": self.singleton_count,
            "total_kept": self.kept_count,
            "total_removed": self.removed_count,
        }


@dataclass
class _Bucket:
    """Mutable accumulator for a single fingerprint during a reconcile pass."""

    fingerprint: str
    members: list[ReconciliationInput] = field(default_factory=list)


def reconcile(candidates: list[ReconciliationInput]) -> ReconciliationResult:
    """Deterministically cluster candidates and flag duplicates.

    Candidates are ordered by ``(chunk_id, candidate_id)`` before bucketing, so
    the choice of "first" (canonical) within a dedup group is stable and
    reproducible across runs (important for auditability).  No I/IO.

    Args:
        candidates: The version's persistable, source-validated candidates
            (CP29 does not touch ``persistable=False``/``is_valid=False``
            rows — those are audit-only).

    Returns:
        One :class:`ReconciliationGroup` per distinct normalized text, with
        ``kept``/``removed`` candidate ids and a ``decision``.
    """

    # Stable total order -> deterministic canonical choice + group order.
    ordered = sorted(
        candidates, key=lambda c: (c.chunk_id, str(c.candidate_id))
    )

    buckets: dict[str, _Bucket] = {}
    fingerprint_order: list[str] = []
    for cand in ordered:
        fp = _normalize_ws(cand.normalized_text)
        if fp not in buckets:
            buckets[fp] = _Bucket(fingerprint=fp)
            fingerprint_order.append(fp)
        buckets[fp].members.append(cand)

    groups: list[ReconciliationGroup] = []
    for fp in fingerprint_order:
        members = buckets[fp].members
        if len(members) == 1:
            m = members[0]
            groups.append(
                ReconciliationGroup(
                    group_id=_group_id(fp),
                    decision=DECISION_SINGLETON,
                    kept=[m.candidate_id],
                    removed=[],
                    reason=None,
                    page_sets=(_page_set(m.page_numbers),),
                    member_chunks=(m.chunk_id,),
                )
            )
            continue

        page_sets = [_page_set(m.page_numbers) for m in members]
        # Overlap duplicate: identical text, source spans share a page.
        if _any_pair_shares_page(page_sets):
            kept = [members[0].candidate_id]
            removed = [m.candidate_id for m in members[1:]]
            groups.append(
                ReconciliationGroup(
                    group_id=_group_id(fp),
                    decision=DECISION_DEDUP,
                    kept=kept,
                    removed=removed,
                    reason=(
                        "verbatim duplicate with overlapping source span "
                        "(same requirement emitted across adjacent windows)"
                    ),
                    page_sets=tuple(page_sets),
                    member_chunks=tuple(m.chunk_id for m in members),
                )
            )
        else:
            # Identical text on disjoint pages — flag for review, keep all
            # (AGENTS: "prefer a possible duplicate for review over silently
            # deleting a distinct requirement").
            kept = [m.candidate_id for m in members]
            groups.append(
                ReconciliationGroup(
                    group_id=_group_id(fp),
                    decision=DECISION_FLAGGED,
                    kept=kept,
                    removed=[],
                    reason=(
                        "identical normalized text on distinct pages; "
                        "requires human review (not silently merged)"
                    ),
                    page_sets=tuple(page_sets),
                    member_chunks=tuple(m.chunk_id for m in members),
                )
            )

    input_count = len(ordered)
    deduped_count = sum(1 for g in groups if g.decision == DECISION_DEDUP)
    flagged_count = sum(1 for g in groups if g.decision == DECISION_FLAGGED)
    singleton_count = sum(1 for g in groups if g.decision == DECISION_SINGLETON)

    return ReconciliationResult(
        groups=groups,
        input_count=input_count,
        deduped_count=deduped_count,
        flagged_count=flagged_count,
        singleton_count=singleton_count,
    )


__all__ = [
    "DECISION_DEDUP",
    "DECISION_FLAGGED",
    "DECISION_SINGLETON",
    "ReconciliationGroup",
    "ReconciliationInput",
    "ReconciliationResult",
    "reconcile",
]
