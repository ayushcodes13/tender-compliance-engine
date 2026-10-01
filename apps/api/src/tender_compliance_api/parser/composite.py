"""Composite parser adapter (CP22).

A thin :class:`ParserAdapter` that dispatches to one of several
format-specific sub-adapters by MIME type.  This lets a single
:class:`~tender_compliance_api.worker.JobProcessor` (which holds one
``ParserAdapter``) accept PDF **and** DOCX uploads without any change to
the processor itself.

Provenance note: the composite records its own ``name``/``version`` on a
*ParseResult-fatal* path (when no sub-adapter matches the MIME type), but
on success the sub-adapter's identity is preserved because the processor
records ``parse_result.parser_name`` rather than ``self._parser.name``
(see CP22 change in ``processor.py``).  In other words, a DOCX upload ends
up with ``version.parser_name == "python-docx"`` and a PDF with
``"pypdf"`` — never a lossy ``"composite"`` label.
"""

from __future__ import annotations

import collections.abc

from tender_compliance_api.parser.adapter import (
    ParserAdapter,
    ParseResult,
)


class CompositeParserAdapter(ParserAdapter):
    """Dispatch :meth:`parse` to a sub-adapter by MIME type.

    Args:
        adapters: A mapping of MIME type -> :class:`ParserAdapter` for that
            document format.
    """

    def __init__(self, adapters: collections.abc.Mapping[str, ParserAdapter]) -> None:
        # Copy into a plain dict so later mutation of the caller's mapping
        # cannot silently change dispatch behaviour.
        self._adapters: dict[str, ParserAdapter] = dict(adapters)

    @property
    def name(self) -> str:
        return "composite"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset(self._adapters)

    async def parse(self, data: bytes, mime_type: str) -> ParseResult:
        sub = self._adapters.get(mime_type)
        if sub is None:
            supported = ", ".join(sorted(self._adapters)) or "none"
            return ParseResult(
                parser_name=self.name,
                parser_version=self.version,
                page_count=0,
                pages=[],
                fatal_error=(
                    f"unsupported MIME type: {mime_type} "
                    f"(supported: {supported})"
                ),
            )
        return await sub.parse(data, mime_type)


__all__ = ["CompositeParserAdapter"]
