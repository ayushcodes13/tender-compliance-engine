"""Deterministic page-level structural cleanup (CP23).

This module is deliberately **pure** (no I/O, no DB): it consumes a
list of :class:`PageResult` objects — exactly what the PARSE stage
produces — and returns a cleaned text plus auditable header/footer
metadata for each page.  Keeping it pure makes the cleanup logic unit
testable without a database and independent of parsing/rendering
providers.

Guardrails honoured:

* The parser's raw text is **never mutated**.  We produce a separate
  ``cleaned_text`` (see :class:`PageCleanup`); the raw text lives on
  ``extracted_text`` in :class:`DocumentPage`.
* Only **identical, repeated** lines that appear in the *first* or *last*
  position of multiple pages are treated as header/footer noise.  Lines
  that vary per page (e.g. a "Page 3 of 10" footer) are **not** stripped —
  we refuse to guess at non-deterministic content.
* Numbered-clause references (e.g. ``1.2.3``, ``4.1.``) are never
  treated as header/footer lines, so requirement numbering is preserved.
* What is stripped is always recorded (in ``headers`` / ``footers`` /
  ``warnings``) so the cleanup is reversible and auditable.
* No semantic rewriting is performed — only removal of repeated
  positional noise (AGENTS.md: "Do not perform semantic rewriting").
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from tender_compliance_api.parser.adapter import PageResult

#: A line longer than this is assumed to be content, not a header/footer.
_MAX_HEADER_FOOTER_LEN = 80

#: A header/footer line must appear on at least this many pages …
_MIN_REPEAT_PAGES = 2

#: … and on at least this fraction of pages.
_MIN_REPEAT_FRACTION = 0.5

#: Numbered-clause patterns we must never strip (e.g. "1.2.3 Scope").
_CLAUSE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s")


@dataclass(frozen=True)
class PageCleanup:
    """Per-page output of :func:`cleanup_pages`.

    Attributes:
        cleaned_text: The page text with detected header/footer lines
            removed from the top/bottom.  Identical to the raw text when
            no cleanup applied.
        headers: Repeated header line(s) stripped from the top.
        footers: Repeated footer line(s) stripped from the bottom.
        warnings: Human-readable notes describing what was stripped.
    """

    cleaned_text: str
    headers: list[str] = field(default_factory=list)
    footers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_header_footer_candidate(line: str) -> bool:
    """True if ``line`` looks like a possible header/footer line."""
    if not line:
        return False
    if len(line) > _MAX_HEADER_FOOTER_LEN:
        return False
    if _CLAUSE_RE.match(line):
        return False
    return True


def _repeated_values(lines_for_pages: list[str]) -> set[str]:
    """Return the set of lines repeated on enough pages to be noise."""
    if not lines_for_pages:
        return set()
    threshold = max(_MIN_REPEAT_PAGES, math.ceil(len(lines_for_pages) * _MIN_REPEAT_FRACTION))
    counts: dict[str, int] = {}
    for line in lines_for_pages:
        if not _is_header_footer_candidate(line):
            continue
        counts[line] = counts.get(line, 0) + 1
    return {line for line, count in counts.items() if count >= threshold}


def cleanup_pages(pages: list[PageResult]) -> list[PageCleanup]:
    """Deterministically detect and strip repeated header/footer lines.

    A line is treated as a header if it is the **first** non-empty line of a
    page and the same line recurs (textually identical, case-sensitive) on
    ``>= max(2, ceil(50% * n_pages))`` pages.  Footers are detected the same
    way from the **last** non-empty line.

    For each page, the matched header line is removed from the top and the
    footer line from the bottom of ``cleaned_text``.  No body text is ever
    touched.  All detections are recorded for auditability.
    """
    if not pages:
        return []

    first_lines: list[str] = []
    last_lines: list[str] = []
    for page in pages:
        lines = [ln for ln in page.text.splitlines() if ln.strip()]
        first = lines[0].strip() if lines else ""
        last = lines[-1].strip() if lines else ""
        first_lines.append(first)
        last_lines.append(last)

    headers = _repeated_values(first_lines)
    footers = _repeated_values(last_lines)

    cleanups: list[PageCleanup] = []
    for i, page in enumerate(pages):
        lines = [ln for ln in page.text.splitlines() if ln.strip()]
        page_headers = [ln for ln in [first_lines[i]] if ln in headers]
        page_footers = [ln for ln in [last_lines[i]] if ln in footers]

        cleaned_lines = lines[:]
        if page_headers and cleaned_lines and cleaned_lines[0].strip() == page_headers[0]:
            cleaned_lines = cleaned_lines[1:]
        if page_footers and cleaned_lines and cleaned_lines[-1].strip() == page_footers[0]:
            cleaned_lines = cleaned_lines[:-1]

        cleaned_text = "\n".join(cleaned_lines)
        warnings: list[str] = []
        for h in page_headers:
            warnings.append(f"stripped repeated header line: {h!r}")
        for f in page_footers:
            warnings.append(f"stripped repeated footer line: {f!r}")

        cleanups.append(
            PageCleanup(
                cleaned_text=cleaned_text,
                headers=page_headers,
                footers=page_footers,
                warnings=warnings,
            )
        )
    return cleanups


__all__ = ["PageCleanup", "cleanup_pages"]
