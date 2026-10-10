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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from tender_compliance_api.db.models import DocumentPage
from tender_compliance_api.extraction.schema import (
    LocationType,
    TrustedSourceContext,
)
from tender_compliance_api.extraction.technical_scope import SourceTextRange

#: Same numbered-clause convention as ``parser.cleanup`` (e.g. "1.2.3 Scope").
_CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s")
_LETTERED_ROW_RE = re.compile(r"^\s*[a-z]\)\s+\S", re.I)
_LETTERED_ROW_START_RE = re.compile(r"(?m)^[ \t]*[a-z]\)[ \t]+\S", re.I)
_NUMBERED_HEADING_START_RE = re.compile(r"(?m)^[ \t]*\d+(?:\.\d+)*\.?[ \t]+\S")
_SUBSCRIPT_WARNING_MARKER = "native text may have separated chemical subscripts"
_SUSPICIOUS_SUBSCRIPT_ORDER = re.compile(
    r"\b(?:details\s+of\s+)?\d\s+\d+\s+achievable\s+"
    r"[A-Z][a-z]?\s*/\s*[A-Z][a-z]?\b",
    re.I,
)

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
    ocr_warning: bool = False  # page was OCR-derived or structurally errored


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
        ocr_warning: ``True`` when any contributing page was OCR-derived
            (``ocr_needed``) or carries a parse/structure error in its
            ``structural_metadata`` (CP27.7).  Candidates drawn from such a
            window are flagged ``UNCERTAIN`` by the extraction orchestrator
            (CP28.7) rather than presented as confirmed.
    """

    chunk_id: str
    text: str
    sources: tuple[TrustedSourceContext, ...]
    overlap: str | None = None
    hierarchy: tuple[str, ...] = ()
    table_context: tuple[str, ...] = ()
    ocr_warning: bool = False
    literal_source_row: bool = False


def _line_kind(line: str) -> str:
    """Classify a single line into ``clause`` / ``table`` / ``para`` / ``blank``."""

    if _BLANK_RE.match(line):
        return "blank"
    if _CLAUSE_RE.match(line) or _LETTERED_ROW_RE.match(line):
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


def _visual_review_applies(page: DocumentPage, text: str) -> bool:
    metadata = page.structural_metadata or {}
    if not metadata.get("visual_verification_required"):
        return False
    warnings = metadata.get("warnings", ())
    if any(_SUBSCRIPT_WARNING_MARKER in str(item).casefold() for item in warnings):
        return bool(_SUSPICIOUS_SUBSCRIPT_ORDER.search(text))
    return True


def _segment_page(
    page: DocumentPage,
    *,
    scope_ranges: Sequence[SourceTextRange] | None = None,
) -> list[_Segment]:
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

    # A page is "uncertain" if it was OCR-derived or carries a parse/structure
    # error from cleanup.  All segments from such a page inherit the flag so the
    # extraction orchestrator (CP28.7) can bump affected candidates' uncertainty.
    page_metadata = page.structural_metadata or {}
    page_ocr_warning = bool(page.ocr_needed) or bool(page_metadata.get("error"))

    cur_kind: str | None = None
    cur_lines: list[tuple[str, int, int]] = []
    cur_table_label: str | None = None
    previous_line_in_scope: bool | None = None

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
                ocr_warning=page_ocr_warning or _visual_review_applies(page, body),
            )
        )

    for line, kind, start, end in records:
        line_in_scope = scope_ranges is None or any(
            start >= source_range.start and end <= source_range.end
            for source_range in scope_ranges
        )
        if (
            previous_line_in_scope is not None
            and line_in_scope != previous_line_in_scope
        ):
            flush()
            cur_kind = None
            cur_lines = []
            cur_table_label = None
        previous_line_in_scope = line_in_scope

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
                    ocr_warning=page_ocr_warning or _visual_review_applies(page, line),
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
    window_spans: dict[int, list[int]] = field(default_factory=dict)
    table_labels: list[str] = field(default_factory=list)
    hierarchy: tuple[str, ...] = ()
    ocr_warning: bool = False
    active_clause: str | None = None

    def add(self, seg: _Segment) -> None:
        window_start = self.length + (1 if self.parts else 0)
        window_end = window_start + len(seg.text)
        if self.parts:
            self.parts.append(seg.text)
            self.length += 1 + len(seg.text)
        else:
            self.parts.append(seg.text)
            self.length += len(seg.text)

        span = self.sources.setdefault(seg.page_number, [seg.char_start, seg.char_end])
        span[0] = min(span[0], seg.char_start)
        span[1] = max(span[1], seg.char_end)
        window_span = self.window_spans.setdefault(
            seg.page_number, [window_start, window_end]
        )
        window_span[0] = min(window_span[0], window_start)
        window_span[1] = max(window_span[1], window_end)

        if seg.table_label and seg.table_label not in self.table_labels:
            self.table_labels.append(seg.table_label)

        self.ocr_warning = self.ocr_warning or seg.ocr_warning

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
    window_spans: dict[int, list[int]],
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
                window_char_start=window_spans[page_number][0],
                window_char_end=window_spans[page_number][1],
                # OCR confidence is a parser/OCR signal; carry it through.
                ocr_confidence=page.ocr_confidence,
                location_type=LocationType.EXACT,
                # Trusted window text the candidate citation is checked
                # against — the full multi-page window text, not a fragment.
                source_text=window_text,
                # Persist only this window's page span, not the full page for
                # every candidate. The base offset preserves page coordinates.
                page_source_text=(page.cleaned_text or "")[start:end],
                page_source_char_start=start,
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
        acc.window_spans,
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
        ocr_warning=acc.ocr_warning,
    )


def build_source_windows(
    pages: list[DocumentPage],
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    max_chars: int = 1500,
    overlap_chars: int = 150,
    included_ranges_by_page: Mapping[int, Sequence[SourceTextRange]] | None = None,
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
        included_ranges_by_page: Optional source-authorized ranges. When set,
            only complete structural segments wholly inside one of these
            original-page ranges are emitted. Gaps reset overlap so text from
            outside the selected section cannot leak into model context.

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
        scope_ranges = (
            included_ranges_by_page.get(page.page_number, ())
            if included_ranges_by_page is not None
            else None
        )
        segments.extend(_segment_page(page, scope_ranges=scope_ranges))
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
        if included_ranges_by_page is not None:
            allowed_ranges = included_ranges_by_page.get(seg.page_number, ())
            if not any(
                seg.char_start >= source_range.start
                and seg.char_end <= source_range.end
                for source_range in allowed_ranges
            ):
                if not acc.empty:
                    windows.append(
                        _finalize_window(
                            acc, cur_segments, prev_text, overlap_chars,
                            pages_by_number, version_id, organization_id, document_id,
                        )
                    )
                    acc = _WindowAccumulator()
                    cur_segments = []
                # Do not carry an overlap across excluded tender content.
                prev_text = None
                continue

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


def build_lettered_row_windows(
    page: DocumentPage,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    included_ranges: Sequence[SourceTextRange],
) -> list[SourceWindow]:
    """Build one source window per explicit lettered row within selected ranges.

    Dense equipment schedules were being sent to the model in multi-row
    windows, where later sibling requirements could be omitted. This helper
    narrows only that explicit source structure: each window contains one
    lettered row and its wrapped continuation, with exact page-local offsets.
    Numbered headings terminate the final row in a section.
    """
    windows: list[SourceWindow] = []
    for row_range in lettered_row_ranges(page.cleaned_text or "", included_ranges):
        windows.extend(
            replace(window, literal_source_row=True)
            for window in build_source_windows(
                [page],
                organization_id=organization_id,
                document_id=document_id,
                max_chars=max(1, row_range.end - row_range.start),
                overlap_chars=0,
                included_ranges_by_page={
                    page.page_number: (row_range,)
                },
            )
        )
    return windows


def build_literal_source_window(
    page: DocumentPage,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    char_start: int,
    char_end: int,
    clause_number: str | None = None,
    table_context: Sequence[str] = (),
) -> SourceWindow:
    """Anchor one already-segmented source row without asking a model to copy it."""
    page_text = page.cleaned_text or ""
    if char_start < 0 or char_end > len(page_text) or char_start >= char_end:
        raise ValueError("source row offsets must select text within the page")
    text = page_text[char_start:char_end]
    page_metadata = page.structural_metadata or {}
    ocr_warning = (
        bool(page.ocr_needed)
        or bool(page_metadata.get("error"))
        or _visual_review_applies(page, text)
    )
    source = TrustedSourceContext.from_page(
        page,
        organization_id,
        document_id,
        clause_number=clause_number,
        source_text=text,
        location_type=LocationType.EXACT,
    ).model_copy(
        update={
            "char_start": char_start,
            "char_end": char_end,
            "window_char_start": 0,
            "window_char_end": len(text),
            "page_source_text": page_text,
            "page_source_char_start": 0,
        }
    )
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    key = f"{page.document_version_id}:{page.page_number}:{char_start}:{char_end}:{content_hash}"
    chunk_id = "cw-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return SourceWindow(
        chunk_id=chunk_id,
        text=text,
        sources=(source,),
        table_context=tuple(table_context),
        ocr_warning=ocr_warning,
        literal_source_row=True,
    )


def lettered_row_ranges(
    text: str,
    included_ranges: Sequence[SourceTextRange],
) -> tuple[SourceTextRange, ...]:
    """Return source ranges for each lettered row inside authorized ranges."""
    if not text or not included_ranges:
        return ()
    lettered_starts = {match.start() for match in _LETTERED_ROW_START_RE.finditer(text)}
    boundaries = sorted(
        lettered_starts
        | {match.start() for match in _NUMBERED_HEADING_START_RE.finditer(text)}
    )
    ranges: list[SourceTextRange] = []
    for row_start in sorted(lettered_starts):
        scope = next(
            (
                source_range
                for source_range in included_ranges
                if source_range.start <= row_start < source_range.end
            ),
            None,
        )
        if scope is None:
            continue
        next_boundary = next(
            (start for start in boundaries if start > row_start), scope.end
        )
        row_end = min(next_boundary, scope.end)
        if row_end > row_start:
            ranges.append(SourceTextRange(row_start, row_end))
    return tuple(ranges)


__all__ = [
    "SourceWindow",
    "build_lettered_row_windows",
    "build_source_windows",
    "lettered_row_ranges",
]
