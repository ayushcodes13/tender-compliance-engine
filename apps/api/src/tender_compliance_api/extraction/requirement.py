"""Candidate -> Requirement promotion logic (CP30).

Pure functions that decide *whether* a reconciled candidate is promotable to a
:class:`~tender_compliance_api.db.models.Requirement` and resolve the strongest
**EXACT/APPROXIMATE** source anchor actually known — without fabricating
offsets, pages, or clauses.

Phase 1 domain semantics (per AGENTS.md): only candidates that survived CP25
source validation *and* CP29 reconciliation (``is_valid`` / ``persistable`` /
``deduped=False``) are promotable. Ordinary UNCERTAIN/ABSTAIN candidates are
not promoted. A strict verbatim-fallback recovery is the narrow exception: it
supplies an exact quote from the same source window and is promoted only into a
human-review state (``NEEDS_CLARIFICATION`` or ``OCR_WARNING``), never as an
approved result.

Anchor resolution is deterministic and never upgrades precision on a fuzzy
match (Bynd reuse note #4): ``EXACT`` is recorded only when the candidate's
``raw_source`` is a literal substring of the trusted page ``source_text``;
otherwise the anchor is ``APPROXIMATE`` (page/clause only).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from tender_compliance_api.extraction.schema import LocationType

_WS = re.compile(r"\s+")


def _normalize_ws(text: str | None) -> str:
    """Collapse whitespace and strip — used for fingerprints and substring checks."""

    if not text:
        return ""
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class ResolvedSource:
    """A single resolved source anchor for a Requirement (CP30)."""

    page_number: int
    clause_number: str | None
    char_start: int | None
    char_end: int | None
    bbox: dict[str, Any] | None
    ocr_confidence: float | None
    location_type: str  # "exact" | "approximate"
    source_text: str | None


@dataclass(frozen=True)
class PromotionInput:
    """A candidate reduced to exactly what CP30 needs to build a Requirement."""

    candidate_id: uuid.UUID
    chunk_id: str
    normalized_text: str
    raw_source: str
    requirement_type: str
    uncertainty: str
    clause_number: str | None
    ocr_warning: bool
    reconciliation_group_id: str | None
    sources_json: list[dict[str, Any]] | None
    page_numbers: tuple[int, ...]
    promotion_key: str


def promotion_key(
    normalized_text: str,
    requirement_type: str,
    clause_number: str | None,
    page_numbers: tuple[int, ...],
) -> str:
    """Stable, content-addressed identity for an obligation (CP30.9).

    Combines whitespace-normalized text + type + clause + contributing pages so
    that reprocessing an unchanged version yields the same key (→ no duplicate
    :class:`Requirement` rows) while genuinely-changed obligations get a new
    key (→ fresh row).
    """

    pages = ",".join(str(p) for p in sorted(set(page_numbers)))
    fp = _normalize_ws(normalized_text)
    raw = f"{fp}|{requirement_type}|{clause_number or ''}|{pages}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _iter_sources(sources_json: Any) -> list[dict[str, Any]]:
    """Normalize the stored sources_json into a list of fragment dicts."""

    if isinstance(sources_json, dict):
        return [sources_json]
    if isinstance(sources_json, list):
        return [s for s in sources_json if isinstance(s, dict)]
    return []


def to_promotion_input(row: Any) -> PromotionInput:
    """Project a persisted :class:`ExtractionCandidate` into a promotion input.

    Uses the trusted ``sources_json`` (no fabrication): page numbers are read
    from the source fragments the chunker recorded.
    """

    sources = _iter_sources(row.sources_json)
    page_numbers = tuple(
        s["page_number"]
        for s in sources
        if s.get("page_number") is not None
    )
    return PromotionInput(
        candidate_id=row.id,
        chunk_id=row.chunk_id,
        normalized_text=row.normalized_text,
        raw_source=row.raw_source,
        requirement_type=row.requirement_type,
        uncertainty=row.uncertainty,
        clause_number=row.clause_number,
        ocr_warning=bool(row.ocr_warning),
        reconciliation_group_id=row.reconciliation_group_id,
        sources_json=sources or None,
        page_numbers=page_numbers,
        promotion_key=promotion_key(
            row.normalized_text,
            row.requirement_type,
            row.clause_number,
            page_numbers,
        ),
    )


def resolve_sources(
    raw_source: str,
    sources_json: list[dict[str, Any]] | None,
    *,
    allow_exact: bool = True,
) -> list[ResolvedSource]:
    """Resolve the strongest known anchor per contributing source fragment.

    ``EXACT`` only when ``raw_source`` is a *literal* substring of the trusted
    page ``source_text`` (deterministic offset, no fuzzy mapping).  Otherwise
    ``APPROXIMATE`` (page/clause only) — precision is never upgraded on a
    plausible-but-non-literal match. ``allow_exact=False`` is used when an LLM
    selected a literal quote but did not establish its precise offsets.
    """

    resolved: list[ResolvedSource] = []
    norm_raw = _normalize_ws(raw_source)
    for frag in _iter_sources(sources_json):
        page = frag.get("page_number")
        if page is None:
            continue
        src_text = frag.get("source_text")
        char_start = frag.get("char_start")
        char_end = frag.get("char_end")

        exact_start: int | None = None
        if allow_exact and src_text is not None and raw_source:
            idx = src_text.find(raw_source)
            if idx == -1 and norm_raw:
                # Whitespace differs (e.g. model cited reformatted text) — we
                # cannot safely map back to original offsets, so stay
                # APPROXIMATE rather than fabricating a position.
                idx = None
            if idx is not None:
                exact_start = idx

        if exact_start is not None:
            location = LocationType.EXACT
            resolved_start: int | None = exact_start
            resolved_end: int | None = exact_start + len(raw_source)
        else:
            location = LocationType.APPROXIMATE
            resolved_start = char_start  # may be None — approximate is fine
            resolved_end = char_end

        resolved.append(
            ResolvedSource(
                page_number=page,
                clause_number=frag.get("clause_number"),
                char_start=resolved_start,
                char_end=resolved_end,
                bbox=frag.get("bbox"),
                ocr_confidence=frag.get("ocr_confidence"),
                location_type=location.value,
                source_text=src_text,
            )
        )
    return resolved


__all__ = [
    "PromotionInput",
    "ResolvedSource",
    "promotion_key",
    "resolve_sources",
    "to_promotion_input",
]
