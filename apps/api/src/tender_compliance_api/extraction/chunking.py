"""Source-window chunking for extraction (CP27).

Converts a version's parsed :class:`~tender_compliance_api.db.models.DocumentPage`
rows into bounded :class:`SourceWindow` fragments that the EXTRACT stage
(CP28) feeds to the LLM.  The chunker is **pure** (no I/O, no DB) and purely
deterministic so chunk IDs are stable across re-runs — a non-negotiable for
auditability: the same page text must always yield the same windows.

Boundaries (CP27.1):
  - **page** boundaries (trusted — ``DocumentPage.page_number``).
  - **clause/section** headers, detected with the same numbered-clause
    convention as :mod:`tender_compliance_api.parser.cleanup` so a "1.2.3
    Scope" line is never silently swallowed by a split.
  - **table** blocks (consecutive ``|``-delimited rows kept together, never
    split mid-table) with their header row preserved.

Overlap (CP27.2): each window after the first carries ``overlap`` — the bounded
tail of the previous window's text — so a requirement straddling two windows
still has cross-boundary context.  The overlap tail is recorded (not silently
merged) so CP29 can collapse it deterministically.

Provenance (CP27.3 / CP27.6): every window carries a stable ``chunk_id`` and a
per-page :class:`TrustedSourceContext` with exact char offsets within that
page's ``cleaned_text``.  A window may span several pages, in which case
``sources`` has one fragment per contributing page — so a multi-page
requirement is never detached from any of its locations.

Guardrail: structure is never flattened.  A clause header, a table, or a
paragraph is an atomic segment; windows break only *between* segments, so a
single oversized segment is allowed to exceed ``max_chars`` (no data loss).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction.schema import (
    LocationType,
    TrustedSourceContext,
)

#: Same numbered-clause convention as ``parser.cleanup`` (e.g. "1.2.3 Scope").
_CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s")

#: A line containing a table-cell delimiter.
_TABLE_RE = re.compile(r"\|")

#: A blank/whitespace-only line.
_BLANK_RE = re.compile(r"^\s*$")


@dataclass(frozen=True)
class _Segment:
    """One atomic structural unit within a page's cleaned text."""

    kind: str  # "clause" | "table" | "para"
    text: str
    page_number: int
    char_start: int
    char_end: int
    clause: str | None  # active clause at this segment (None if unnumbered)
    table_label: str | None  # first row of a table block (row/col header hint)


@dataclass(frozen=True)
class SourceWindow:
    """A bounded, source-anchored extraction window (CP27).

    Attributes:
        chunk_id: Stable, deterministic id content-addressed to the window's
            contributing pages, char span, clause, and content — so the same
            document version always produces the same windows.
        text: The window's own content text (headers/footers already stripped by
            CP23 cleanup).  Does **not** include ``overlap``.
        sources: One :class:`TrustedSourceContext` per contributing page
            (>=1), each with exact char offsets within that page.  A window that
            spans pages retains a fragment for every contributing page.
        overlap: The bounded tail of the previous window's text, supplied so a
            cross-boundary requirement keeps context.  ``None`` for the first
            window.
        hierarchy: Active clause/section path, deepest level last
            (e.g. ``("1", "1.2", "1.2.3")``).
        table_context: Header labels of any tables included in this window,
            preserving row/column header identity (CP27.5).
    """

    chunk_id: str
    text: str
    sources: tuple[TrustedSourceContext, ...]
    overlap: str | None = None
    hierarchy: tuple[str, ...] = ()
    table_context: tuple[str, ...] = ()


def _line_kind(line: str) -> str:
    """Classify a single line into ``clause`` / ``table`` / ``para`` / ``blank``."""

    if _BLANK_RE.match(line):
        return "blank"
    if _CLAUSE_RE.match(line):
        return "clause"
    if _TABLE_RE.search(line):
        return "table"
    return "para"


def _clause_number(line: str) -> str | None:
    """Extract the numeric clause label (e.g. ``1.2.3``) from a clause header."""

    match = _CLAUSE_RE.match(line)
    if not match:
        return None
    token = match.group(0).strip().rstrip(".")
    return token if token else None


def _hierarchy_for(clause: str) -> list[str]:
    """Expand a dotted clause label into its ancestor path.

    ``"1.2.3"`` -> ``["1", "1.2", "1.2.3"]``.
    """

    parts = [p for p in clause.split(".") if p]
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def _segment_page(page: DocumentPage) -> list[_Segment]:
    """Split a page's :attr:`cleaned_text` into atomic structural segments.

    Segments never cross a clause header or a table boundary, and a clause
    header is always its own segment.  ``char_start``/``char_end`` are exact
    offsets into the page's ``cleaned_text``.
    """

    text = page.cleaned_text or ""
    if not text:
        return []

    records: list[tuple[str, str, int, int]] = []  # (line, kind, start, end)
    pos = 0
    for line in text.splitlines(keepends=True):
        start = pos
        end = pos + len(line)
        stripped = line.rstrip("\n").rstrip("\r")
        records.append((stripped, _line_kind(stripped), start, end))
        pos = end

    segments: list[_Segment] = []
    active_clause: str | None = None

    cur_kind: str | None = None
    cur_lines: list[tuple[str, int, int]] = []
    cur_table_label: str | None = None

    def flush() -> None:
        if not cur_lines:
            return
        body = "\n".join(ln for ln, _, _ in cur_lines)
        segments.append(
            _Segment(
                kind=cur_kind or "para",
                text=body,
                page_number=page.page_number,
                char_start=cur_lines[0][1],
                char_end=cur_lines[-1][2],
                clause=active_clause,
                table_label=cur_table_label,
            )
        )

    for line, kind, start, end in records:
        if kind == "blank":
            flush()  # blank line breaks the current paragraph/table segment
            cur_kind = None
            cur_lines = []
            cur_table_label = None
            continue
        if kind == "clause":
            flush()
            active_clause = _clause_number(line)
            segments.append(
                _Segment(
                    kind="clause",
                    text=line,
                    page_number=page.page_number,
                    char_start=start,
                    char_end=end,
                    clause=active_clause,
                    table_label=None,
                )
            )
            cur_kind = None
            cur_lines = []
            cur_table_label = None
            continue

        if kind != cur_kind:
            flush()
            cur_kind = kind
            cur_lines = []
            cur_table_label = None
        if kind == "table" and cur_table_label is None:
            cur_table_label = line  # first row => header label
        cur_lines.append((line, start, end))

    flush()
    return segments


@dataclass
class _WindowAccumulator:
    """Mutable builder for the in-progress window."""

    parts: list[str] = field(default_factory=list)
    length: int = 0
    sources: dict[int, list[int]] = field(default_factory=dict)
    table_labels: list[str] = field(default_factory=list)
    hierarchy: tuple[str, ...] = ()
    active_clause: str | None = None

    def add(self, seg: _Segment) -> None:
        if self.parts:
            self.parts.append(seg.text)
            self.length += 1 + len(seg.text)
        else:
            self.parts.append(seg.text)
            self.length += len(seg.text)

        span = self.sources.setdefault(seg.page_number, [seg.char_start, seg.char_end])
        span[0] = min(span[0], seg.char_start)
        span[1] = max(span[1], seg.char_end)

        if seg.table_label and seg.table_label not in self.table_labels:
            self.table_labels.append(seg.table_label)

        if seg.clause and seg.clause != self.active_clause:
            self.active_clause = seg.clause
            self.hierarchy = tuple(_hierarchy_for(seg.clause))

    @property
    def empty(self) -> bool:
        return not self.parts

    def text(self) -> str:
        return "\n".join(self.parts)


def _build_contexts(
    page_sources: dict[int, list[int]],
    pages_by_number: dict[int, DocumentPage],
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    window_text: str,
    clause: str | None,
) -> tuple[TrustedSourceContext, ...]:
    """One exact, per-page :class:`TrustedSourceContext` per contributing page."""

    contexts: list[TrustedSourceContext] = []
    for page_number in sorted(pages_by_number):
        if page_number not in page_sources:
            continue
        page = pages_by_number[page_number]
        start, end = page_sources[page_number]
        contexts.append(
            TrustedSourceContext(
                organization_id=organization_id,
                document_id=document_id,
                document_version_id=page.document_version_id,
                page_number=page_number,
                clause_number=clause,
                char_start=start,
                char_end=end,
                # OCR confidence is a parser/OCR signal; carry it through.
                ocr_confidence=page.ocr_confidence,
                location_type=LocationType.EXACT,
                # Trusted window text the candidate citation is checked
                # against — the full multi-page window text, not a fragment.
                source_text=window_text,
            )
        )
    return tuple(contexts)


def _stable_chunk_id(
    version_id: uuid.UUID,
    segs: list[_Segment],
    window_text: str,
) -> str:
    """Content-addressed, deterministic chunk id (CP27.3)."""

    pages_spanned = tuple(sorted({seg.page_number for seg in segs}))
    first = segs[0]
    last = segs[-1]
    content_hash = hashlib.sha256(window_text.encode("utf-8")).hexdigest()[:12]
    key = (
        f"{version_id}:{pages_spanned}:"
        f"{first.page_number}:{first.char_start}:"
        f"{last.page_number}:{last.char_end}:{content_hash}"
    )
    return "cw-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _finalize_window(
    acc: _WindowAccumulator,
    segs: list[_Segment],
    prev_text: str | None,
    overlap_chars: int,
    pages_by_number: dict[int, DocumentPage],
    version_id: uuid.UUID,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> SourceWindow:
    """Materialize a :class:`SourceWindow` from the accumulator state."""

    text = acc.text()
    overlap = prev_text[-overlap_chars:] if (prev_text and overlap_chars) else None
    contexts = _build_contexts(
        acc.sources,
        pages_by_number,
        organization_id,
        document_id,
        text,
        segs[0].clause if segs else None,
    )
    chunk_id = _stable_chunk_id(version_id, segs, text)
    return SourceWindow(
        chunk_id=chunk_id,
        text=text,
        sources=contexts,
        overlap=overlap,
        hierarchy=acc.hierarchy,
        table_context=tuple(acc.table_labels),
    )


def build_source_windows(
    pages: list[DocumentPage],
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    max_chars: int = 1500,
    overlap_chars: int = 150,
) -> list[SourceWindow]:
    """Chunk parsed :class:`DocumentPage` rows into source-anchored windows.

    Args:
        pages: Document pages for a single version (any order; sorted here).
            The version id is taken from each page's ``document_version_id``.
        organization_id / document_id: Trusted provenance scope.
        max_chars: Per-window content size cap.  A single atomic segment larger
            than this is still emitted whole (never split) to avoid data loss.
        overlap_chars: Bounded tail of the previous window's text carried into
            the next window as ``overlap``.

    Returns:
        Windows in document order, with stable ``chunk_id``s.

    Raises:
        ValueError: If ``max_chars`` is not positive, or ``overlap_chars`` is
            negative / not less than ``max_chars``.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be < max_chars")

    ordered = sorted(pages, key=lambda p: p.page_number)
    pages_by_number: dict[int, DocumentPage] = {p.page_number: p for p in ordered}

    segments: list[_Segment] = []
    version_id: uuid.UUID | None = None
    for page in ordered:
        segments.extend(_segment_page(page))
        if version_id is None:
            version_id = page.document_version_id
    if version_id is None or not segments:
        # No pages with text — nothing to chunk.
        return []

    windows: list[SourceWindow] = []
    prev_text: str | None = None
    acc = _WindowAccumulator()
    cur_segments: list[_Segment] = []

    for seg in segments:
        # Flush before adding if the atomic segment would overflow and the
        # window is non-empty.  An oversized single segment still goes in whole.
        if not acc.empty and acc.length + 1 + len(seg.text) > max_chars:
            windows.append(
                _finalize_window(
                    acc, cur_segments, prev_text, overlap_chars,
                    pages_by_number, version_id, organization_id, document_id,
                )
            )
            prev_text = acc.text()
            acc = _WindowAccumulator()
            cur_segments = []
        acc.add(seg)
        cur_segments.append(seg)

    if not acc.empty:
        windows.append(
            _finalize_window(
                acc, cur_segments, prev_text, overlap_chars,
                pages_by_number, version_id, organization_id, document_id,
            )
        )

    return windows


__all__ = ["SourceWindow", "build_source_windows"]
