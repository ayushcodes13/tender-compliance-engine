"""Job processing business logic (CP18, CP19).

``JobProcessor`` transforms a :class:`QueuedJob` into concrete
``ProcessingRun`` rows and ``DocumentVersion`` state transitions.
It is deliberately separated from the polling loop so it can be
unit-tested without Redis.

The worker now executes the production ingestion path: PARSE stores source
pages and applies deterministic structural cleanup during page persistence,
OCR handles pages flagged as scanned, and EXTRACT runs the configured
source-bounded requirement extractor.  CLEANUP remains an explicit audit
stage, but its transformation is intentionally performed inside
`DocumentService.store_pages` so raw and cleaned page text are persisted
together atomically.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    OemDocument,
    OemDocumentVersion,
    ProcessingRun,
    ProcessingStage,
    Project,
    RunStatus,
    StoredObject,
)
from tender_compliance_api.document.service import DocumentNotFoundError, DocumentService
from tender_compliance_api.errors import PROCESSING_STAGE_FAILURE
from tender_compliance_api.extraction.adapter import LlmAdapter
from tender_compliance_api.extraction.chunking import (
    SourceWindow,
    build_lettered_row_windows,
    build_literal_source_window,
    build_source_windows,
    lettered_row_ranges,
)
from tender_compliance_api.extraction.extractor import extract_from_windows
from tender_compliance_api.extraction.technical_scope import (
    SourceTextRange,
    select_technical_specification_ranges,
)
from tender_compliance_api.logs import error_category
from tender_compliance_api.ocr.adapter import OcrAdapter
from tender_compliance_api.parser.adapter import ParserAdapter, ParseResult
from tender_compliance_api.queue import QueuedJob
from tender_compliance_api.renderer.adapter import RendererAdapter, RenderResult
from tender_compliance_api.storage.adapter import ObjectStorageAdapter

logger = logging.getLogger(__name__)

# Technical response sheets often contain long nested specification rows that
# exceed the generic short-window default. Keep a complete labeled row and its
# bullets together when possible so the extractor can retain the source's row
# grouping rather than emitting only isolated fragments.
_TECHNICAL_SOURCE_WINDOW_CHARS = 3000
_LETTERED_SPEC_ROW_RE = re.compile(r"^[ \t]*[a-z]\)[ \t]+\S", re.I | re.M)
_SOURCE_ROW_START_RE = re.compile(
    r"(?m)^[ \t]*(?:[a-z]\)|\d+(?:\.\d+)*(?:[.)])?)[ \t]+\S", re.I
)
_STANDALONE_NUMBERED_HEADING_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*[.)]?\s+.{1,70}?\s*$"
)
_TECHNICAL_PREAMBLE_RE = re.compile(
    r"^\s*item\s+details\s+and\s+technical\s+specifications\s+"
    r"as\s+mentioned\s+below\s*:",
    re.I,
)
_TECHNICAL_SECTION_TITLE_RE = re.compile(
    r"^\s*(?:section\s*[-\wIVX]+\s*[/|]\s*)?"
    r"technical\s+(?:specifications?|parameters?)\s*$|"
    r"^.*[/|]\s*technical\s+(?:specifications?|parameters?)\s*$",
    re.I,
)
_STANDALONE_SAMPLE_ROW_HEADING_RE = re.compile(
    r"^\s*other\s+important\s+requirements\s*:\s*$", re.I
)
_NON_ROW_SECTION_LABEL_RE = re.compile(r"^\s*optional\s+items\s*$", re.I)


def _span_is_in_scope(
    start: int, end: int, scope_ranges: tuple[SourceTextRange, ...]
) -> bool:
    cursor = start
    for source_range in sorted(scope_ranges, key=lambda item: item.start):
        if source_range.end <= cursor:
            continue
        if source_range.start > cursor:
            return False
        cursor = max(cursor, source_range.end)
        if cursor >= end:
            return True
    return False


def _boundary_continuation_ranges(
    previous_page: DocumentPage,
    next_page: DocumentPage,
    previous_scope: tuple[SourceTextRange, ...],
    next_scope: tuple[SourceTextRange, ...],
) -> tuple[SourceTextRange, SourceTextRange] | None:
    """Find a labeled source row split across adjacent pages.

    The previous fragment must be in scope and end in a letter-labeled row.
    The next page's leading in-scope text is joined until its next explicit
    row label or numbered heading. The sample response sheets treat unlabeled
    continuation paragraphs as part of the preceding row, including when a
    continuation starts a new sentence.
    """
    previous_text = previous_page.cleaned_text or ""
    next_text = next_page.cleaned_text or ""
    previous_labels = list(_LETTERED_SPEC_ROW_RE.finditer(previous_text))
    next_labels = list(_SOURCE_ROW_START_RE.finditer(next_text))
    if not previous_labels:
        return None
    prev_start = previous_labels[-1].start()
    prev_end = len(previous_text)
    footer = re.search(rf"(?:^|\n)[ \t]*{previous_page.page_number}[ \t]*$", previous_text)
    if footer:
        # Keep the preceding row's terminating newline, which is part of the
        # parser's exact segment span; exclude the standalone footer number.
        prev_end = footer.start() + 1
    next_start = 0
    next_end = next_labels[0].start() if next_labels else len(next_text)
    next_content_end = next_end
    while next_content_end > next_start and next_text[next_content_end - 1].isspace():
        next_content_end -= 1
    next_value = next_text[next_start:next_end].strip()
    if not _span_is_in_scope(prev_start, prev_end, previous_scope):
        return None
    if not _span_is_in_scope(next_start, next_content_end, next_scope):
        return None
    if not next_value or re.match(r"^\s*(?:[a-z]\)|\d+[.)])\s+", next_value, re.I):
        return None
    # A short standalone heading (for example, "Optional Items:") is a new
    # section boundary rather than continuation prose.
    first_line = next_value.splitlines()[0].strip()
    if first_line.endswith(":") and len(first_line.split()) <= 6:
        return None
    return SourceTextRange(prev_start, prev_end), SourceTextRange(next_start, next_end)


def _subtract_source_range(
    ranges: tuple[SourceTextRange, ...],
    excluded: tuple[SourceTextRange, ...] = (),
) -> tuple[SourceTextRange, ...]:
    remaining = list(ranges)
    for removed in excluded:
        next_ranges: list[SourceTextRange] = []
        for source_range in remaining:
            if removed.end <= source_range.start or removed.start >= source_range.end:
                next_ranges.append(source_range)
                continue
            if source_range.start < removed.start:
                next_ranges.append(SourceTextRange(source_range.start, removed.start))
            if removed.end < source_range.end:
                next_ranges.append(SourceTextRange(removed.end, source_range.end))
        remaining = next_ranges
    return tuple(remaining)


def _technical_table_schema(cells: tuple[str, ...]) -> tuple[int, ...] | None:
    labels = tuple(" ".join(cell.casefold().split()) for cell in cells)
    if len(labels) >= 2 and "parameter" in labels[0] and "required specification" in labels[1]:
        return (0, 1)
    if len(labels) >= 2 and any("s.no" in value or "serial" in value for value in labels[0:1]):
        if "technical specification" in labels[1]:
            return (1,)
    if labels and "technical parameters" in labels[0]:
        return (0,)
    return None


def _table_cell_source_windows(
    page: DocumentPage,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    included_ranges: tuple[SourceTextRange, ...],
    schema: tuple[int, ...] | None,
) -> tuple[list[SourceWindow], tuple[SourceTextRange, ...], tuple[int, ...] | None]:
    """Build literal source windows from detected table rows and retain schema."""
    text = page.cleaned_text or ""
    windows = []
    excluded: list[SourceTextRange] = []
    offset = 0
    current_schema = schema
    for raw_line in text.splitlines(keepends=True):
        line_start = offset
        line_end = offset + len(raw_line)
        offset = line_end
        line = raw_line.rstrip("\r\n")
        if not any(
            source_range.start <= line_start and line_end <= source_range.end
            for source_range in included_ranges
        ):
            continue
        if " | " not in line:
            continue
        cells = tuple(line.split(" | "))
        detected_schema = _technical_table_schema(cells)
        if detected_schema is not None:
            current_schema = detected_schema
            excluded.append(SourceTextRange(line_start, line_end))
            continue
        if current_schema is None or max(current_schema, default=0) >= len(cells):
            continue
        # A new response-table heading invalidates the previous column map.
        if any("compliance" in cell.casefold() for cell in cells):
            current_schema = _technical_table_schema(cells)
            if current_schema is not None:
                excluded.append(SourceTextRange(line_start, line_end))
            continue

        cell_ranges: list[tuple[int, int]] = []
        cell_offset = line_start
        for cell in cells:
            cell_ranges.append((cell_offset, cell_offset + len(cell)))
            cell_offset += len(cell) + len(" | ")
        first_cell, last_cell = current_schema[0], current_schema[-1]
        cell_start = cell_ranges[first_cell][0]
        cell_end = cell_ranges[last_cell][1]
        source_value = text[cell_start:cell_end]
        if not source_value.strip():
            continue
        windows.append(
            build_literal_source_window(
                page,
                organization_id=organization_id,
                document_id=document_id,
                char_start=cell_start,
                char_end=cell_end,
                table_context=cells,
            )
        )
        excluded.append(SourceTextRange(line_start, line_end))
    return windows, tuple(excluded), current_schema


def _standalone_numbered_heading_ranges(
    text: str, included_ranges: tuple[SourceTextRange, ...]
) -> tuple[SourceTextRange, ...]:
    """Identify short numbered section labels that the examples keep as rows."""
    found: list[SourceTextRange] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        end = offset + len(line)
        if (
            line.strip()
            and _STANDALONE_NUMBERED_HEADING_RE.fullmatch(line)
            and any(item.start <= offset and end <= item.end for item in included_ranges)
        ):
            body = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s+", "", line).strip()
            # Avoid turning short complete sentences or numbered instructions
            # into heading rows; section labels end in a colon or have no
            # sentence-final punctuation.
            if body.endswith(":") or body[-1:] not in ".!?;":
                found.append(SourceTextRange(offset, end))
        offset += len(raw_line)
    return tuple(found)


def _technical_preamble_ranges(
    text: str, included_ranges: tuple[SourceTextRange, ...]
) -> tuple[SourceTextRange, ...]:
    """Exclude the sample's explicit lead-in sentence from sheet rows."""
    found: list[SourceTextRange] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        end = offset + len(line)
        if (
            _TECHNICAL_PREAMBLE_RE.match(line)
            and any(item.start <= offset and end <= item.end for item in included_ranges)
        ):
            found.append(SourceTextRange(offset, end))
        offset += len(raw_line)
    return tuple(found)


def _technical_section_title_ranges(
    text: str, included_ranges: tuple[SourceTextRange, ...]
) -> tuple[SourceTextRange, ...]:
    found: list[SourceTextRange] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        end = offset + len(line)
        if (
            _TECHNICAL_SECTION_TITLE_RE.fullmatch(line)
            and any(item.start <= offset and end <= item.end for item in included_ranges)
        ):
            found.append(SourceTextRange(offset, end))
        offset += len(raw_line)
    return tuple(found)


def _sample_heading_ranges(
    text: str, included_ranges: tuple[SourceTextRange, ...]
) -> tuple[tuple[SourceTextRange, ...], tuple[SourceTextRange, ...]]:
    """Separate the example's standalone data-row heading from a non-row label."""
    row_headings: list[SourceTextRange] = []
    section_labels: list[SourceTextRange] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        end = offset + len(line)
        if any(item.start <= offset and end <= item.end for item in included_ranges):
            if _STANDALONE_SAMPLE_ROW_HEADING_RE.fullmatch(line):
                row_headings.append(SourceTextRange(offset, end))
            elif _NON_ROW_SECTION_LABEL_RE.fullmatch(line):
                section_labels.append(SourceTextRange(offset, end))
        offset += len(raw_line)
    return tuple(row_headings), tuple(section_labels)

#: The system worker's actor ID — seeded by Alembic migration 0035 because
#: audit_logs.actor_id is a foreign key to users.id.
WORKER_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000100")

#: Stages the worker processes, in order.
STAGES: list[ProcessingStage] = [
    ProcessingStage.PARSE,
    ProcessingStage.OCR,
    ProcessingStage.CLEANUP,
    ProcessingStage.EXTRACT,
]

#: Maximum retry attempts before a job is permanently failed.
MAX_RETRIES = 5


class SessionFactory(Protocol):
    """Protocol for an async session factory (async_sessionmaker)."""

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]: ...


class JobProcessor:
    """Process a single queued document-processing job.

    Idempotency:
    - If the version is already in a terminal state (PARSED, FAILED),
      the job is a no-op (likely re-delivered after a crash).
    - If a ``ProcessingRun`` already exists for the given ``run_id``,
      it is reused rather than duplicated.

    Args:
        session_factory: Callable returning an async context manager
            yielding an ``AsyncSession``.
        parser: :class:`ParserAdapter` used to extract page text (CP19).
            Defaults to :class:`PyMuPDFParserAdapter`.
        renderer: :class:`RendererAdapter` used to rasterize page images
            (CP20).  When ``None``, no page images are produced.  Defaults
            to :class:`PymupdfRendererAdapter`.
        storage: :class:`ObjectStorageAdapter` used to read the original
            document bytes from storage.
        ocr: :class:`OcrAdapter` used to recognize text on scanned pages
            (CP21).  When ``None``, the OCR stage is a no-op (existing
            pages keep their ``ocr_needed`` flag).  Defaults to
            :class:`TesseractOcrAdapter`.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        parser: ParserAdapter | None = None,
        renderer: RendererAdapter | None = None,
        storage: ObjectStorageAdapter | None = None,
        ocr: OcrAdapter | None = None,
        llm: LlmAdapter | None = None,
        verbatim_validation_fallback_enabled: bool = False,
        obligation_coverage_audit_enabled: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._parser = parser or _default_parser()
        # renderer defaults to None (no rendering) so direct JobProcessor
        # construction in tests is a no-op for rendering.  Production
        # workers created via ``create_worker`` inject a real renderer
        # (CP20).
        self._renderer: RendererAdapter | None = renderer
        # OCR defaults to None so tests that construct JobProcessor
        # directly skip OCR (best-effort, non-fatal).  Production workers
        # created via ``create_worker`` inject a real OCR adapter (CP21).
        self._ocr: OcrAdapter | None = ocr
        # LLM extraction defaults to None so tests that construct JobProcessor
        # directly never hit the network.  Production workers created via
        # ``create_worker`` inject a real LLM adapter (CP26); the EXTRACT
        # stage invokes it once implemented (CP28).
        self._llm: LlmAdapter | None = llm
        self._verbatim_validation_fallback_enabled = (
            verbatim_validation_fallback_enabled
        )
        self._obligation_coverage_audit_enabled = obligation_coverage_audit_enabled
        self._storage = storage or _default_storage()

    async def process(self, job: QueuedJob) -> None:
        """Process a single job to completion.

        Raises an exception on unrecoverable failure so the
        :class:`~tender_compliance_worker.worker.Worker` can
        release/requeue the job.
        """
        payload = job.payload
        version_id = uuid.UUID(str(payload["document_version_id"]))
        org_id = uuid.UUID(str(payload["organization_id"]))
        run_id = uuid.UUID(str(payload["run_id"]))

        auth = AuthContext(
            actor_id=WORKER_ACTOR_ID,
            organization_id=org_id,
            roles=frozenset({"worker"}),
        )

        async with self._session_factory() as session:
            svc = DocumentService(session)

            version = await self._get_version(session, version_id)
            if version is None:
                oem_version = await self._get_oem_version(
                    session, version_id, org_id
                )
                if oem_version is None:
                    raise ValueError(
                        f"Document version {version_id} not found in org {org_id}"
                    )
                await self._process_oem(
                    session, svc, auth, oem_version
                )
                await session.commit()
                return

            # Skip if already terminal — job was re-delivered after crash.
            if version.processing_status in (
                DocumentProcessingStatus.PARSED,
                DocumentProcessingStatus.FAILED,
            ):
                logger.info(
                    "Skipping job %s — version %s already %s",
                    job.job_id,
                    version_id,
                    version.processing_status.value,
                )
                return

            # If the version is still UPLOADED (worker picked up the job
            # before the enqueue step ran), transition to QUEUED first.
            if version.processing_status == DocumentProcessingStatus.UPLOADED:
                await svc.transition_to(
                    auth,
                    document_id=version.document_id,
                    version_number=version.version_number,
                    target=DocumentProcessingStatus.QUEUED,
                )

            # Complete each expected stage, in order.
            # begin_run also handles QUEUED → PROCESSING on the first call.
            for stage in STAGES:
                # Skip if this stage was already completed.
                prior = await self._find_run(session, version, run_id, stage)
                if prior and prior.status == RunStatus.COMPLETED:
                    continue
                # Begin the stage (creates ProcessingRun if none exists).
                if prior is None:
                    await svc.begin_run(
                        auth,
                        document_id=version.document_id,
                        version_number=version.version_number,
                        stage=stage,
                        run_id=run_id,
                    )

                if stage == ProcessingStage.PARSE:
                    # Real parsing: read bytes, parse, store pages.
                    # If parsing fails fatally, skip remaining stages.
                    parse_ok = await self._do_parse(
                        session, svc, auth, version, run_id,
                    )
                    if not parse_ok:
                        # PARSE failed — identity was already recorded on the
                        # version from parse_result inside _do_parse.
                        await session.commit()
                        return
                elif stage == ProcessingStage.OCR:
                    # Recognize text on scanned pages (CP21).  Best-effort
                    # and non-fatal — provider/availability errors are
                    # recorded per-page, not raised.
                    await self._do_ocr(
                        session, svc, auth, version, run_id
                    )
                elif stage == ProcessingStage.EXTRACT:
                    # Requirement-candidate extraction (CP28).  Best-effort:
                    # per-window LLM failures are logged and skipped, so a
                    # transient provider outage does not strand the version.
                    # CP31 hardens retry / partial-failure semantics.
                    await self._do_extract(
                        session, svc, auth, version, run_id
                    )
                else:
                    # CLEANUP is an audit/state-machine boundary.  The actual
                    # deterministic header/footer cleanup is applied inside
                    # DocumentService.store_pages during PARSE so raw and
                    # cleaned text are written together atomically.
                    await svc.complete_run(
                        auth,
                        document_id=version.document_id,
                        version_number=version.version_number,
                        stage=stage,
                        run_id=run_id,
                        error_type=None,
                        error_message=None,
                    )

            # Parser identity was recorded inside _do_parse from the
            # ParseResult (so a composite dispatch surfaces the real
            # sub-parser name).  OCR identity (ocr_name/ocr_version) is
            # recorded within _do_ocr when OCR actually runs; leaving the
            # columns NULL when OCR was not used is intentional (avoids
            # claiming text is OCR-derived when it was read natively).
            await session.commit()

    async def _do_parse(
        self,
        session: AsyncSession,
        svc: DocumentService,
        auth: AuthContext,
        version: DocumentVersion,
        run_id: uuid.UUID,
    ) -> bool:
        """Execute the PARSE stage: read bytes, parse, store pages.

        Returns ``True`` on success, ``False`` on fatal error.  On fatal
        errors the run is marked FAILED and the caller skips remaining
        stages.
        """
        # Look up the storage key for this version.
        try:
            storage_key = await svc.get_stored_object_key(
                auth, version.document_id, version.version_number
            )
        except DocumentNotFoundError:
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.PARSE,
                run_id=run_id,
                error_type="StorageError",
                error_message=f"stored object not found for version {version.id}",
            )
            return False

        # Read the original document bytes.
        data = await self._storage.get(storage_key)

        # Parse the document.  Record the parser that *actually* produced
        # this result on the version — if a composite adapter dispatched to
        # a sub-adapter, parse_result.parser_name is the sub-adapter's
        # identity ("pymupdf" / "python-docx"), not the composite's.
        parse_result = await self._parser.parse(data, version.mime_type)

        version.parser_name = parse_result.parser_name
        version.parser_version = parse_result.parser_version

        if parse_result.fatal_error is not None:
            # Fatal parse error — mark the run as failed.
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.PARSE,
                run_id=run_id,
                error_type="ParseError",
                error_message=PROCESSING_STAGE_FAILURE,
            )
            return False

        # Store parsed pages.
        await svc.store_pages(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            parse_result=parse_result,
        )

        # Render visual page assets (best-effort, non-fatal — CP20).
        await self._render_pages(svc, auth, version, data, parse_result)

        # Complete the PARSE run successfully.
        await svc.complete_run(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            stage=ProcessingStage.PARSE,
            run_id=run_id,
            error_type=None,
            error_message=None,
        )
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _render_pages(
        self,
        svc: DocumentService,
        auth: AuthContext,
        version: DocumentVersion,
        data: bytes,
        parse_result: ParseResult,
    ) -> None:
        """Render visual page assets and persist image keys (CP20).

        Best-effort and non-fatal: a renderer exception or a fatal render
        error is logged and recorded per-page (via
        :meth:`DocumentService.store_rendered_pages`) without failing the
        PARSE stage.  If no renderer is configured, this is a no-op.
        """
        if self._renderer is None:
            return
        try:
            render_result = await self._renderer.render(
                data, version.mime_type
            )
        except Exception as exc:  # noqa: BLE001 — never fail parsing on render
            logger.warning(
                "page rendering failed for version %s (error_type=%s, category=%s)",
                version.id,
                type(exc).__name__,
                error_category(exc),
            )
            # Synthesize a fatal RenderResult so the failure is recorded
            # per-page (via store_rendered_pages) rather than only logged.
            render_result = RenderResult(
                renderer_name=self._renderer.name,
                renderer_version=self._renderer.version,
                render_dpi=self._renderer.render_dpi,
                page_count=0,
                pages=[],
                fatal_error="The page renderer could not process this document.",
            )
        try:
            await svc.store_rendered_pages(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                render_result=render_result,
                storage=self._storage,
            )
        except Exception as exc:  # noqa: BLE001 — storage failure is non-fatal
            logger.warning(
                "storing rendered pages failed for version %s (error_type=%s, category=%s)",
                version.id,
                type(exc).__name__,
                error_category(exc),
            )

    async def _do_ocr(
        self,
        session: AsyncSession,
        svc: DocumentService,
        auth: AuthContext,
        version: DocumentVersion,
        run_id: uuid.UUID,
    ) -> None:
        """Execute the OCR stage (CP21).

        Runs OCR on every page flagged ``ocr_needed`` using the rendered
        page images produced by the PARSE stage (CP20).  Provider and
        per-page failures are surfaced as per-page warnings (via
        :meth:`DocumentService.apply_ocr`) and are **never** fatal to the
        job.  When no OCR adapter is configured this completes the OCR run
        as a no-op, preserving prior behavior.
        """
        if self._ocr is None:
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.OCR,
                run_id=run_id,
                error_type=None,
                error_message=None,
            )
            return

        try:
            await svc.apply_ocr(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                ocr_adapter=self._ocr,
                storage=self._storage,
            )
            error_type: str | None = None
            error_message: str | None = None
        except Exception as exc:  # noqa: BLE001 — never fail the job on OCR
            logger.warning(
                "OCR stage failed for version %s (error_type=%s, category=%s)",
                version.id,
                type(exc).__name__,
                error_category(exc),
            )
            error_type = "OCRError"
            error_message = PROCESSING_STAGE_FAILURE

        await svc.complete_run(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            stage=ProcessingStage.OCR,
            run_id=run_id,
            error_type=error_type,
            error_message=error_message,
        )

    async def _do_extract(
        self,
        session: AsyncSession,
        svc: DocumentService,
        auth: AuthContext,
        version: DocumentVersion,
        run_id: uuid.UUID,
    ) -> None:
        """Execute the EXTRACT stage (CP28): chunk + LLM candidate extraction.

        Loads the version's pages, builds trusted source windows (CP27), calls
        the LLM adapter (CP26) per window, logs every call to the EXTRACT run
        (CP26 audit), and persists the validated candidate records.  If no LLM
        adapter is configured (e.g. direct ``JobProcessor`` construction in
        tests) the stage completes as a no-op, preserving prior behavior.

        Per-window LLM failures (:class:`LlmCallError`) are logged and the
        offending window is skipped — the stage still completes so the version
        is not stranded (CP31 hardens retry/partial-failure semantics).
        """

        if self._llm is None:
            # No adapter configured → nothing to extract.  Keep prior behavior
            # (test_worker constructs JobProcessor without an LLM) and complete
            # the EXTRACT run as a clean no-op.
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.EXTRACT,
                run_id=run_id,
                error_type=None,
                error_message=None,
            )
            return

        try:
            pages = await self._load_pages(session, version.id)
            scope = select_technical_specification_ranges(pages)
            if not scope.found:
                await svc.complete_run(
                    auth,
                    document_id=version.document_id,
                    version_number=version.version_number,
                    stage=ProcessingStage.EXTRACT,
                    run_id=run_id,
                    error_type="technical_specification_section_not_found",
                    error_message=(
                        "Could not identify a technical-specification or "
                        "technical-compliance section. No tender text was "
                        "sent for requirement extraction."
                    ),
                )
                return

            # Keep ordinary extraction windows page-local. The only exception
            # is a labeled requirement that visibly continues mid-sentence at
            # the next page; it receives a bounded two-page window with both
            # original page fragments retained as source anchors.
            boundary_continuations: list[
                tuple[DocumentPage, DocumentPage, SourceTextRange, SourceTextRange]
            ] = []
            page_scope = scope.ranges_by_page
            ordered_pages = sorted(pages, key=lambda item: item.page_number)
            excluded_by_page: dict[int, list[SourceTextRange]] = {}
            for previous_page, next_page in zip(
                ordered_pages, ordered_pages[1:], strict=False
            ):
                previous_scope = page_scope.get(previous_page.page_number, ())
                next_scope = page_scope.get(next_page.page_number, ())
                if not previous_scope or not next_scope:
                    continue
                continuation = _boundary_continuation_ranges(
                    previous_page,
                    next_page,
                    previous_scope,
                    next_scope,
                )
                if continuation is None:
                    continue
                previous_range, next_range = continuation
                boundary_continuations.append(
                    (previous_page, next_page, previous_range, next_range)
                )
                excluded_by_page.setdefault(previous_page.page_number, []).append(
                    previous_range
                )
                excluded_by_page.setdefault(next_page.page_number, []).append(
                    next_range
                )

            windows = []
            active_table_schema: tuple[int, ...] | None = None
            for page in ordered_pages:
                page_ranges = page_scope.get(page.page_number)
                if not page_ranges:
                    continue
                included_ranges = _subtract_source_range(
                    page_ranges,
                    tuple(excluded_by_page.get(page.page_number, ())),
                )
                page_text = page.cleaned_text or ""
                preamble_ranges = _technical_preamble_ranges(
                    page_text, included_ranges
                )
                section_title_ranges = _technical_section_title_ranges(
                    page_text,
                    _subtract_source_range(included_ranges, preamble_ranges),
                )
                numbered_headings = _standalone_numbered_heading_ranges(
                    page_text,
                    _subtract_source_range(
                        included_ranges, (*preamble_ranges, *section_title_ranges)
                    ),
                )
                sample_row_headings, nonrow_labels = _sample_heading_ranges(
                    page_text,
                    _subtract_source_range(
                        included_ranges,
                        (
                            *preamble_ranges,
                            *section_title_ranges,
                            *numbered_headings,
                        ),
                    ),
                )
                windows.extend(
                    build_literal_source_window(
                        page,
                        organization_id=auth.organization_id,
                        document_id=version.document_id,
                        char_start=source_range.start,
                        char_end=source_range.end,
                    )
                    for source_range in numbered_headings
                )
                windows.extend(
                    build_literal_source_window(
                        page,
                        organization_id=auth.organization_id,
                        document_id=version.document_id,
                        char_start=source_range.start,
                        char_end=source_range.end,
                    )
                    for source_range in sample_row_headings
                )
                included_ranges = _subtract_source_range(
                    included_ranges,
                    (
                        *preamble_ranges,
                        *section_title_ranges,
                        *numbered_headings,
                        *sample_row_headings,
                        *nonrow_labels,
                    ),
                )
                table_windows, table_row_ranges, active_table_schema = (
                    _table_cell_source_windows(
                        page,
                        organization_id=auth.organization_id,
                        document_id=version.document_id,
                        included_ranges=included_ranges,
                        schema=active_table_schema,
                    )
                )
                windows.extend(table_windows)
                included_ranges = _subtract_source_range(
                    included_ranges, table_row_ranges
                )
                if len(_LETTERED_SPEC_ROW_RE.findall(page.cleaned_text or "")) >= 6:
                    # Give each explicit row and its wrapped continuation its
                    # own request. This prevents omissions in dense schedules
                    # while preserving exact source offsets and scope limits.
                    windows.extend(
                        build_lettered_row_windows(
                            page,
                            organization_id=auth.organization_id,
                            document_id=version.document_id,
                            included_ranges=included_ranges,
                        )
                    )
                    # Keep unlettered technical text and numbered section
                    # descriptions in the ordinary extractor. Removing the
                    # explicit row spans prevents duplicate row extraction.
                    unlettered_ranges = _subtract_source_range(
                        included_ranges,
                        lettered_row_ranges(page.cleaned_text or "", included_ranges),
                    )
                    windows.extend(
                        build_source_windows(
                            [page],
                            organization_id=auth.organization_id,
                            document_id=version.document_id,
                            included_ranges_by_page={
                                page.page_number: unlettered_ranges
                            },
                            max_chars=_TECHNICAL_SOURCE_WINDOW_CHARS,
                        )
                    )
                    continue
                windows.extend(
                    build_source_windows(
                        [page],
                        organization_id=auth.organization_id,
                        document_id=version.document_id,
                        included_ranges_by_page={page.page_number: included_ranges},
                        max_chars=_TECHNICAL_SOURCE_WINDOW_CHARS,
                    )
                )
            for previous_page, next_page, previous_range, next_range in (
                boundary_continuations
            ):
                continuation_windows = build_source_windows(
                    [previous_page, next_page],
                    organization_id=auth.organization_id,
                    document_id=version.document_id,
                    max_chars=5000,
                    overlap_chars=0,
                    included_ranges_by_page={
                        previous_page.page_number: (previous_range,),
                        next_page.page_number: (next_range,),
                    },
                )
                if _LETTERED_SPEC_ROW_RE.match(
                    (previous_page.cleaned_text or "")[previous_range.start :]
                ):
                    continuation_windows = [
                        SourceWindow(
                            chunk_id=window.chunk_id,
                            text=window.text,
                            sources=window.sources,
                            overlap=window.overlap,
                            hierarchy=window.hierarchy,
                            table_context=window.table_context,
                            ocr_warning=window.ocr_warning,
                            literal_source_row=True,
                        )
                        for window in continuation_windows
                    ]
                windows.extend(continuation_windows)
            windows.sort(
                key=lambda window: (
                    window.sources[0].page_number if window.sources else 2**31 - 1,
                    window.sources[0].char_start if window.sources else 2**31 - 1,
                    window.chunk_id,
                )
            )
            if not windows:
                await svc.complete_run(
                    auth,
                    document_id=version.document_id,
                    version_number=version.version_number,
                    stage=ProcessingStage.EXTRACT,
                    run_id=run_id,
                    error_type="technical_specification_text_unavailable",
                    error_message=(
                        "A technical-specification section heading was found, "
                        "but no parseable source text was available within it."
                    ),
                )
                return

            run = await svc.get_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                run_id=run_id,
                stage=ProcessingStage.EXTRACT,
            )
            coverage_audit_enabled = (
                self._obligation_coverage_audit_enabled
                and self._llm.provider != "dev"
            )
            candidate_image_validation_enabled = (
                self._verbatim_validation_fallback_enabled
                and self._llm.provider != "dev"
            )
            coverage_page_images: dict[int, bytes] = {}
            coverage_page_texts: dict[int, str] = {}
            if coverage_audit_enabled or candidate_image_validation_enabled:
                for page in pages:
                    if page.cleaned_text:
                        coverage_page_texts[page.page_number] = page.cleaned_text
                    image_key = page.rendered_image_object_key
                    if image_key:
                        try:
                            coverage_page_images[page.page_number] = (
                                await self._storage.get(image_key)
                            )
                        except Exception:
                            # A missing/unreadable image must fail the visual
                            # audit closed; never substitute OCR text as proof.
                            continue
            outcome = await extract_from_windows(
                windows,
                self._llm,
                log_call=lambda call: svc.log_llm_call(run.id, call),
                enable_verbatim_fallback=self._verbatim_validation_fallback_enabled,
                # Source windows were restricted to an explicitly titled
                # technical-specification section. Source-valid uncertain
                # rows belong in human review so they remain visible in the
                # tender sheet; abstentions and invalid source quotes stay out.
                persist_uncertain_for_review=True,
                enable_obligation_coverage_audit=coverage_audit_enabled,
                coverage_page_images=coverage_page_images,
                coverage_page_texts=coverage_page_texts,
            )
            await svc.store_extraction_candidates(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                run_id=run_id,
                candidates=outcome.candidates,
            )
            # Dedup the freshly-extracted candidates (CP29).  Reconciliation is
            # best-effort: if it fails, candidates are still persisted (CP30
            # can re-reconcile); the EXTRACT run still completes.
            reconciliation_outcome = None
            promoted = 0
            try:
                reconciliation_outcome = await svc.reconcile_version_candidates(
                    auth,
                    document_id=version.document_id,
                    version_number=version.version_number,
                    run_id=run.id,
                )
                # Promote reconciled candidates to persisted Requirements
                # (CP30).  Best-effort: failure here does not undo the
                # already-persisted candidates — CP30 can be re-run.
                try:
                    inserted, skipped = await svc.persist_requirements(
                        auth,
                        document_id=version.document_id,
                        version_number=version.version_number,
                        run_id=run.id,
                    )
                    promoted = inserted
                    if inserted or skipped:
                        logger.info(
                            "EXTRACT promoted %d requirement(s) for version "
                            "%s (%d unchanged skipped)",
                            inserted, version.id, skipped,
                        )
                except Exception as prom_exc:  # noqa: BLE001
                    logger.warning(
                        "EXTRACT requirement promotion failed for version "
                        "%s (error_type=%s, category=%s)",
                        version.id,
                        type(prom_exc).__name__,
                        error_category(prom_exc),
                    )
            except Exception as rec_exc:  # noqa: BLE001
                logger.warning(
                    "EXTRACT reconciliation failed for version %s "
                    "(error_type=%s, category=%s)",
                    version.id,
                    type(rec_exc).__name__,
                    error_category(rec_exc),
                )
            # Record one diagnostics row for this run (CP31) — best-effort,
            # never strands the version if it fails.
            try:
                # Pass the run_id *column* value (run.run_id), not the row PK
                # (run.id): capture_extraction_diagnostics resolves the run via
                # get_run, which matches ProcessingRun.run_id. The PK is a
                # different column and is not what get_run looks up, so passing
                # it raises "processing run … not found" and silently drops the
                # diagnostics row (caught + warned above).
                await svc.capture_extraction_diagnostics(
                    auth,
                    document_id=version.document_id,
                    version_number=version.version_number,
                    run_id=run.run_id,
                    outcome=outcome,
                    reconciliation_outcome=reconciliation_outcome,
                    promoted_count=promoted,
                )
            except Exception as diag_exc:  # noqa: BLE001
                logger.warning(
                    "EXTRACT diagnostics capture failed for version %s: %s",
                    version.id,
                    type(diag_exc).__name__,
                )
        except Exception as exc:  # noqa: BLE001 — never strand the version
            logger.warning(
                "EXTRACT stage failed for version %s (error_type=%s, category=%s)",
                version.id,
                type(exc).__name__,
                error_category(exc),
            )
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.EXTRACT,
                run_id=run_id,
                error_type="ExtractionError",
                error_message=PROCESSING_STAGE_FAILURE,
            )
            return

        await svc.complete_run(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            stage=ProcessingStage.EXTRACT,
            run_id=run_id,
            error_type=None,
            error_message=None,
        )


    async def _process_oem(
        self,
        session: AsyncSession,
        svc: DocumentService,
        auth: AuthContext,
        version: OemDocumentVersion,
    ) -> None:
        """Parse an OEM version into searchable, source-linked text segments.

        OEM jobs intentionally stop after source extraction/indexing. They do not
        run tender requirement extraction or create tender ProcessingRun rows.
        """
        if version.processing_status in (
            DocumentProcessingStatus.PARSED,
            DocumentProcessingStatus.FAILED,
        ):
            return

        previous = version.processing_status
        version.processing_status = DocumentProcessingStatus.PROCESSING
        audit = AuditService(session)
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="oem_document.processing_started",
            entity_type="oem_document_version",
            entity_id=version.id,
            project_id=await svc._oem_project_id_for(version.document_id),  # noqa: SLF001
            metadata={"from": previous.value, "to": "processing"},
        )

        stored_result = await session.execute(
            select(StoredObject).where(
                StoredObject.id == version.stored_object_id,
                StoredObject.organization_id == auth.organization_id,
            )
        )
        stored = stored_result.scalar_one_or_none()
        if stored is None:
            version.processing_status = DocumentProcessingStatus.FAILED
            await audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="oem_document.processing_failed",
                entity_type="oem_document_version",
                entity_id=version.id,
                project_id=await svc._oem_project_id_for(version.document_id),  # noqa: SLF001
                metadata={"reason": "stored_object_missing"},
            )
            return

        try:
            data = await self._storage.get(stored.storage_key)
            parsed = await self._parser.parse(data, version.mime_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OEM parse failed for version %s (error_type=%s, category=%s)",
                version.id,
                type(exc).__name__,
                error_category(exc),
            )
            version.processing_status = DocumentProcessingStatus.FAILED
            await audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="oem_document.processing_failed",
                entity_type="oem_document_version",
                entity_id=version.id,
                project_id=await svc._oem_project_id_for(version.document_id),  # noqa: SLF001
                metadata={"reason": type(exc).__name__},
            )
            return

        version.parser_name = parsed.parser_name
        version.parser_version = parsed.parser_version

        if parsed.fatal_error is not None:
            version.processing_status = DocumentProcessingStatus.FAILED
            await audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="oem_document.processing_failed",
                entity_type="oem_document_version",
                entity_id=version.id,
                project_id=await svc._oem_project_id_for(version.document_id),  # noqa: SLF001
                metadata={"reason": "parser_fatal_error"},
            )
            return

        segments = [
            (page.page_number, page.text)
            for page in parsed.pages
            if page.text.strip()
        ]
        await svc.create_oem_text_segments(
            auth,
            version.document_id,
            version.version_number,
            segments,
        )

        needs_review = any(
            page.error is not None or page.ocr_needed for page in parsed.pages
        )
        version.processing_status = (
            DocumentProcessingStatus.PARTIAL
            if needs_review
            else DocumentProcessingStatus.PARSED
        )
        await audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="oem_document.processing_completed",
            entity_type="oem_document_version",
            entity_id=version.id,
            project_id=await svc._oem_project_id_for(version.document_id),  # noqa: SLF001
            metadata={
                "status": version.processing_status.value,
                "page_count": parsed.page_count,
                "segment_count": len(segments),
            },
        )

    async def _get_oem_version(
        self,
        session: AsyncSession,
        version_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> OemDocumentVersion | None:
        result = await session.execute(
            select(OemDocumentVersion)
            .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                OemDocumentVersion.id == version_id,
                Project.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_version(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> DocumentVersion | None:
        result = await session.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def _load_pages(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> list[DocumentPage]:
        """Load a version's parsed pages in page order for chunking (CP28)."""

        result = await session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version_id)
            .order_by(DocumentPage.page_number)
        )
        return list(result.scalars().all())

    async def _find_run(
        self,
        session: AsyncSession,
        version: DocumentVersion,
        run_id: uuid.UUID,
        stage: ProcessingStage | None = None,
    ) -> ProcessingRun | None:
        query = select(ProcessingRun).where(
            ProcessingRun.document_version_id == version.id,
            ProcessingRun.run_id == run_id,
        )
        if stage is not None:
            query = query.where(ProcessingRun.stage == stage)
        result = await session.execute(query)
        return result.scalar_one_or_none()


def _default_parser() -> ParserAdapter:
    """Return the default production PDF parser (PyMuPDF)."""
    from tender_compliance_api.parser.pymupdf import PyMuPDFParserAdapter

    return PyMuPDFParserAdapter()


def _default_storage() -> ObjectStorageAdapter:
    """Return the configured durable storage adapter."""
    from tender_compliance_api.storage.factory import create_storage_adapter

    return create_storage_adapter()


async def record_failure(
    session_factory: SessionFactory,
    job: QueuedJob,
    error: Exception,
) -> None:
    """Record a permanent failure on the job's ProcessingRun.

    Called by the worker when a job exceeds ``MAX_RETRIES``.
    """
    payload = job.payload
    org_id = uuid.UUID(str(payload["organization_id"]))
    auth = AuthContext(
        actor_id=WORKER_ACTOR_ID,
        organization_id=org_id,
        roles=frozenset({"worker"}),
    )

    async with session_factory() as session:
        svc = DocumentService(session)
        try:
            version = await svc.get_version_or_raise(
                auth,
                uuid.UUID(str(payload["document_id"])),
                int(str(payload["version_number"])),
            )
        except DocumentNotFoundError:
            return

        await svc.complete_run(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            stage=ProcessingStage(str(payload["stage"])),
            run_id=uuid.UUID(str(payload["run_id"])),
            error_type=type(error).__name__,
            error_message=PROCESSING_STAGE_FAILURE,
        )
        await session.commit()
