"""Document domain: processing state machine and version persistence (CP17).

Business rules for document-version processing states live here — not in routes.
Every method takes a verified :class:`AuthContext` so tenant isolation is
enforced in one place, consistent with :mod:`tender_compliance_api.project`.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.config import get_settings
from tender_compliance_api.db.models import (
    Category,
    ConstraintNormalizationState,
    CoverageFindingReview,
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    ExportArtifact,
    ExportFormat,
    ExportStatus,
    ExtractionCandidate,
    ExtractionDiagnostics,
    ExtractionReconciliation,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionWindowAudit,
    OemDocument,
    OemDocumentVersion,
    OemTextSegment,
    ProcessingRun,
    ProcessingStage,
    Project,
    Requirement,
    RequirementConstraint,
    RequirementNote,
    RequirementRelation,
    RequirementRelationType,
    RequirementReviewState,
    RequirementRevision,
    RequirementSource,
    RunStatus,
    StoredObject,
    TenderDocument,
    requirement_categories,
)
from tender_compliance_api.errors import (
    EXPORT_FAILURE,
    PAGE_IMAGE_STORAGE_FAILURE,
    PAGE_OCR_FAILURE,
    PAGE_RENDER_FAILURE,
    PAGE_TEXT_FAILURE,
    PROCESSING_STAGE_FAILURE,
)
from tender_compliance_api.extraction.adapter import LlmAdapter, LlmCallResult
from tender_compliance_api.extraction.constraint_parser import (
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.coverage_audit import quote_is_covered
from tender_compliance_api.extraction.diagnostics import compute_diagnostics
from tender_compliance_api.extraction.extractor import CandidateRecord, ExtractionOutcome
from tender_compliance_api.extraction.qualitative import (
    NORMALIZATION_VERSION,
    QualitativeCondition,
    conservative_normalized_text,
    parse_qualitative_conditions,
)
from tender_compliance_api.extraction.reconcile import (
    DECISION_DEDUP,
    DECISION_SINGLETON,
    ReconciliationInput,
    ReconciliationResult,
    reconcile,
)
from tender_compliance_api.extraction.requirement import (
    PromotionInput,
    ResolvedSource,
    resolve_sources,
    to_promotion_input,
)
from tender_compliance_api.logs import error_category
from tender_compliance_api.parser.cleanup import cleanup_pages
from tender_compliance_api.project.service import ProjectNotFoundError
from tender_compliance_api.queue import make_job_id
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.factory import create_storage_adapter
from tender_compliance_api.storage.keys import build_key

if TYPE_CHECKING:
    from tender_compliance_api.matrix.projection import FinalMatrixRow, MatrixRow
    from tender_compliance_api.ocr.adapter import OcrAdapter
    from tender_compliance_api.parser.adapter import ParseResult
    from tender_compliance_api.renderer.adapter import RenderResult
    from tender_compliance_api.storage.adapter import ObjectStorageAdapter


@dataclass(frozen=True)
class _SourcePageForValidation:
    page_number: int
    image_key: str | None
    ocr_warning: bool
    source_text: str | None
    location_type: str
    char_start: int | None


#: Deterministic namespace for rendered-image object keys, so that
#: re-rendering the same version/page/DPI overwrites the same storage key
#: instead of producing duplicate blobs (CP20 idempotency).
_RENDER_KEY_NAMESPACE = uuid.UUID("00000000-0000-5000-8000-000000000042")


def _resolve_storage() -> ObjectStorageAdapter:
    """Return a storage adapter based on configuration (CP42).

    Mirrors the logic in ``routes/uploads.py:get_storage_adapter`` but as
    a plain function so the service layer can call it without depending
    on FastAPI's dependency-injection machinery.
    """
    return create_storage_adapter()


async def validate_ocr_page_quote_from_image(
    page: DocumentPage, source_quote: str
) -> dict[str, object]:
    """Strictly verify a reviewer-supplied quote against its rendered OCR page.

    Returns only audit-safe provider metadata. Missing image/configuration and
    provider failures remain non-success results so callers can fail closed.
    """
    if not page.rendered_image_object_key:
        return {"status": "image_unavailable"}
    settings = get_settings()
    if not settings.verbatim_validation_fallback_enabled or not settings.openai_api_key.strip():
        return {"status": "validator_unavailable"}

    try:
        image_bytes = await _resolve_storage().get(page.rendered_image_object_key)
    except Exception:  # noqa: BLE001 — inaccessible source image is not proof
        return {"status": "image_unavailable"}

    try:
        from tender_compliance_api.export.visual_validation import (
            validate_quote_on_page_image,
        )
        from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter

        response, call = await validate_quote_on_page_image(
            proposed_quote=source_quote,
            page_number=page.page_number,
            image_bytes=image_bytes,
            image_mime_type="image/png",
            adapter=OpenAiLlmAdapter(),
        )
        return {
            "status": (
                "exact"
                if response is not None and response.verdict == "exact"
                else "needs_review"
            ),
            "provider": call.provider,
            "model": call.model,
            "prompt_version": call.prompt_version,
            "schema_version": call.schema_version,
            "call_status": call.status,
        }
    except Exception:  # noqa: BLE001 — errors cannot authorize a quote
        return {"status": "needs_review"}


async def _source_quote_validation_report(
    session: AsyncSession,
    rows: Sequence[FinalMatrixRow | MatrixRow],
    storage: ObjectStorageAdapter,
    document_version_id: uuid.UUID,
) -> dict[str, object]:
    """Check linked source text and require image verification for OCR pages."""
    from tender_compliance_api.export.validation import (  # noqa: PLC0415
        AuthorizedSourceFragment,
        RequirementCell,
        SourceQuoteIssue,
        validate_source_quote_presence,
    )
    from tender_compliance_api.export.visual_validation import (  # noqa: PLC0415
        MAX_CALLS_PER_PAGE,
        MAX_CONCURRENT_VALIDATIONS,
        MAX_QUOTES_PER_CALL,
        PageImageQuote,
        validate_quotes_on_page_image,
    )

    requirement_ids = [row.requirement_id for row in rows]
    # The exported page is authoritative. Keep that page and any later
    # page-local fragments needed to verify a quote that continues forward.
    selected_page_by_requirement = {
        str(row.requirement_id): row.source_page for row in rows
    }
    sources_by_requirement: dict[str, list[AuthorizedSourceFragment]] = {}
    page_texts_added: set[tuple[str, int]] = set()
    pages_by_requirement: dict[str, list[_SourcePageForValidation]] = {}
    if requirement_ids:
        result = await session.execute(
            select(
                RequirementSource.requirement_id,
                RequirementSource.source_text,
                RequirementSource.page_number,
                RequirementSource.location_type,
                RequirementSource.char_start,
                DocumentPage.rendered_image_object_key,
                DocumentPage.ocr_needed,
                DocumentPage.structural_metadata,
                DocumentPage.cleaned_text,
            ).where(RequirementSource.requirement_id.in_(requirement_ids))
            .where(RequirementSource.document_version_id == document_version_id)
            .outerjoin(
                DocumentPage,
                (DocumentPage.document_version_id == RequirementSource.document_version_id)
                & (DocumentPage.page_number == RequirementSource.page_number),
            )
        )
        for (
            requirement_id,
            source_text,
            page_number,
            location_type,
            char_start,
            image_key,
            page_ocr_needed,
            structural_metadata,
            page_text,
        ) in result:
            requirement_key = str(requirement_id)
            if not isinstance(page_number, int):
                continue
            selected_page = selected_page_by_requirement.get(requirement_key)
            if selected_page is not None and page_number < selected_page:
                continue
            if isinstance(source_text, str) and source_text:
                sources_by_requirement.setdefault(requirement_key, []).append(
                    AuthorizedSourceFragment(
                        page_number=(page_number if isinstance(page_number, int) else None),
                        text=source_text,
                        page_local=location_type == "exact",
                        char_start=(char_start if isinstance(char_start, int) else None),
                    )
                )
            # Approximate anchors can retain a whole extraction window on
            # several pages. Check the selected page's own parsed text as
            # page-scoped wording evidence, without upgrading the anchor's
            # location precision or using page text to stitch multi-page
            # quotes together.
            page_text_key = (requirement_key, page_number)
            if isinstance(page_text, str) and page_text and page_text_key not in page_texts_added:
                sources_by_requirement.setdefault(requirement_key, []).append(
                    AuthorizedSourceFragment(
                        page_number=page_number,
                        text=page_text,
                        page_local=False,
                        authoritative_page_text=True,
                    )
                )
                page_texts_added.add(page_text_key)
            page_metadata = (
                structural_metadata if isinstance(structural_metadata, dict) else {}
            )
            pages_by_requirement.setdefault(requirement_key, []).append(
                _SourcePageForValidation(
                    page_number=page_number,
                    image_key=image_key if isinstance(image_key, str) else None,
                    ocr_warning=bool(page_ocr_needed)
                    or bool(page_metadata.get("error"))
                    or bool(page_metadata.get("visual_verification_required")),
                    source_text=(source_text if isinstance(source_text, str) else None),
                    location_type=str(location_type),
                    char_start=(char_start if isinstance(char_start, int) else None),
                )
            )

    expected = [
        RequirementCell(
            str(row.requirement_id), row.raw_source, source_page=row.source_page
        )
        for row in rows
    ]
    issues = list(validate_source_quote_presence(expected, sources_by_requirement))
    visual_required_ids = {
        str(row.requirement_id) for row in rows if row.ocr_warning
    }
    visual_required_ids.update(
        requirement_id
        for requirement_id, page_sources in pages_by_requirement.items()
        if any(page.ocr_warning for page in page_sources)
    )
    issue_ids = {
        issue.row_id
        for issue in issues
        if issue.code
        in {
            "source_text_unavailable",
            "source_quote_not_found",
            "ocr_visual_verification_required",
        }
    }
    issues.extend(
        SourceQuoteIssue(requirement_id, "ocr_visual_verification_required")
        for requirement_id in sorted(visual_required_ids - issue_ids)
    )
    settings = get_settings()
    adapter: LlmAdapter | None = None
    if settings.verbatim_validation_fallback_enabled and settings.openai_api_key.strip():
        from tender_compliance_api.extraction.openai_adapter import (  # noqa: PLC0415
            OpenAiLlmAdapter,
        )

        adapter = OpenAiLlmAdapter()

    row_by_id = {str(row.requirement_id): row for row in rows}
    fallback_results: list[dict[str, object]] = []
    resolved_ids: set[str] = set()

    def validation_parts(
        quote: str,
        page_sources: Sequence[_SourcePageForValidation],
        selected_page: int | None,
    ) -> list[tuple[_SourcePageForValidation, str]]:
        normalized_quote = re.sub(r"\s+", " ", quote).strip()
        exact_sources = [
            page
            for page in page_sources
            if page.location_type == "exact" and page.source_text
            and (selected_page is None or page.page_number >= selected_page)
        ]
        pages_to_check = (
            [page for page in exact_sources if page.page_number == selected_page]
            if selected_page is not None
            else exact_sources
        )
        text_pages: dict[str, set[int]] = {}
        for page in exact_sources:
            page_text = re.sub(r"\s+", " ", page.source_text or "").strip()
            text_pages.setdefault(page_text, set()).add(page.page_number)
        duplicated_window_texts = {
            page_text for page_text, numbers in text_pages.items() if len(numbers) > 1
        }
        for page in sorted(pages_to_check, key=lambda item: item.page_number):
            normalized_source = re.sub(r"\s+", " ", page.source_text or "").strip()
            if (
                normalized_quote
                and normalized_quote in normalized_source
                and normalized_source not in duplicated_window_texts
            ):
                return [(page, quote)]

        by_page: dict[int, list[_SourcePageForValidation]] = {}
        for page in exact_sources:
            by_page.setdefault(page.page_number, []).append(page)
        ordered_pages = sorted(by_page)
        if selected_page is not None:
            ordered_pages = [page for page in ordered_pages if page >= selected_page]
            if selected_page not in ordered_pages:
                ordered_pages = []
        if ordered_pages and all(
            current == previous + 1
            for previous, current in zip(ordered_pages, ordered_pages[1:], strict=False)
        ):
            page_parts = []
            for page_number in ordered_pages:
                page_items = sorted(
                    by_page[page_number],
                    key=lambda item: (
                        item.char_start if item.char_start is not None else -1
                    ),
                )
                page_parts.append(
                    "\n".join(item.source_text or "" for item in page_items)
                )
            if re.sub(r"\s+", " ", "\n".join(page_parts)).strip() == normalized_quote:
                representative_by_page = {
                    page_number: min(
                        by_page[page_number],
                        key=lambda item: (
                            item.char_start if item.char_start is not None else -1
                        ),
                    )
                    for page_number in ordered_pages
                }
                return [
                    (representative_by_page[page_number], page_part)
                    for page_number, page_part in zip(
                        ordered_pages, page_parts, strict=True
                    )
                ]

        unique_pages = {page.page_number: page for page in page_sources}
        if selected_page is not None:
            selected = unique_pages.get(selected_page)
            return [(selected, quote)] if selected is not None else []
        return [(page, quote) for page in unique_pages.values()]

    if adapter is not None:
        eligible_issues = [
            issue
            for issue in issues
            if issue.code in {
                "source_text_unavailable",
                "source_quote_not_found",
                "ocr_visual_verification_required",
            }
        ]
        planned_parts: dict[str, list[tuple[_SourcePageForValidation, str]]] = {}
        targets_by_page: dict[
            tuple[int, str | None],
            list[tuple[str, int, _SourcePageForValidation, str]],
        ] = {}
        for issue in eligible_issues:
            row = row_by_id.get(issue.row_id)
            if row is None:
                continue
            parts = validation_parts(
                row.raw_source,
                pages_by_requirement.get(issue.row_id, []),
                selected_page_by_requirement.get(issue.row_id),
            )
            planned_parts[issue.row_id] = parts
            for part_index, (page_source, proposed_quote) in enumerate(parts):
                key = (page_source.page_number, page_source.image_key)
                targets_by_page.setdefault(key, []).append(
                    (issue.row_id, part_index, page_source, proposed_quote)
                )

        fallback_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)
        outcomes_by_row: dict[str, list[bool]] = {
            issue.row_id: [] for issue in eligible_issues
        }
        results_by_row: dict[str, list[dict[str, object]]] = {
            issue.row_id: [] for issue in eligible_issues
        }
        for issue in eligible_issues:
            if not planned_parts.get(issue.row_id):
                results_by_row[issue.row_id].append(
                    {
                        "row_id": issue.row_id,
                        "status": "source_page_unavailable",
                        "verdict": "not_run",
                        "reason_code": "source_page_unavailable",
                        "call_status": "not_run",
                    }
                )
                outcomes_by_row[issue.row_id].append(False)

        async def validate_page_group(
            key: tuple[int, str | None],
            targets: list[tuple[str, int, _SourcePageForValidation, str]],
        ) -> list[tuple[str, bool, dict[str, object]]]:
            page_number, image_key = key
            if image_key is None:
                return [
                    (
                        row_id,
                        False,
                        {
                            "row_id": row_id,
                            "page_number": page_number,
                            "status": "image_unavailable",
                            "verdict": "unavailable",
                            "reason_code": "page_image_unavailable",
                            "call_status": "not_run",
                        },
                    )
                    for row_id, _part, _source, _quote in targets
                ]
            try:
                image_bytes = await storage.get(image_key)
            except Exception:  # noqa: BLE001 — fail closed on image retrieval
                return [
                    (
                        row_id,
                        False,
                        {
                            "row_id": row_id,
                            "page_number": page_number,
                            "status": "image_unavailable",
                            "verdict": "unavailable",
                            "reason_code": "page_image_unavailable",
                            "call_status": "not_run",
                        },
                    )
                    for row_id, _part, _source, _quote in targets
                ]

            page_results: list[tuple[str, bool, dict[str, object]]] = []
            call_budget = 0
            for chunk_start in range(0, len(targets), MAX_QUOTES_PER_CALL):
                chunk = targets[chunk_start : chunk_start + MAX_QUOTES_PER_CALL]
                if call_budget >= MAX_CALLS_PER_PAGE:
                    page_results.extend(
                        (
                            row_id,
                            False,
                            {
                                "row_id": row_id,
                                "page_number": page_number,
                                "status": "call_limit_reached",
                                "verdict": "not_run",
                                "reason_code": "visual_call_limit_reached",
                                "call_status": "not_run",
                            },
                        )
                        for row_id, _part, _source, _quote in chunk
                    )
                    continue
                call_budget += 1
                request_items = [
                    PageImageQuote(item_id=str(index), proposed_quote=quote)
                    for index, (_row_id, _part, _source, quote) in enumerate(chunk)
                ]
                async with fallback_semaphore:
                    decisions, call = await validate_quotes_on_page_image(
                        items=request_items,
                        page_number=page_number,
                        image_bytes=image_bytes,
                        image_mime_type="image/png",
                        adapter=adapter,
                    )
                for index, (row_id, _part, _source, _quote) in enumerate(chunk):
                    decision = decisions.get(str(index))
                    accepted = decision is not None and decision.verdict == "exact"
                    if accepted:
                        verdict = "exact"
                        reason_code = "visual_exact_match"
                    elif call.status != "completed" or decision is None:
                        verdict = "unavailable"
                        reason_code = "visual_validation_unavailable"
                    elif decision.verdict == "not_exact":
                        verdict = "not_exact"
                        reason_code = "visual_wording_mismatch"
                    else:
                        verdict = "cannot_tell"
                        reason_code = "visual_result_uncertain"
                    page_results.append(
                        (
                            row_id,
                            accepted,
                            {
                                "row_id": row_id,
                                "page_number": page_number,
                                "status": "exact" if accepted else "needs_review",
                                "verdict": verdict,
                                "reason_code": reason_code,
                                "provider": call.provider,
                                "model": call.model,
                                "prompt_version": call.prompt_version,
                                "schema_version": call.schema_version,
                                "call_status": call.status,
                                "latency_ms": call.latency_ms,
                                "prompt_tokens": call.prompt_tokens,
                                "completion_tokens": call.completion_tokens,
                                "total_tokens": call.total_tokens,
                                "error_category": call.error_category,
                            },
                        )
                    )
            return page_results

        page_results = await asyncio.gather(
            *(
                validate_page_group(key, targets)
                for key, targets in targets_by_page.items()
            )
        )
        for page_group_result in page_results:
            for row_id, accepted, metadata in page_group_result:
                outcomes_by_row.setdefault(row_id, []).append(accepted)
                results_by_row.setdefault(row_id, []).append(metadata)
        for row_id, row_results in results_by_row.items():
            fallback_results.extend(row_results)
            if outcomes_by_row.get(row_id) and all(outcomes_by_row[row_id]):
                resolved_ids.add(row_id)

    unresolved_issues = [issue for issue in issues if issue.row_id not in resolved_ids]
    return {
        "status": "needs_review" if unresolved_issues else "passed",
        "checked_rows": len(expected),
        "llm_assisted_rows": sorted(resolved_ids),
        "issues": [
            {"row_id": issue.row_id, "code": issue.code}
            for issue in unresolved_issues
        ],
        "llm_fallback_results": fallback_results,
    }


async def _extraction_window_coverage_report(
    session: AsyncSession,
    document_version_id: uuid.UUID,
) -> dict[str, object]:
    """Report whether the latest extraction run reached every source window.

    This is processing coverage only. A successful model call does not prove
    that the model found every technical obligation in that window.
    """
    diagnostics = (
        await session.execute(
            select(ExtractionDiagnostics)
            .where(ExtractionDiagnostics.document_version_id == document_version_id)
            .order_by(
                ExtractionDiagnostics.created_at.desc(),
                ExtractionDiagnostics.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if diagnostics is None or diagnostics.processing_run_id is None:
        return {
            "status": "not_available",
            "completeness_proven": False,
            "obligation_audit_status": "not_available",
            "obligation_audited_windows": 0,
            "obligation_audit_failed_windows": [],
            "potential_omissions": [],
            "message": "No extraction-window audit is available for this version.",
        }

    audits = list(
        (
            await session.execute(
                select(ExtractionWindowAudit)
                .where(
                    ExtractionWindowAudit.processing_run_id
                    == diagnostics.processing_run_id
                )
                .order_by(ExtractionWindowAudit.window_index.asc())
            )
        ).scalars().all()
    )
    expected = max(diagnostics.total_windows, 0)
    missing_count = max(expected - len(audits), 0)
    failed = [audit for audit in audits if audit.call_status != "completed"]
    emitted_source_rows = list(
        (
            await session.execute(
                select(
                    Requirement.id,
                    Requirement.raw_source,
                    RequirementSource.page_number,
                )
                .join(RequirementSource, RequirementSource.requirement_id == Requirement.id)
                .where(
                    Requirement.document_version_id == document_version_id,
                    Requirement.superseded.is_(False),
                )
            )
        ).all()
    )
    page_texts = dict(
        (
            await session.execute(
                select(DocumentPage.page_number, DocumentPage.cleaned_text).where(
                    DocumentPage.document_version_id == document_version_id
                )
            )
        ).all()
    )
    emitted_quotes_by_requirement: dict[uuid.UUID, list[tuple[str, int]]] = {}
    for requirement_id, raw_source, page_number in emitted_source_rows:
        if isinstance(raw_source, str):
            emitted_quotes_by_requirement.setdefault(requirement_id, []).append(
                (raw_source, page_number)
            )

    review_rows = list(
        (
            await session.execute(
                select(CoverageFindingReview)
                .where(
                    CoverageFindingReview.document_version_id == document_version_id
                )
                .order_by(
                    CoverageFindingReview.created_at.asc(),
                    CoverageFindingReview.id.asc(),
                )
            )
        ).scalars().all()
    )
    latest_reviews: dict[tuple[int, str], CoverageFindingReview] = {}
    for review in review_rows:
        latest_reviews[(review.page_number, review.source_quote_sha256)] = review

    def window_record(audit: ExtractionWindowAudit) -> dict[str, object]:
        spans = audit.source_spans if isinstance(audit.source_spans, list) else []
        return {
            "window_index": audit.window_index,
            "chunk_id": audit.chunk_id,
            "coverage_error_category": audit.coverage_error_category,
            "pages": sorted(
                {
                    int(span["page_number"])
                    for span in spans
                    if isinstance(span, dict)
                    and isinstance(span.get("page_number"), int)
                }
            ),
        }

    status = (
        "complete"
        if not missing_count and len(audits) == expected and not failed
        else "incomplete"
    )
    coverage_completed = [
        audit for audit in audits if audit.coverage_status == "completed"
    ]
    coverage_not_run = [
        audit for audit in audits if audit.coverage_status == "not_run"
    ]
    coverage_failed = [
        audit
        for audit in audits
        if audit.coverage_status not in {"completed", "not_run"}
    ]
    potential_omissions: list[dict[str, object]] = []
    resolved_omissions: list[dict[str, object]] = []
    seen_omissions: set[tuple[tuple[int, ...], str]] = set()
    seen_resolved_omissions: set[tuple[int, str]] = set()
    # Keep page-image findings from pages that were audited successfully even
    # when another page in the same OCR window was unreadable. The window
    # remains failed closed, but known findings should still reach reviewers.
    coverage_with_findings = [
        audit
        for audit in audits
        if audit.coverage_status != "not_run"
        and isinstance(audit.potential_omissions, list)
        and audit.potential_omissions
    ]
    for audit in coverage_with_findings:
        spans = audit.source_spans if isinstance(audit.source_spans, list) else []
        pages = sorted(
            {
                int(span["page_number"])
                for span in spans
                if isinstance(span, dict)
                and isinstance(span.get("page_number"), int)
            }
        )
        quotes = audit.potential_omissions
        if not isinstance(quotes, list):
            continue
        for item in quotes:
            explicit_page: int | None = None
            if isinstance(item, dict):
                quote = item.get("source_quote")
                candidate_page = item.get("page_number")
                if isinstance(candidate_page, int) and not isinstance(candidate_page, bool):
                    explicit_page = candidate_page
            else:
                quote = item
            if not isinstance(quote, str):
                continue
            normalized_quote = re.sub(r"\s+", " ", quote).strip()
            quote_pages = (
                [explicit_page]
                if explicit_page is not None and explicit_page in pages
                else [
                    page_number
                    for page_number in pages
                    if isinstance(page_texts.get(page_number), str)
                    and normalized_quote
                    and re.sub(
                        r"\s+", " ", str(page_texts[page_number])
                    ).strip().count(normalized_quote)
                    == 1
                ]
            )
            finding_pages = quote_pages if len(quote_pages) == 1 else pages
            same_window_quotes = [
                raw_source
                for _requirement_id, raw_source, page_number in emitted_source_rows
                if isinstance(raw_source, str)
                and len(quote_pages) == 1
                and page_number in finding_pages
            ]
            # A multi-page window cannot be resolved by finding identical
            # words on some other page; exact page provenance is required.
            resolved_on_same_page = (
                len(pages) == 1 or len(quote_pages) == 1
            )
            unresolved_pages: list[int] = []
            quote_digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            for page_number in finding_pages:
                finding_review = latest_reviews.get((page_number, quote_digest))
                is_valid_review = False
                if finding_review is not None and finding_review.decision == "not_in_scope":
                    is_valid_review = True
                elif (
                    finding_review is not None
                    and finding_review.decision == "covered_by_requirement"
                    and finding_review.requirement_id is not None
                ):
                    is_valid_review = any(
                        source_page == page_number
                        and quote_is_covered(quote, [raw_source])
                        for raw_source, source_page in emitted_quotes_by_requirement.get(
                            finding_review.requirement_id, []
                        )
                    )
                if is_valid_review and finding_review is not None:
                    resolved_key = (page_number, quote)
                    if resolved_key not in seen_resolved_omissions:
                        seen_resolved_omissions.add(resolved_key)
                        resolved_omissions.append(
                            {
                                "window_index": audit.window_index,
                                "page_number": page_number,
                                "source_quote": quote,
                                "decision": finding_review.decision,
                                "rationale": finding_review.rationale,
                                "requirement_id": (
                                    str(finding_review.requirement_id)
                                    if finding_review.requirement_id is not None
                                    else None
                                ),
                                "actor_id": (
                                    str(finding_review.actor_id)
                                    if finding_review.actor_id is not None
                                    else None
                                ),
                                "reviewed_at": finding_review.created_at.isoformat(),
                            }
                        )
                else:
                    unresolved_pages.append(page_number)

            if unresolved_pages and (
                not resolved_on_same_page
                or not quote_is_covered(quote, same_window_quotes)
            ):
                key = (tuple(unresolved_pages), quote)
                if key in seen_omissions:
                    continue
                seen_omissions.add(key)
                potential_omissions.append(
                    {
                        "window_index": audit.window_index,
                        "pages": unresolved_pages,
                        "source_quote": quote,
                        "coverage_candidates": [
                            {
                                "requirement_id": str(requirement_id),
                                "page_number": source_page,
                                "label": raw_source,
                            }
                            for requirement_id, raw_source, source_page in emitted_source_rows
                            if isinstance(raw_source, str)
                            and source_page in unresolved_pages
                            and quote_is_covered(quote, [raw_source])
                        ],
                    }
                )

    if status == "incomplete":
        coverage_status = "incomplete"
    elif coverage_failed or (
        coverage_completed and coverage_not_run
    ):
        coverage_status = "audit_failed"
    elif coverage_not_run or not coverage_completed:
        coverage_status = "not_available"
    elif potential_omissions:
        coverage_status = "potential_omissions"
    else:
        coverage_status = "no_potential_omissions"

    return {
        "status": status,
        "completeness_proven": False,
        "obligation_audit_status": coverage_status,
        "obligation_audited_windows": len(coverage_completed),
        "obligation_audit_failed_windows": [
            window_record(audit) for audit in coverage_failed
        ],
        "potential_omissions": potential_omissions,
        "resolved_omissions": resolved_omissions,
        "expected_windows": expected,
        "audited_windows": len(audits),
        "missing_window_count": missing_count,
        "failed_windows": [window_record(audit) for audit in failed],
        "zero_candidate_windows": [
            window_record(audit)
            for audit in audits
            if audit.call_status == "completed" and audit.candidate_count == 0
        ],
        "ocr_warning_windows": [
            window_record(audit) for audit in audits if audit.ocr_warning
        ],
        "message": (
            "Every recorded source window received a completed extraction call. "
            "This does not prove that every technical obligation was identified."
            if status == "complete"
            else "One or more source windows were not successfully audited."
        ),
    }


class DocumentNotFoundError(Exception):
    """Raised when a TenderDocument or DocumentVersion is not found or not owned."""


class ConcurrentEditError(Exception):
    """Raised when a requirement edit is rejected due to optimistic
    concurrency — the requirement was modified by another actor between
    the client's read and write.

    Carries the ``current_updated_at`` so the caller can retry with a fresh
    read.
    """

    def __init__(self, current_updated_at: datetime | None) -> None:
        self.current_updated_at = current_updated_at
        super().__init__(
            "The requirement was modified by another user. "
            "Please refresh and try again."
        )


class TransitionError(Exception):
    """Raised when a processing-state transition is not permitted."""


# ---------------------------------------------------------------------------
# State-machine definition
# ---------------------------------------------------------------------------

# Allowed transitions for DocumentVersion.processing_status.
# Keys are the current state; values are the states it can move to.
_ALLOWED_TRANSITIONS: dict[
    DocumentProcessingStatus, frozenset[DocumentProcessingStatus]
] = {
    DocumentProcessingStatus.UPLOADED: frozenset(
        {DocumentProcessingStatus.QUEUED}
    ),
    DocumentProcessingStatus.QUEUED: frozenset(
        {DocumentProcessingStatus.PROCESSING}
    ),
    DocumentProcessingStatus.PROCESSING: frozenset(
        {
            DocumentProcessingStatus.PARSED,
            DocumentProcessingStatus.PARTIAL,
            DocumentProcessingStatus.FAILED,
            DocumentProcessingStatus.QUEUED,
        }
    ),
    DocumentProcessingStatus.PARTIAL: frozenset(
        {DocumentProcessingStatus.QUEUED, DocumentProcessingStatus.PARSED}
    ),
    DocumentProcessingStatus.PARSED: frozenset(set()),
    DocumentProcessingStatus.FAILED: frozenset(
        {DocumentProcessingStatus.QUEUED}
    ),
}


def _is_valid_transition(
    current: DocumentProcessingStatus, target: DocumentProcessingStatus
) -> bool:
    """Return True if *target* is an allowed transition from *current*."""
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


# ---------------------------------------------------------------------------
# Review state machine (CP40)
# ---------------------------------------------------------------------------

# Allowed transitions for RequirementReviewState.
# Keys are the current state; values are the states it can move to.
# Phase 1 review states only — never vendor-compliance verdicts.
_ALLOWED_REVIEW_TRANSITIONS: dict[
    RequirementReviewState, frozenset[RequirementReviewState]
] = {
    RequirementReviewState.UNREVIEWED: frozenset(
        {
            RequirementReviewState.REVIEWED,
            RequirementReviewState.NEEDS_CLARIFICATION,
            RequirementReviewState.OCR_WARNING,
        }
    ),
    RequirementReviewState.REVIEWED: frozenset(
        {
            RequirementReviewState.UNREVIEWED,
            RequirementReviewState.NEEDS_CLARIFICATION,
        }
    ),
    RequirementReviewState.NEEDS_CLARIFICATION: frozenset(
        {
            RequirementReviewState.UNREVIEWED,
            RequirementReviewState.REVIEWED,
            RequirementReviewState.OCR_WARNING,
        }
    ),
    RequirementReviewState.OCR_WARNING: frozenset(
        {
            RequirementReviewState.UNREVIEWED,
            RequirementReviewState.REVIEWED,
            RequirementReviewState.NEEDS_CLARIFICATION,
        }
    ),
}


def _is_valid_review_transition(
    current: RequirementReviewState, target: RequirementReviewState
) -> bool:
    """Return True if *target* is an allowed review-state transition from
    *current*."""
    return target in _ALLOWED_REVIEW_TRANSITIONS.get(current, frozenset())


def _append_page_warning(page: DocumentPage, message: str) -> None:
    """Append a warning to a page's ``structural_metadata`` in place.

    Preserves any existing non-warning metadata so cleanup/structural
    signals from parsing are not lost when rendering later annotates the
    page.
    """
    existing = dict(page.structural_metadata or {})
    warnings = list(existing.get("warnings") or [])
    warnings.append(message)
    existing["warnings"] = warnings
    page.structural_metadata = existing


# ---------------------------------------------------------------------------


def _candidate_to_input(row: ExtractionCandidate) -> ReconciliationInput:
    """Project a persisted candidate into the CP29 reconciliation surface.

    Page numbers are parsed from the candidate's trusted ``sources_json``
    (never synthesized) so dedup signals reflect the actual cited locations.
    Candidates with no source fragments are reconciled by text alone (they
    cluster by fingerprint but cannot share a page span, so identical-text
    cases become ``flagged_review`` rather than silently deduped).
    """

    sources = row.sources_json
    if isinstance(sources, list):
        page_numbers = tuple(
            sorted(
                {
                    s["page_number"]
                    for s in sources
                    if isinstance(s, dict) and "page_number" in s
                }
            )
        )
    else:
        page_numbers = ()
    return ReconciliationInput(
        candidate_id=row.id,
        chunk_id=row.chunk_id,
        normalized_text=row.normalized_text,
        page_numbers=page_numbers,
        sources_json=sources if isinstance(sources, list) else None,
    )


class DocumentService:
    """State-machine and query service for document versions.

    Construct with an active :class:`AsyncSession`.  Audit events are
    flushed within the same transaction.
    """

    MAX_RETRIES = 5

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_version_or_raise(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> DocumentVersion:
        """Return a specific version of a document, scoped to *auth*'s org.

        Raises :class:`DocumentNotFoundError` if the document is not in the
        authenticated organization or the version does not exist.
        """
        result = await self._session.execute(
            select(DocumentVersion)
            .join(TenderDocument)
            .where(
                TenderDocument.id == document_id,
                TenderDocument.project_id == Project.id,
                Project.organization_id == auth.organization_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_number,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DocumentNotFoundError(
                f"document {document_id} v{version_number} "
                f"not found in org {auth.organization_id}"
            )
        return version

    async def normalize_requirement_constraints(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> list[ParsedConstraint]:
        """Parse the verbatim ``raw_source`` of a requirement into structured
        constraints and **persist** them (CP33 + CP34).

        Numeric constraints (CP33) and qualitative conditions (CP34) are
        parsed from the requirement's verbatim ``raw_source`` and written as
        :class:`RequirementConstraint` rows in a single transaction.  The
        requirement's ``normalization_state`` is derived from the worst
        constraint state, and the ``review_state`` is escalated to
        ``OCR_WARNING`` when the source is OCR-derived.

        Idempotent: existing constraints for the requirement are replaced
        on each call so reprocessing yields the same persisted state.

        Deterministic & reproducible: the same ``raw_source`` always yields
        the same output.  Every persisted constraint carries its verbatim
        ``raw_fragment``.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(Requirement).where(
                Requirement.id == requirement_id,
                Requirement.document_version_id == version.id,
            )
        )
        requirement = result.scalar_one_or_none()
        if requirement is None:
            raise DocumentNotFoundError(
                f"requirement {requirement_id} not found in "
                f"document {document_id} v{version_number}"
            )
        raw_source = requirement.raw_source or ""
        ocr_warning = bool(requirement.ocr_warning)

        # Clear existing constraints for idempotency — reprocessing the same
        # requirement should not accumulate stale rows.
        await self._session.execute(
            delete(RequirementConstraint).where(
                RequirementConstraint.requirement_id == requirement_id
            )
        )

        parsed: list[ParsedConstraint] = parse_constraint(
            raw_source, ocr_warning=ocr_warning
        )
        qualitative: list[QualitativeCondition] = parse_qualitative_conditions(
            raw_source, ocr_warning=ocr_warning
        )

        # Persist numeric constraints.
        for pc in parsed:
            row = RequirementConstraint(
                requirement_id=requirement_id,
                document_version_id=version.id,
                parameter=pc.parameter,
                operator=pc.operator,
                numeric_value=pc.numeric_value,
                lower_bound=pc.lower_bound,
                upper_bound=pc.upper_bound,
                unit=pc.unit,
                tolerance=pc.tolerance,
                qualitative_condition=None,
                normalization_state=pc.normalization_state,
                raw_fragment=pc.raw_fragment,
            )
            self._session.add(row)

        # Persist qualitative conditions.
        for qc in qualitative:
            row = RequirementConstraint(
                requirement_id=requirement_id,
                document_version_id=version.id,
                parameter=qc.parameter,
                operator=None,
                numeric_value=None,
                lower_bound=None,
                upper_bound=None,
                unit=None,
                tolerance=None,
                qualitative_condition=qc.condition,
                normalization_state=qc.normalization_state,
                raw_fragment=qc.raw_fragment,
            )
            self._session.add(row)

        # Determine the worst normalization state across all constraints.
        all_states = [c.normalization_state for c in parsed] + [
            c.normalization_state for c in qualitative
        ]
        if all_states:
            if ConstraintNormalizationState.NEEDS_REVIEW in all_states:
                worst = ConstraintNormalizationState.NEEDS_REVIEW
            elif ConstraintNormalizationState.PARTIAL in all_states:
                worst = ConstraintNormalizationState.PARTIAL
            else:
                worst = ConstraintNormalizationState.SAFE
        else:
            worst = ConstraintNormalizationState.UNNORMALIZED

        # Propagate OCR warning to the requirement's review state.
        if requirement.ocr_warning:
            requirement.review_state = RequirementReviewState.OCR_WARNING
        elif requirement.review_state == RequirementReviewState.UNREVIEWED:
            # Requirements with any constraint needing review stay unreviewed
            # for human attention.  Otherwise leave the existing state.
            if worst is ConstraintNormalizationState.NEEDS_REVIEW:
                requirement.review_state = RequirementReviewState.NEEDS_CLARIFICATION

        # Apply conservative normalized text (whitespace-only normalisation,
        # never a semantic rewrite).
        requirement.normalized_text = conservative_normalized_text(raw_source)

        # Record which normalisation ruleset version produced these constraints.
        # Stored via audit log so reprocessing with a new version is traceable.
        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.normalize_constraints",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=await self._project_id_for(version.document_id),
            metadata={
                "normalization_version": NORMALIZATION_VERSION,
                "ocr_warning": ocr_warning,
                "numeric_constraints": len(parsed),
                "qualitative_conditions": len(qualitative),
                "worst_normalization_state": worst.value if worst else None,
            },
        )

        await self._session.flush()
        return parsed

    # ------------------------------------------------------------------
    # Requirement queries (CP35)
    # ------------------------------------------------------------------

    async def list_requirements(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        review_state: RequirementReviewState | None = None,
        requirement_type: str | None = None,
        search: str | None = None,
        include_superseded: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Requirement]:
        """List requirements for a document version, tenant-scoped.

        Supports stable ordering (by ``display_order`` then ``created_at``
        descending), pagination (``limit``/``offset``), and optional filters
        on ``review_state`` and ``requirement_type``.  ``search`` performs a
        case-insensitive substring match on ``normalized_text`` or ``raw_source``.

        By default, superseded (soft-deleted) requirements are excluded.
        Pass ``include_superseded=True`` to include them.

        Authorized by organization (via the document version lookup) and
        project ownership.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)

        stmt = (
            select(Requirement)
            .where(Requirement.document_version_id == version.id)
            .order_by(
                Requirement.display_order.asc().nulls_last(),
                Requirement.created_at.desc(),
                Requirement.id,
            )
            .limit(limit)
            .offset(offset)
        )

        if not include_superseded:
            stmt = stmt.where(Requirement.superseded.is_(False))
        if review_state is not None:
            stmt = stmt.where(Requirement.review_state == review_state)
        if requirement_type is not None:
            stmt = stmt.where(Requirement.requirement_type == requirement_type)
        if search:
            # Case-insensitive substring search on both normalized and raw text.
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Requirement.normalized_text.like(pattern),
                    Requirement.raw_source.like(pattern),
                )
            )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_requirement(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> Requirement:
        """Fetch a single requirement with its constraints and sources,
        tenant-scoped.

        Raises :class:`DocumentNotFoundError` if the requirement does not
        exist in the authenticated organization's document version.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(Requirement)
            .options(
                selectinload(Requirement.constraints),
                selectinload(Requirement.sources),
                selectinload(Requirement.revisions),
            )
            .where(
                Requirement.id == requirement_id,
                Requirement.document_version_id == version.id,
            )
        )
        requirement = result.scalar_one_or_none()
        if requirement is None:
            raise DocumentNotFoundError(
                f"requirement {requirement_id} not found in "
                f"document {document_id} v{version_number}"
            )
        return requirement

    async def update_requirement_normalized_text(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        new_normalized_text: str,
        *,
        expected_updated_at: datetime | None = None,
        note: str | None = None,
    ) -> Requirement:
        """Edit a requirement's ``normalized_text`` with immutable revision
        history (CP38).

        - **Raw source is never touched.** Only ``normalized_text`` is modified;
          ``raw_source`` remains the verbatim extracted text for audit.
        - **Optimistic concurrency:** if ``expected_updated_at`` is provided and
          does not match the requirement's current ``updated_at``, raises
          :class:`ConcurrentEditError` with the current timestamp so the caller
          can refresh and retry.
        - **Revision history:** if ``new_normalized_text`` differs materially
          from the current value, a :class:`RequirementRevision` row is created
          capturing the *previous* text, the actor, the note, and an
          ``updated_at`` snapshot.  No revision row is created for no-ops.
        - **Audit trail:** a ``requirement.edit_normalized_text`` audit event is
          written with the actor, old/new text hash, and revision ID.
        - **Tenant isolation:** enforced via ``get_version_or_raise``.

        Returns the updated :class:`Requirement` with ``revisions`` eager-loaded.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)

        # Eager-load the requirement with its revision history.
        result = await self._session.execute(
            select(Requirement)
            .options(selectinload(Requirement.revisions))
            .where(
                Requirement.id == requirement_id,
                Requirement.document_version_id == version.id,
            )
        )
        requirement = result.scalar_one_or_none()
        if requirement is None:
            raise DocumentNotFoundError(
                f"requirement {requirement_id} not found in "
                f"document {document_id} v{version_number}"
            )

        # Optimistic concurrency check.
        if expected_updated_at is not None:
            if requirement.updated_at != expected_updated_at:
                raise ConcurrentEditError(requirement.updated_at)

        # Skip if the text is identical (no revision row needed).
        old_text = requirement.normalized_text
        if old_text == new_normalized_text:
            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="requirement.edit_normalized_text",
                entity_type="requirement",
                entity_id=requirement_id,
                project_id=await self._project_id_for(document_id),
                metadata={
                    "changed": False,
                    "reason": "text_unchanged",
                },
            )
            return requirement

        # Create an immutable revision capturing the PREVIOUS text.
        revision = RequirementRevision(
            requirement_id=requirement_id,
            previous_normalized_text=old_text,
            updated_at_at_edit=requirement.updated_at,
            actor_id=auth.actor_id,
            note=note,
        )
        self._session.add(revision)
        await self._session.flush()  # get revision.id before audit

        # Apply the edit.
        now = datetime.now(UTC)
        requirement.normalized_text = new_normalized_text
        requirement.updated_at = now
        await self._session.flush()

        # Write the audit event.
        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.edit_normalized_text",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=await self._project_id_for(document_id),
            metadata={
                "changed": True,
                "revision_id": str(revision.id),
                "old_text_sha256": hashlib.sha256(old_text.encode()).hexdigest(),
                "new_text_sha256": hashlib.sha256(
                    new_normalized_text.encode()
                ).hexdigest(),
                "note": note,
            },
        )

        return requirement

    async def get_requirement_revisions(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> list[RequirementRevision]:
        """Return the immutable revision history for a requirement,
        tenant-scoped.

        Raises :class:`DocumentNotFoundError` if the requirement does not
        exist in the authenticated organization's document version.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(RequirementRevision)
            .where(
                RequirementRevision.requirement_id == requirement_id,
                Requirement.id == requirement_id,
                Requirement.document_version_id == version.id,
            )
            .order_by(RequirementRevision.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Requirement structure: split, merge, supersede (CP39)
    # ------------------------------------------------------------------

    async def _requirement_or_raise(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> Requirement:
        """Fetch a single requirement, tenant-scoped, raising on missing.

        Eager-loads constraints, sources, revisions, relations, notes,
        and categories so the caller has the full picture.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(Requirement)
            .options(
                selectinload(Requirement.constraints),
                selectinload(Requirement.sources),
                selectinload(Requirement.revisions),
                selectinload(Requirement.relations),
                selectinload(Requirement.notes),
                selectinload(Requirement.categories),
            )
            .where(
                Requirement.id == requirement_id,
                Requirement.document_version_id == version.id,
            )
        )
        requirement = result.scalar_one_or_none()
        if requirement is None:
            raise DocumentNotFoundError(
                f"requirement {requirement_id} not found in "
                f"document {document_id} v{version_number}"
            )
        return requirement

    async def split_requirement(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        new_requirements: list[dict[str, Any]],
    ) -> list[Requirement]:
        """Split one requirement into multiple (CP39).

        Each entry in ``new_requirements`` must contain at least
        ``normalized_text`` and ``raw_source`` (the verbatim snippet this
        child is anchored on).  Optional fields: ``clause_number``,
        ``requirement_type``, ``confidence``.

        The original requirement is marked ``superseded`` and a
        ``SPLIT_INTO`` :class:`RequirementRelation` is created for each
        child, preserving provenance.
        """
        source_req = await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        if source_req.superseded:
            raise DocumentNotFoundError(
                f"requirement {requirement_id} has been superseded"
            )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        children: list[Requirement] = []
        relations: list[RequirementRelation] = []
        for spec in new_requirements:
            child = Requirement(
                document_version_id=version.id,
                promotion_key=f"split-{uuid.uuid4().hex[:12]}",
                requirement_type=spec.get("requirement_type") or source_req.requirement_type,
                normalized_text=spec["normalized_text"],
                raw_source=spec["raw_source"],
                uncertainty=spec.get("uncertainty") or source_req.uncertainty,
                clause_number=spec.get("clause_number") or source_req.clause_number,
                ocr_warning=bool(spec.get("ocr_warning", source_req.ocr_warning)),
                review_state=RequirementReviewState.UNREVIEWED,
            )
            self._session.add(child)
            await self._session.flush()
            children.append(child)
            relations.append(
                RequirementRelation(
                    source_requirement_id=source_req.id,
                    target_requirement_id=child.id,
                    relation_type=RequirementRelationType.SPLIT_INTO,
                    document_version_id=version.id,
                )
            )

        # Mark the original as superseded.
        source_req.superseded = True
        self._session.add_all(relations)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.split",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=project_id,
            metadata={
                "source_id": str(source_req.id),
                "child_ids": [str(c.id) for c in children],
                "child_count": len(children),
            },
        )

        return children

    async def merge_requirements(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_ids: list[uuid.UUID],
        merged_normalized_text: str,
        merged_raw_sources: list[str],
    ) -> Requirement:
        """Merge multiple requirements into one (CP39).

        Creates a new :class:`Requirement` whose ``raw_source`` lists all
        contributing fragments (joined with ``\\n---\\n``), marks all
        source requirements as ``superseded``, and creates a
        ``MERGED_INTO`` relation from each source to the target.
        """
        if len(requirement_ids) < 2:
            raise DocumentNotFoundError(
                "merge requires at least two requirement IDs"
            )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        # Fetch all source requirements.
        result = await self._session.execute(
            select(Requirement)
            .where(
                Requirement.id.in_(requirement_ids),
                Requirement.document_version_id == version.id,
            )
        )
        sources = result.scalars().all()
        if len(sources) != len(requirement_ids):
            found = {s.id for s in sources}
            missing = set(requirement_ids) - found
            raise DocumentNotFoundError(
                f"requirements not found: {missing}"
            )

        # Preserve all contributing source fragments.
        combined_raw = "\n---\n".join(merged_raw_sources)
        target = Requirement(
            document_version_id=version.id,
            promotion_key=f"merge-{uuid.uuid4().hex[:12]}",
            requirement_type=sources[0].requirement_type,
            normalized_text=merged_normalized_text,
            raw_source=combined_raw,
            uncertainty=sources[0].uncertainty,
            ocr_warning=any(s.ocr_warning for s in sources),
            review_state=RequirementReviewState.UNREVIEWED,
        )
        self._session.add(target)
        await self._session.flush()

        # Create MERGED_INTO relations and mark sources superseded.
        relations: list[RequirementRelation] = []
        for src in sources:
            src.superseded = True
            relations.append(
                RequirementRelation(
                    source_requirement_id=src.id,
                    target_requirement_id=target.id,
                    relation_type=RequirementRelationType.MERGED_INTO,
                    document_version_id=version.id,
                )
            )
        self._session.add_all(relations)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.merge",
            entity_type="requirement",
            entity_id=target.id,
            project_id=project_id,
            metadata={
                "source_ids": [str(s.id) for s in sources],
                "target_id": str(target.id),
            },
        )

        return target

    async def supersede_requirement(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        superseded_by: uuid.UUID | None = None,
        note: str | None = None,
    ) -> Requirement:
        """Mark a requirement as superseded (auditable soft-delete, CP39).

        If ``superseded_by`` is provided, a ``SUPERSEDES`` relation is
        created from this requirement to the replacement.  The requirement
        stays in the database for audit purposes but is excluded from
        default list/detail queries.
        """
        req = await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        req.superseded = True
        if superseded_by is not None:
            relation = RequirementRelation(
                source_requirement_id=req.id,
                target_requirement_id=superseded_by,
                relation_type=RequirementRelationType.SUPERSEDES,
                document_version_id=version.id,
            )
            self._session.add(relation)
            await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.supersede",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=project_id,
            metadata={
                "superseded_by": str(superseded_by) if superseded_by else None,
                "note": note,
            },
        )

        return req

    # ------------------------------------------------------------------
    # Requirement structure: mandatory, categories, ordering, notes (CP39)
    # ------------------------------------------------------------------

    async def set_requirement_mandatory(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        mandatory: bool | None,
    ) -> Requirement:
        """Set the tri-state mandatory flag on a requirement (CP39)."""
        req = await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        project_id = await self._project_id_for(document_id)
        req.mandatory = mandatory
        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.set_mandatory",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=project_id,
            metadata={"mandatory": mandatory},
        )
        return req

    async def assign_category(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> Requirement:
        """Assign a category to a requirement (CP39)."""
        await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        project_id = await self._project_id_for(document_id)

        # Verify the category belongs to the same project.
        result = await self._session.execute(
            select(Category).where(
                Category.id == category_id,
                Category.project_id == project_id,
            )
        )
        category = result.scalar_one_or_none()
        if category is None:
            raise DocumentNotFoundError(
                f"category {category_id} not found in project {project_id}"
            )

        # Use raw insert on the association table to avoid duplicate
        # relationship manipulation edge cases.
        await self._session.execute(
            insert(requirement_categories).values(
                requirement_id=requirement_id,
                category_id=category_id,
            )
        )
        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.assign_category",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=project_id,
            metadata={"category_id": str(category_id)},
        )
        # Reload and return the requirement with updated categories.
        return await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )

    async def unassign_category(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> Requirement:
        """Remove a category assignment from a requirement (CP39)."""
        await self._requirement_or_raise(auth, document_id, version_number, requirement_id)
        project_id = await self._project_id_for(document_id)

        await self._session.execute(
            delete(requirement_categories).where(
                requirement_categories.c.requirement_id == requirement_id,
                requirement_categories.c.category_id == category_id,
            )
        )
        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.unassign_category",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=project_id,
            metadata={"category_id": str(category_id)},
        )
        return await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )

    async def reorder_requirements(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        order: list[uuid.UUID],
    ) -> list[Requirement]:
        """Persist a new stable sort order for requirements (CP39).

        ``order`` is an explicit ordered list of requirement IDs.  Each
        requirement's ``display_order`` is set to its index in the list.
        Requirements not in the list are left unchanged (their
        ``display_order`` may be NULL, which sorts last).
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        # Verify all IDs exist in this version.
        result = await self._session.execute(
            select(Requirement.id).where(
                Requirement.id.in_(order),
                Requirement.document_version_id == version.id,
            )
        )
        found_ids = {r for r in result.scalars().all()}
        if len(found_ids) != len(order):
            missing = set(order) - found_ids
            raise DocumentNotFoundError(
                f"requirements not found for reordering: {missing}"
            )

        # Update display_order for each requirement.
        for idx, req_id in enumerate(order):
            await self._session.execute(
                update(Requirement)
                .where(
                    Requirement.id == req_id,
                    Requirement.document_version_id == version.id,
                )
                .values(display_order=idx)
            )

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.reorder",
            entity_type="requirement",
            entity_id=version.id,
            project_id=project_id,
            metadata={
                "ordered_ids": [str(r) for r in order],
                "version_id": str(version.id),
            },
        )
        # Reload reordered requirements.
        result = await self._session.execute(
            select(Requirement)
            .where(Requirement.id.in_(order))
            .order_by(Requirement.display_order.asc().nulls_last())
        )
        rows: list[Requirement] = result.scalars().all()  # type: ignore[assignment]
        return rows

    async def add_note(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        text: str,
    ) -> RequirementNote:
        """Add a reviewer note to a requirement (CP39)."""
        await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        note = RequirementNote(
            requirement_id=requirement_id,
            document_version_id=version.id,
            actor_id=auth.actor_id,
            text=text.strip(),
        )
        self._session.add(note)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.add_note",
            entity_type="requirement_note",
            entity_id=note.id,
            project_id=project_id,
            metadata={"requirement_id": str(requirement_id)},
        )
        return note

    async def get_requirement_notes(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> list[RequirementNote]:
        """List notes for a requirement, new-first, tenant-scoped (CP39)."""
        await self._requirement_or_raise(auth, document_id, version_number, requirement_id)
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(RequirementNote)
            .where(
                RequirementNote.requirement_id == requirement_id,
                RequirementNote.document_version_id == version.id,
            )
            .order_by(RequirementNote.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Review state machine (CP40)
    # ------------------------------------------------------------------

    async def transition_review_state(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        target_state: RequirementReviewState,
        *,
        override_uncertainty: bool = False,
    ) -> Requirement:
        """Transition a requirement's review state (CP40).

        Validates the transition against :data:`_ALLOWED_REVIEW_TRANSITIONS`.
        When transitioning to ``REVIEWED`` and the requirement's ``uncertainty``
        is not ``confirmed``, raises :class:`TransitionError` unless
        ``override_uncertainty`` is True (audited override).

        Every transition is logged as an audit event.
        """
        req = await self._requirement_or_raise(
            auth, document_id, version_number, requirement_id
        )
        current_state = req.review_state
        if current_state == target_state:
            return req  # idempotent no-op

        if not _is_valid_review_transition(current_state, target_state):
            raise TransitionError(
                f"Cannot transition review_state from "
                f"{current_state} to {target_state}"
            )

        # Guard: prevent marking as REVIEWED when uncertainty remains,
        # unless an explicit audited override is provided.
        if (
            target_state == RequirementReviewState.REVIEWED
            and req.uncertainty not in ("confirmed", None)
            and not override_uncertainty
        ):
            raise TransitionError(
                f"Cannot mark as REVIEWED while uncertainty is "
                f"{req.uncertainty!r}. Use override_uncertainty=true "
                f"with an auditable reason."
            )

        prev_state = req.review_state
        req.review_state = target_state
        req.updated_at = datetime.now(UTC)

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="requirement.transition_review_state",
            entity_type="requirement",
            entity_id=requirement_id,
            project_id=await self._project_id_for(document_id),
            metadata={
                "from_state": str(prev_state),
                "to_state": str(target_state),
                "uncertainty": req.uncertainty,
                "override_uncertainty": override_uncertainty,
            },
        )

        return req

    async def mark_reviewed(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
        *,
        override_uncertainty: bool = False,
    ) -> Requirement:
        """Mark a requirement as reviewed (CP40).

        Shorthand for transitioning to ``REVIEWED``. Raises
        :class:`TransitionError` if uncertainty remains and no override is given.
        """
        return await self.transition_review_state(
            auth,
            document_id,
            version_number,
            requirement_id,
            RequirementReviewState.REVIEWED,
            override_uncertainty=override_uncertainty,
        )

    async def reopen(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> Requirement:
        """Reopen a requirement (transition to UNREVIEWED, CP40)."""
        return await self.transition_review_state(
            auth,
            document_id,
            version_number,
            requirement_id,
            RequirementReviewState.UNREVIEWED,
        )

    async def escalate(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        requirement_id: uuid.UUID,
    ) -> Requirement:
        """Escalate a requirement to NEEDS_CLARIFICATION (CP40)."""
        return await self.transition_review_state(
            auth,
            document_id,
            version_number,
            requirement_id,
            RequirementReviewState.NEEDS_CLARIFICATION,
        )

    async def get_project_review_counts(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> dict[str, int]:
        """Compute real review counts for a document version (CP40).

        Returns a dict with keys: ``total``, ``unreviewed``, ``reviewed``,
        ``needs_clarification``, ``ocr_warning``, ``superseded``.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)

        # Use a single grouped query for all non-superseded states.
        result = await self._session.execute(
            select(
                Requirement.review_state,
                func.count(Requirement.id).label("count"),
            )
            .where(
                Requirement.document_version_id == version.id,
                Requirement.superseded.is_(False),
            )
            .group_by(Requirement.review_state)
        )
        counts = {row.review_state.value: row.count for row in result}

        total_result = await self._session.execute(
            select(
                func.count(Requirement.id).label("count"),
                func.count().filter(Requirement.superseded.is_(False)).label("active"),
            ).where(Requirement.document_version_id == version.id)
        )
        row = total_result.one()
        total = row.count
        active = row.active

        return {
            "total": total,
            "active": active,
            "unreviewed": counts.get("unreviewed", 0),
            "reviewed": counts.get("reviewed", 0),
            "needs_clarification": counts.get("needs_clarification", 0),
            "ocr_warning": counts.get("ocr_warning", 0),
            "superseded": (total - active),
        }

    # ------------------------------------------------------------------
    # Matrix projection (CP41)
    # ------------------------------------------------------------------

    async def get_matrix_rows(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> list[MatrixRow]:
        """Return the canonical Phase 1 matrix projection (CP41).

        Delegates to :func:`project_matrix_rows` so that the matrix UI
        and the XLSX exporter share one code path.
        """
        from tender_compliance_api.matrix.projection import (  # noqa: PLC0415
            project_matrix_rows,
        )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        return await project_matrix_rows(self._session, version.id)

    async def get_final_matrix_rows(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> list[FinalMatrixRow]:
        """Return the final (Phase 2) compliance matrix projection (CP59).

        Delegates to :func:`project_final_matrix_rows` so that both the
        final matrix UI and the CP60 exporter share one code path.
        """
        from tender_compliance_api.matrix.projection import (  # noqa: PLC0415
            project_final_matrix_rows,
        )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        return await project_final_matrix_rows(self._session, version.id)

    # ------------------------------------------------------------------
    # Final matrix export — XLSX, DOCX, PDF (CP60)
    # ------------------------------------------------------------------

    async def export_final_matrix(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        export_format: ExportFormat = ExportFormat.XLSX,
        vendor_response_template: bool = False,
        storage: ObjectStorageAdapter | None = None,
    ) -> ExportArtifact:
        """Generate a final matrix or blank vendor response and persist it.

        Final matrix exports use ``project_final_matrix_rows`` (CP59); the
        optional vendor response DOCX uses ``project_matrix_rows`` (CP41).
        The artifact bytes are written to object
        storage and an :class:`ExportArtifact` metadata row records the actor,
        format, requirement count, checksum, and timestamp.

        Each export creates a **new** ``ExportArtifact`` row — previous exports
        are never mutated (append-only history).

        If generation fails, an ``ExportArtifact`` with
        ``status=FAILED`` and ``error_message`` is recorded.
        """
        from tender_compliance_api.matrix.projection import (  # noqa: PLC0415
            project_final_matrix_rows,
            project_matrix_rows,
        )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        vendor_rows: list[MatrixRow] | None = None
        final_rows: list[FinalMatrixRow] | None = None
        if vendor_response_template:
            if export_format != ExportFormat.DOCX:
                raise ValueError("The vendor response template is available as DOCX only")
            vendor_rows = await project_matrix_rows(self._session, version.id)
        else:
            final_rows = await project_final_matrix_rows(self._session, version.id)
        rows = vendor_rows if vendor_rows is not None else final_rows
        assert rows is not None

        if storage is None:
            storage = _resolve_storage()

        integrity_report: dict[str, object] | None = None
        validation_status = "not_run"
        try:
            fmt = export_format.value
            if export_format == ExportFormat.XLSX:
                assert final_rows is not None
                from tender_compliance_api.export.final_xlsx import (  # noqa: PLC0415
                    build_final_matrix_workbook,
                    save_workbook_bytes,
                )

                wb, checksum = build_final_matrix_workbook(
                    final_rows,
                    project_name=str(document_id),
                    document_id=document_id,
                    version_number=version_number,
                    actor_id=auth.actor_id,
                    requirement_count=len(rows),
                )
                artifact_bytes = save_workbook_bytes(wb)
                content_type = (
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                )
                ext = "xlsx"
            elif export_format == ExportFormat.DOCX:
                if vendor_response_template:
                    assert vendor_rows is not None
                    from tender_compliance_api.export.vendor_response_docx import (  # noqa: PLC0415
                        build_vendor_response_docx,
                    )

                    artifact_bytes = build_vendor_response_docx(vendor_rows)
                else:
                    assert final_rows is not None
                    from tender_compliance_api.export.final_docx import (  # noqa: PLC0415
                        build_final_matrix_docx,
                    )

                    artifact_bytes = build_final_matrix_docx(
                        final_rows,
                        project_name=str(document_id),
                        document_id=document_id,
                        version_number=version_number,
                        actor_id=auth.actor_id,
                        requirement_count=len(rows),
                    )
                content_type = (
                    "application/vnd.openxmlformats-"
                    "officedocument.wordprocessingml.document"
                )
                ext = "docx"
            elif export_format == ExportFormat.PDF:
                assert final_rows is not None
                from tender_compliance_api.export.final_pdf import (  # noqa: PLC0415
                    build_final_matrix_pdf,
                )

                artifact_bytes = build_final_matrix_pdf(
                    final_rows,
                    project_name=str(document_id),
                    document_id=document_id,
                    version_number=version_number,
                    actor_id=auth.actor_id,
                    requirement_count=len(rows),
                )
                content_type = "application/pdf"
                ext = "pdf"
            else:
                raise ValueError(f"Unsupported export format: {export_format}")

            # Validate the actual serialized artifact before storing it. This
            # catches exporter clipping, dropped rows, and altered tender
            # wording rather than assuming the in-memory projection survived
            # rendering unchanged.
            from tender_compliance_api.export.expected import (  # noqa: PLC0415
                final_matrix_docx,
                final_matrix_pdf,
                final_matrix_xlsx,
                vendor_response_docx,
            )
            from tender_compliance_api.export.validation import (  # noqa: PLC0415
                validate_generated_requirement_cells,
            )
            presentation = None
            if vendor_response_template:
                from tender_compliance_api.export.vendor_response_presentation import (  # noqa: PLC0415
                    validate_vendor_response_presentation,
                )

                assert vendor_rows is not None
                presentation = validate_vendor_response_presentation(
                    vendor_rows, artifact_bytes
                )

            if vendor_response_template:
                assert vendor_rows is not None
                expected_headers, expected_cells = vendor_response_docx(vendor_rows)
            elif export_format == ExportFormat.XLSX:
                assert final_rows is not None
                expected_headers, expected_cells = final_matrix_xlsx(final_rows)
            elif export_format == ExportFormat.DOCX:
                assert final_rows is not None
                expected_headers, expected_cells = final_matrix_docx(final_rows)
            else:
                assert final_rows is not None
                expected_headers, expected_cells = final_matrix_pdf(final_rows)
            integrity = validate_generated_requirement_cells(
                expected_cells,
                artifact_bytes,
                export_format=fmt,  # type: ignore[arg-type]
                expected_headers=expected_headers,
            )
            integrity_report = {
                "artifact_integrity": integrity.status,
                "expected_rows": integrity.expected_rows,
                "actual_rows": integrity.actual_rows,
                "checked_columns": len(expected_headers),
                "checked_cells": len(expected_headers) * len(expected_cells),
                "issues": [
                    {"row_id": issue.row_id, "code": issue.code}
                    | ({"field": issue.field} if issue.field else {})
                    for issue in integrity.issues
                ],
            }
            if presentation is not None:
                integrity_report["presentation_validation"] = {
                    "status": presentation.status,
                    "checked_headings": presentation.checked_headings,
                    "checked_open_circle_markers": presentation.checked_open_circle_markers,
                    "issues": [
                        {"code": issue.code, "detail": issue.detail}
                        for issue in presentation.issues
                    ],
                }
            if integrity.status != "passed":
                validation_status = "failed"
                raise ValueError("generated sheet failed content validation")
            if presentation is not None and presentation.status != "passed":
                validation_status = "failed"
                raise ValueError("generated sheet failed presentation validation")

            extraction_report = await _extraction_window_coverage_report(
                self._session, version.id
            )
            integrity_report["window_processing"] = extraction_report

            source_report = await _source_quote_validation_report(
                self._session, rows, storage, version.id
            )
            integrity_report["source_validation"] = source_report
            validation_status = str(source_report["status"])
            if validation_status != "passed":
                raise ValueError("generated sheet requires source review")

            if extraction_report["status"] == "incomplete":
                validation_status = "needs_review"
                raise ValueError("extraction did not audit every source window")
            obligation_audit_status = extraction_report.get("obligation_audit_status")
            if obligation_audit_status in {"audit_failed", "potential_omissions"} or (
                get_settings().is_production
                and obligation_audit_status == "not_available"
            ):
                validation_status = "needs_review"
                raise ValueError("obligation coverage audit requires review")

            # Store the artifact bytes.
            storage_key = build_key(
                org_id=auth.organization_id,
                project_id=project_id,
                document_id=document_id,
                version=version_number,
                original_filename=(
                    f"vendor_response_v{version_number}.{ext}"
                    if vendor_response_template
                    else f"final_matrix_v{version_number}.{ext}"
                ),
            )
            obj_info = await storage.put(
                storage_key,
                artifact_bytes,
                content_type=content_type,
            )

            stored_obj = StoredObject(
                organization_id=auth.organization_id,
                project_id=project_id,
                document_id=document_id,
                storage_key=storage_key,
                filename=(
                    f"vendor_response_v{version_number}.{ext}"
                    if vendor_response_template
                    else f"final_matrix_v{version_number}.{ext}"
                ),
                content_type=obj_info.content_type,
                content_length=obj_info.content_length,
                checksum_sha256=obj_info.checksum_sha256,
                etag=obj_info.etag,
            )
            self._session.add(stored_obj)
            await self._session.flush()

            artifact = ExportArtifact(
                document_version_id=version.id,
                stored_object_id=stored_obj.id,
                actor_id=auth.actor_id,
                status=ExportStatus.COMPLETED,
                requirement_count=len(rows),
                workbook_sha256=obj_info.checksum_sha256,
                export_format=export_format,
                validation_status="passed",
                validation_report=integrity_report,
            )
            self._session.add(artifact)
            await self._session.flush()

            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action=(
                    "vendor_response.export"
                    if vendor_response_template
                    else "final_matrix.export"
                ),
                entity_type="export",
                entity_id=artifact.id,
                project_id=project_id,
                metadata={
                    "document_id": str(document_id),
                    "version_number": version_number,
                    "format": fmt,
                    "template": "vendor_response" if vendor_response_template else "final_matrix",
                    "requirement_count": len(rows),
                    "sha256": obj_info.checksum_sha256,
                    "storage_key": storage_key,
                    "artifact_integrity": integrity.status,
                    "validation_expected_rows": integrity.expected_rows,
                    "validation_actual_rows": integrity.actual_rows,
                },
            )

            return artifact

        except Exception as exc:
            artifact = ExportArtifact(
                document_version_id=version.id,
                stored_object_id=None,
                actor_id=auth.actor_id,
                status=ExportStatus.FAILED,
                error_message=EXPORT_FAILURE,
                requirement_count=len(rows),
                workbook_sha256="",
                export_format=export_format,
                validation_status=validation_status,
                validation_report=integrity_report,
            )
            self._session.add(artifact)
            await self._session.flush()

            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action=(
                    "vendor_response.export.failed"
                    if vendor_response_template
                    else "final_matrix.export.failed"
                ),
                entity_type="export",
                entity_id=artifact.id,
                project_id=project_id,
                metadata={
                    "document_id": str(document_id),
                    "version_number": version_number,
                    "format": export_format.value,
                    "error_type": type(exc).__name__,
                    "error_category": error_category(exc),
                    "validation_report": integrity_report,
                },
            )

            raise

    # ------------------------------------------------------------------
    # Matrix XLSX export (CP42)
    # ------------------------------------------------------------------

    async def export_matrix(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        storage: ObjectStorageAdapter | None = None,
    ) -> ExportArtifact:
        """Generate a matrix XLSX workbook and persist it (CP42).

        Uses the canonical matrix projection — no duplicated column logic.
        The workbook bytes are written to object storage, and an
        :class:`ExportArtifact` metadata row records the actor, requirement
        count, checksum, and timestamp.

        If workbook generation fails, an ``ExportArtifact`` with
        ``status=FAILED`` and ``error_message`` is recorded so the caller
        can surface the failure.

        Returns the :class:`ExportArtifact` row (committed by the caller or
        this method on success).
        """
        from tender_compliance_api.export.xlsx import (  # noqa: PLC0415
            build_matrix_workbook,
            save_matrix_workbook,
        )
        from tender_compliance_api.matrix.projection import (  # noqa: PLC0415
            project_matrix_rows,
        )

        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        # Fetch projection (also used to count rows).
        rows = await project_matrix_rows(self._session, version.id)

        if storage is None:
            storage = _resolve_storage()

        integrity_report: dict[str, object] | None = None
        validation_status = "not_run"
        try:
            wb, checksum = build_matrix_workbook(
                rows,
                project_name=str(document_id),
                document_id=document_id,
                version_number=version_number,
                actor_id=auth.actor_id,
                requirement_count=len(rows),
            )
            workbook_bytes = save_matrix_workbook(wb)

            from tender_compliance_api.export.expected import (  # noqa: PLC0415
                phase1_matrix_xlsx,
            )
            from tender_compliance_api.export.validation import (  # noqa: PLC0415
                validate_generated_requirement_cells,
            )

            expected_headers, expected_cells = phase1_matrix_xlsx(rows)
            integrity = validate_generated_requirement_cells(
                expected_cells,
                workbook_bytes,
                export_format="xlsx",
                expected_headers=expected_headers,
            )
            integrity_report = {
                "artifact_integrity": integrity.status,
                "expected_rows": integrity.expected_rows,
                "actual_rows": integrity.actual_rows,
                "checked_columns": len(expected_headers),
                "checked_cells": len(expected_headers) * len(rows),
                "issues": [
                    {"row_id": issue.row_id, "code": issue.code}
                    | ({"field": issue.field} if issue.field else {})
                    for issue in integrity.issues
                ],
            }
            if integrity.status != "passed":
                validation_status = "failed"
                raise ValueError("generated matrix failed content validation")

            extraction_report = await _extraction_window_coverage_report(
                self._session, version.id
            )
            integrity_report["window_processing"] = extraction_report

            source_report = await _source_quote_validation_report(
                self._session, rows, storage, version.id
            )
            integrity_report["source_validation"] = source_report
            validation_status = str(source_report["status"])
            if validation_status != "passed":
                raise ValueError("generated matrix requires source review")

            if extraction_report["status"] == "incomplete":
                validation_status = "needs_review"
                raise ValueError("extraction did not audit every source window")
            obligation_audit_status = extraction_report.get("obligation_audit_status")
            if obligation_audit_status in {"audit_failed", "potential_omissions"} or (
                get_settings().is_production
                and obligation_audit_status == "not_available"
            ):
                validation_status = "needs_review"
                raise ValueError("obligation coverage audit requires review")

            # Store the workbook bytes.
            storage_key = build_key(
                org_id=auth.organization_id,
                project_id=project_id,
                document_id=document_id,
                version=version_number,
                original_filename="tender_matrix_v1.xlsx",
            )
            obj_info = await storage.put(
                storage_key,
                workbook_bytes,
                content_type=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
            )

            # Create the StoredObject row.
            from tender_compliance_api.db.models import (  # noqa: PLC0415
                StoredObject,
            )

            stored_obj = StoredObject(
                organization_id=auth.organization_id,
                project_id=project_id,
                document_id=document_id,
                storage_key=storage_key,
                filename=f"tender_matrix_v{version_number}.xlsx",
                content_type=obj_info.content_type,
                content_length=obj_info.content_length,
                checksum_sha256=obj_info.checksum_sha256,
                etag=obj_info.etag,
            )
            self._session.add(stored_obj)
            await self._session.flush()

            artifact = ExportArtifact(
                document_version_id=version.id,
                stored_object_id=stored_obj.id,
                actor_id=auth.actor_id,
                status=ExportStatus.COMPLETED,
                requirement_count=len(rows),
                workbook_sha256=obj_info.checksum_sha256,
                validation_status="passed",
                validation_report=integrity_report,
            )
            self._session.add(artifact)
            await self._session.flush()

            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="matrix.export",
                entity_type="export",
                entity_id=artifact.id,
                project_id=project_id,
                metadata={
                    "document_id": str(document_id),
                    "version_number": version_number,
                    "requirement_count": len(rows),
                    "workbook_sha256": obj_info.checksum_sha256,
                    "storage_key": storage_key,
                    "artifact_integrity": "passed",
                    "validation_expected_rows": integrity.expected_rows,
                    "validation_actual_rows": integrity.actual_rows,
                },
            )

            return artifact

        except Exception as exc:
            # Record the failure as an audit trail entry.
            artifact = ExportArtifact(
                document_version_id=version.id,
                stored_object_id=None,
                actor_id=auth.actor_id,
                status=ExportStatus.FAILED,
                error_message=EXPORT_FAILURE,
                requirement_count=0,
                workbook_sha256="",
                validation_status=validation_status,
                validation_report=integrity_report,
            )
            self._session.add(artifact)
            await self._session.flush()

            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="matrix.export.failed",
                entity_type="export",
                entity_id=artifact.id,
                project_id=project_id,
                metadata={
                    "document_id": str(document_id),
                    "version_number": version_number,
                    "error_type": type(exc).__name__,
                    "error_category": error_category(exc),
                    "validation_report": integrity_report,
                },
            )

            raise

    async def get_exports(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> list[ExportArtifact]:
        """List export artifacts for a document version (CP42)."""
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(ExportArtifact)
            .where(ExportArtifact.document_version_id == version.id)
            .order_by(ExportArtifact.generated_at.desc())
        )
        return list(result.scalars().all())

    async def download_export(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        export_id: uuid.UUID,
        *,
        storage: ObjectStorageAdapter | None = None,
    ) -> bytes:
        """Download the workbook bytes for a completed export (CP42)."""
        version = await self.get_version_or_raise(auth, document_id, version_number)

        if storage is None:
            storage = _resolve_storage()

        result = await self._session.execute(
            select(ExportArtifact)
            .where(
                ExportArtifact.id == export_id,
                ExportArtifact.document_version_id == version.id,
            )
        )
        artifact = result.scalar_one_or_none()
        if artifact is None:
            raise DocumentNotFoundError(
                f"export {export_id} not found for document "
                f"{document_id} v{version_number}"
            )

        if artifact.status != ExportStatus.COMPLETED:
            raise DocumentNotFoundError(
                f"export {export_id} is not available "
                f"(status={artifact.status})"
            )

        if artifact.stored_object_id is None:
            raise DocumentNotFoundError(
                f"export {export_id} has no stored object"
            )

        # Fetch the StoredObject to get the storage_key.
        stored = await self._session.get(StoredObject, artifact.stored_object_id)
        if stored is None:
            raise DocumentNotFoundError(
                f"stored object for export {export_id} not found"
            )

        return await storage.get(stored.storage_key)

    # ------------------------------------------------------------------
    # Source viewer (CP36)
    # ------------------------------------------------------------------

    async def get_page(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        page_number: int,
    ) -> DocumentPage:
        """Fetch a single :class:`DocumentPage` by page number, tenant-scoped.

        Returns the page with its text, OCR confidence, and structural
        metadata.  Raises :class:`DocumentNotFoundError` if the page (or
        version, or document) is not in the authenticated organization.
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(DocumentPage).where(
                DocumentPage.document_version_id == version.id,
                DocumentPage.page_number == page_number,
            )
        )
        page = result.scalar_one_or_none()
        if page is None:
            raise DocumentNotFoundError(
                f"page {page_number} not found in "
                f"document {document_id} v{version_number}"
            )
        return page

    async def get_page_image_bytes(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        page_number: int,
        storage: ObjectStorageAdapter,
    ) -> tuple[bytes, str]:
        """Fetch the rendered PNG bytes for a page, tenant-scoped.

        Returns ``(image_bytes, content_type)``.  If the page has no
        rendered image yet (rendering was skipped/failed), raises
        :class:`DocumentNotFoundError` — the client should fall back to
        the text viewer.
        """
        page = await self.get_page(auth, document_id, version_number, page_number)
        if page.rendered_image_object_key is None:
            raise DocumentNotFoundError(
                f"page {page_number} of document {document_id} v{version_number} "
                f"has no rendered image available"
            )
        image_bytes = await storage.get(page.rendered_image_object_key)
        # Determine content type from the stored object metadata, falling
        # back to PNG (the renderer always produces PNG).
        content_type = "image/png"
        return image_bytes, content_type

    async def get_runs(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> list[ProcessingRun]:
        """Return all processing runs for a document version, newest first."""
        version = await self.get_version_or_raise(auth, document_id, version_number)
        result = await self._session.execute(
            select(ProcessingRun)
            .where(
                ProcessingRun.document_version_id == version.id,
            )
            .order_by(ProcessingRun.started_at.desc())
        )
        return list(result.scalars().all())

    async def list_project_versions(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> list[tuple[TenderDocument, DocumentVersion]]:
        """Return all (document, version) pairs for a project, ordered by
        document creation time then version number."""
        await self._project_exists(auth, project_id)
        result = await self._session.execute(
            select(TenderDocument, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .where(TenderDocument.project_id == project_id)
            .order_by(TenderDocument.created_at, DocumentVersion.version_number)
        )
        return list(result)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    async def transition_to(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        target: DocumentProcessingStatus,
    ) -> DocumentVersion:
        """Transition a version to *target*, guarding invalid transitions.

        Raises :class:`TransitionError` if the transition is not permitted
        by the state machine.  Audit events record every attempt.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )
        if not _is_valid_transition(version.processing_status, target):
            raise TransitionError(
                f"cannot transition {version.processing_status.value} "
                f"→ {target.value}"
            )

        old_status = version.processing_status
        version.processing_status = target

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.status_transition",
            entity_type="document_version",
            entity_id=version.id,
            project_id=await self._project_id_for(version.document_id),
            metadata={
                "document_id": str(version.document_id),
                "version_number": version.version_number,
                "from": old_status.value,
                "to": target.value,
            },
        )

        await self._session.flush()
        return version

    async def begin_run(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        stage: ProcessingStage,
        run_id: uuid.UUID | None = None,
    ) -> ProcessingRun:
        """Record that processing has begun for a stage on this version.

        Transitions the version to ``PROCESSING`` (from ``QUEUED``) if
        possible.  If already ``PROCESSING``, the run is still recorded.

        Returns the created :class:`ProcessingRun` (status=RUNNING).
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )

        # Attempt QUEUED → PROCESSING; if already PROCESSING this is a no-op.
        if version.processing_status == DocumentProcessingStatus.QUEUED:
            await self._set_processing(auth, version)

        run = ProcessingRun(
            document_version_id=version.id,
            run_id=run_id or uuid.uuid4(),
            attempt=await self._next_attempt(version.id, stage),
            stage=stage,
            status=RunStatus.RUNNING,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def complete_run(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        stage: ProcessingStage,
        run_id: uuid.UUID,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> ProcessingRun:
        """Mark a run as completed or failed, then update the version status.

        When *error_type* is None the run is COMPLETED.  When all expected
        stages succeed, the version transitions to PARSED.  When some stages
        succeed and others fail, the version transitions to PARTIAL.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )

        result = await self._session.execute(
            select(ProcessingRun).where(
                ProcessingRun.document_version_id == version.id,
                ProcessingRun.run_id == run_id,
                ProcessingRun.stage == stage,
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise DocumentNotFoundError(
                f"processing run {run_id} stage={stage.value} not found"
            )

        run.completed_at = _now()
        if error_type is None:
            run.status = RunStatus.COMPLETED
        else:
            run.status = RunStatus.FAILED
            run.error_type = error_type
            run.error_message = error_message

        # Determine the aggregate version status from all runs.
        await self._reconcile_version_status(auth, version)

        await self._session.flush()
        return run

    # ------------------------------------------------------------------
    # Enqueue (CP18)
    # ------------------------------------------------------------------

    async def enqueue_processing(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> uuid.UUID:
        """Transition a version from ``UPLOADED`` to ``QUEUED``.

        Returns a deterministic ``run_id`` (derived from version + stage)
        that the caller uses as the correlation ID for the queue job.
        The actual :class:`ProcessingRun` row is created by the worker
        when it calls :meth:`begin_run` with this ``run_id``.

        Idempotent: if the version is already ``QUEUED`` or ``PROCESSING``,
        the same deterministic ``run_id`` is returned (no transition).
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )

        run_id = make_job_id(str(version.id), ProcessingStage.PARSE.value)

        if version.processing_status == DocumentProcessingStatus.UPLOADED:
            await self.transition_to(
                auth, document_id, version_number,
                DocumentProcessingStatus.QUEUED,
            )
        elif version.processing_status in (
            DocumentProcessingStatus.QUEUED,
            DocumentProcessingStatus.PROCESSING,
        ):
            # Already enqueued/processing — return existing run_id.
            pass
        else:
            # Terminal state — should not enqueue.
            raise TransitionError(
                f"version {version.id} is {version.processing_status.value}, "
                "cannot enqueue for processing"
            )

        return run_id

    async def get_oem_version_or_raise(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> OemDocumentVersion:
        """Return a specific OEM document version, scoped to *auth*'s org.

        Raises :class:`DocumentNotFoundError` if the document is not in the
        authenticated organization or the version does not exist.
        """
        result = await self._session.execute(
            select(OemDocumentVersion)
            .join(OemDocument)
            .where(
                OemDocument.id == document_id,
                OemDocument.project_id == Project.id,
                Project.organization_id == auth.organization_id,
                OemDocumentVersion.document_id == document_id,
                OemDocumentVersion.version_number == version_number,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DocumentNotFoundError(
                f"oem document {document_id} v{version_number} "
                f"not found in org {auth.organization_id}"
            )
        return version

    async def enqueue_oem_processing(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> uuid.UUID:
        """Transition an OEM version from UPLOADED to QUEUED.

        Mirrors :meth:`enqueue_processing` but operates on
        :class:`OemDocumentVersion` instead of :class:`DocumentVersion`.
        Returns a deterministic run_id for the queue job.
        """
        version = await self.get_oem_version_or_raise(
            auth, document_id, version_number
        )

        run_id = make_job_id(
            str(version.id), ProcessingStage.PARSE.value,
            namespace="oem",
        )

        if version.processing_status == DocumentProcessingStatus.UPLOADED:
            # Transition UPLOADED → QUEUED
            from tender_compliance_api.document.service import _is_valid_transition
            if not _is_valid_transition(
                version.processing_status,
                DocumentProcessingStatus.QUEUED,
            ):
                raise TransitionError(
                    f"cannot transition {version.processing_status.value} "
                    f"→ {DocumentProcessingStatus.QUEUED.value}"
                )
            version.processing_status = DocumentProcessingStatus.QUEUED
            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="oem_document.status_transition",
                entity_type="oem_document_version",
                entity_id=version.id,
                project_id=await self._oem_project_id_for(version.document_id),
                metadata={
                    "document_id": str(version.document_id),
                    "version_number": version.version_number,
                    "from": version.processing_status.value,
                    "to": DocumentProcessingStatus.QUEUED.value,
                },
            )
            await self._session.flush()
        elif version.processing_status in (
            DocumentProcessingStatus.QUEUED,
            DocumentProcessingStatus.PROCESSING,
        ):
            pass
        else:
            raise TransitionError(
                f"oem version {version.id} is "
                f"{version.processing_status.value}, "
                "cannot enqueue for processing"
            )

        return run_id

    async def create_oem_text_segments(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        segments: list[tuple[int, str]],
    ) -> int:
        """Create searchable text segments for an OEM document version (CP50).

        Called during OEM document processing (PARSE/CLEANUP stage) to index
        page text into :class:`OemTextSegment` rows.  Each tuple is
        ``(page_number, text)``.  Segments replace any existing segments
        for the same version (idempotent reprocessing).

        Args:
            auth: Authenticated context (organization-scoped).
            document_id: The OEM document UUID.
            version_number: The version number.
            segments: List of ``(page_number, text)`` tuples.

        Returns:
            The number of ``OemTextSegment`` rows created.
        """
        version = await self.get_oem_version_or_raise(
            auth, document_id, version_number
        )

        # Idempotent: delete existing segments before recreating.
        await self._session.execute(
            delete(OemTextSegment).where(
                OemTextSegment.oem_document_version_id == version.id
            )
        )

        for page_number, text in segments:
            self._session.add(
                OemTextSegment(
                    oem_document_version_id=version.id,
                    page_number=page_number,
                    segment_index=0,
                    start_char=0,
                    end_char=len(text),
                    text=text,
                )
            )

        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="oem_document.segments_created",
            entity_type="oem_document_version",
            entity_id=version.id,
            project_id=await self._oem_project_id_for(version.document_id),
            metadata={
                "num_segments": len(segments),
                "total_chars": sum(len(t) for _, t in segments),
            },
        )

        return len(segments)

    async def requeue_version(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
    ) -> uuid.UUID:
        """Re-queue a ``FAILED``/``PARTIAL`` version for reprocessing (CP24).

        Transitions the version back to ``QUEUED`` (the state machine only
        permits this from ``FAILED``/``PARTIAL``) and returns the
        deterministic PARSE ``run_id`` the caller should enqueue with.

        *Idempotent*: if the version is already ``QUEUED``/``PROCESSING``,
        the existing ``run_id`` is returned without re-transitioning, so a
        retry action fired twice re-enqueues the same deterministic job
        (queue-side dedup handles the duplicate).

        Raises :class:`TransitionError` for ``PARSED`` (terminal — a
        completed version must not be silently reprocessed; retrying it is a
        new upload/version, not a re-run of the same source).  The immutable
        source bytes on the version are never modified or destroyed.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )
        current = version.processing_status

        if current == DocumentProcessingStatus.PARSED:
            raise TransitionError(
                f"version {version.id} is PARSED; cannot retry a completed version"
            )

        if current in (
            DocumentProcessingStatus.QUEUED,
            DocumentProcessingStatus.PROCESSING,
        ):
            # Already queued/processing — idempotent: reuse the run_id.
            pass
        else:
            # FAILED or PARTIAL -> QUEUED
            await self.transition_to(
                auth, document_id, version_number,
                DocumentProcessingStatus.QUEUED,
            )

        run_id = make_job_id(str(version.id), ProcessingStage.PARSE.value)

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="document.retry",
            entity_type="document_version",
            entity_id=version.id,
            project_id=await self._project_id_for(version.document_id),
            metadata={
                "document_id": str(version.document_id),
                "version_number": version.version_number,
                "from": current.value,
                "to": DocumentProcessingStatus.QUEUED.value,
                "run_id": str(run_id),
            },
        )

        return run_id

    async def log_llm_call(
        self,
        processing_run_id: uuid.UUID,
        call: LlmCallResult,
    ) -> ExtractionRun:
        """Persist an LLM-call audit record under a processing run (CP26).

        The record captures provider, model, prompt version, schema version,
        latency, token usage (provider-reported; ``None`` when unknown —
        never fabricated zero), cost (``None`` when pricing is unknown),
        and finish reason.  Anchoring on ``processing_run_id`` (a
        :class:`ProcessingRun`) ties every LLM call to a version + stage so
        operators can explain exactly which extraction configuration produced
        which candidates.
        """

        extraction_run = ExtractionRun(
            processing_run_id=processing_run_id,
            provider=call.provider,
            model=call.model,
            prompt_version=call.prompt_version,
            schema_version=call.schema_version,
            call_site=call.call_site,
            latency_ms=call.latency_ms,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            total_tokens=call.total_tokens,
            # cost_usd is None when pricing is unknown — never a fabricated 0.
            cost_usd=call.cost_usd,
            finish_reason=call.finish_reason,
            status=ExtractionRunStatus(call.status),
            error_message=(
                PROCESSING_STAGE_FAILURE
                if call.status == "failed" and call.error_message
                else None
            ),
        )
        self._session.add(extraction_run)
        await self._session.flush()
        return extraction_run

    async def get_run(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        run_id: uuid.UUID,
        stage: ProcessingStage,
    ) -> ProcessingRun:
        """Look up the :class:`ProcessingRun` for a stage/run, tenant-scoped.

        Used by the EXTRACT stage (CP28) to anchor LLM call audit records and
        candidate persistence to the correct run row.
        """

        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )
        result = await self._session.execute(
            select(ProcessingRun).where(
                ProcessingRun.document_version_id == version.id,
                ProcessingRun.run_id == run_id,
                ProcessingRun.stage == stage,
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise DocumentNotFoundError(
                f"processing run {run_id} stage={stage.value} not found"
            )
        return run

    async def store_extraction_candidates(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        run_id: uuid.UUID,
        candidates: list[CandidateRecord],
    ) -> int:
        """Persist EXTRACT-stage candidate records for this run (CP28).

        Writes one :class:`ExtractionCandidate` row per record (including
        ``is_valid=False`` rejections, so the invented-requirement rate stays
        measurable — CP29/CP30 promote only ``persistable=True`` rows).

        Returns the number of rows persisted.
        """

        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )
        run = await self.get_run(
            auth, document_id, version_number, run_id, ProcessingStage.EXTRACT
        )
        rows: list[ExtractionCandidate] = []
        for record in candidates:
            rows.append(
                ExtractionCandidate(
                    document_version_id=version.id,
                    processing_run_id=run.id,
                    chunk_id=record.chunk_id,
                    window_text=record.window_text,
                    sources_json=record.sources_json,
                    normalized_text=record.normalized_text,
                    raw_source=record.raw_source,
                    requirement_type=record.requirement_type,
                    uncertainty=record.uncertainty,
                    clause_number=record.clause_number,
                    group_hint=record.group_hint,
                    ocr_warning=record.ocr_warning,
                    is_valid=record.is_valid,
                    persistable=record.persistable,
                    rejection_reason=record.rejection_reason,
                    verbatim_validation=record.verbatim_validation,
                )
            )
        self._session.add_all(rows)
        await self._session.flush()
        return len(rows)

    async def reconcile_version_candidates(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        run_id: uuid.UUID | None = None,
    ) -> ReconciliationResult:
        """Deterministically reconcile a version's persisted candidates (CP29).

        Clusters the version's source-validated, persistable candidates by
        whitespace-normalized ``normalized_text`` (via
        :func:`tender_compliance_api.extraction.reconcile.reconcile`), then
        records each candidate's ``reconciliation_group_id`` / ``deduped`` /
        ``reconciliation_decision`` so CP30 promotes only non-deduped
        candidates, and writes a single audit row
        (:class:`~tender_compliance_api.db.models.ExtractionReconciliation`)
        capturing the aggregate counts.

        Reconciliation is idempotent and re-runnable (CP31 retry semantics):
        re-running yields the same group ids and decisions, and re-overwrites
        the per-candidate columns.
        """

        version = await self.get_version_or_raise(auth, document_id, version_number)

        # Only candidates that passed source validation can become requirements;
        # invalid (fabrication-guarded) rows are audit-only and left untouched.
        result = await self._session.execute(
            select(ExtractionCandidate)
            .where(
                ExtractionCandidate.document_version_id == version.id,
                ExtractionCandidate.is_valid.is_(True),
                ExtractionCandidate.persistable.is_(True),
            )
            .order_by(ExtractionCandidate.chunk_id, ExtractionCandidate.id)
        )
        rows = list(result.scalars().all())

        inputs = [_candidate_to_input(row) for row in rows]
        outcome = reconcile(inputs)

        # Map candidate_id -> (group_id, deduped, decision) for the update.
        decisions: dict[uuid.UUID, tuple[str, bool, str]] = {}
        for group in outcome.groups:
            for cid in group.kept:
                decisions[cid] = (group.group_id, False, group.decision)
            for cid in group.removed:
                decisions[cid] = (group.group_id, True, DECISION_DEDUP)

        # Bulk-update the per-candidate columns in stable (id) order.
        for row in sorted(rows, key=lambda r: r.id):
            group_id, deduped, decision = decisions.get(
                row.id, (row.reconciliation_group_id, row.deduped, DECISION_SINGLETON)
            )
            # SQLAlchemy 2.0 bulk UPDATE by primary key.
            await self._session.execute(
                update(ExtractionCandidate)
                .where(ExtractionCandidate.id == row.id)
                .values(
                    reconciliation_group_id=group_id,
                    deduped=deduped,
                    reconciliation_decision=decision,
                )
            )

        audit = ExtractionReconciliation(
            document_version_id=version.id,
            processing_run_id=run_id,
            summary=outcome.summary(),
        )
        self._session.add(audit)
        await self._session.flush()
        return outcome

    async def capture_extraction_diagnostics(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        run_id: uuid.UUID,
        outcome: ExtractionOutcome,
        reconciliation_outcome: ReconciliationResult | None = None,
        promoted_count: int = 0,
    ) -> ExtractionDiagnostics:
        """Persist one diagnostics row for an EXTRACT run (CP31).

        Answers "why did this document produce its requirement set" from a
        single auditable row: window/call/candidate counts, accepted vs
        rejected (fabrication-guarded) vs OCR-uncertain, deduped, promoted, plus
        the provider/model/prompt/schema versions taken from the audited LLM
        calls.  Rejection keys are short reason codes — never document bodies
        (AGENTS: do not log sensitive content, do not expose provider internals).

        The row is anchored to the EXTRACT ``ProcessingRun`` (unique), so it is
        written once per stage completion; reprocessing a version creates a new
        run → a new diagnostics row (history grows rather than overwrites).
        """

        version = await self.get_version_or_raise(auth, document_id, version_number)
        run = await self.get_run(
            auth, document_id, version_number, run_id, ProcessingStage.EXTRACT
        )

        summary = compute_diagnostics(
            outcome,
            promoted_count=promoted_count,
            reconciliation_outcome=reconciliation_outcome,
        )
        for window in outcome.window_results:
            self._session.add(
                ExtractionWindowAudit(
                    document_version_id=version.id,
                    processing_run_id=run.id,
                    chunk_id=window.chunk_id,
                    window_index=window.window_index,
                    call_status=window.call_status,
                    candidate_count=window.candidate_count,
                    ocr_warning=window.ocr_warning,
                    source_spans=window.source_spans,
                    coverage_status=window.coverage_status,
                    coverage_error_category=window.coverage_error_category,
                    potential_omissions=window.potential_omissions,
                )
            )
        diag = ExtractionDiagnostics(
            document_version_id=version.id,
            processing_run_id=run.id,
            total_windows=summary.total_windows,
            total_llm_calls=summary.total_llm_calls,
            total_candidates=summary.total_candidates,
            accepted_candidates=summary.accepted_candidates,
            rejected_candidates=summary.rejected_candidates,
            deduped_candidates=summary.deduped_candidates,
            promoted_requirements=summary.promoted_requirements,
            ocr_warning_candidates=summary.ocr_warning_candidates,
            provider=summary.provider,
            model=summary.model,
            prompt_version=summary.prompt_version,
            schema_version=summary.schema_version,
            rejection_breakdown=summary.rejection_breakdown,
            reconciliation_summary=summary.reconciliation_summary,
        )
        self._session.add(diag)
        await self._session.flush()
        return diag

    async def persist_requirements(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        *,
        run_id: uuid.UUID | None = None,
    ) -> tuple[int, int]:
        """Promote reconciled candidates to :class:`Requirement` rows (CP30).

        Promotes only candidates that survived CP25 source validation, CP29
        reconciliation, and are not deduped (``is_valid`` / ``persistable`` /
        ``deduped=False``).  Each promotion:
        - resolves EXACT/APPROXIMATE source anchors from the candidate's trusted
          ``sources_json`` (never fabricating offsets/pages),
        - assigns OCR_WARNING to recovered OCR-derived candidates, and
          NEEDS_CLARIFICATION to other strict-fallback recoveries; ordinary
          confirmed candidates start UNREVIEWED,
        - uses a stable ``promotion_key`` so reprocessing an unchanged version
          does not duplicate a row (``inserted`` count stays 0) and never
          overwrites a human-reviewed requirement.

        Returns ``(inserted, skipped)`` where ``skipped`` counts candidates
        whose requirement already existed (preserved with their existing
        review_state).
        """

        version = await self.get_version_or_raise(auth, document_id, version_number)

        rows = list((
            await self._session.execute(
                select(ExtractionCandidate)
                .where(
                    ExtractionCandidate.document_version_id == version.id,
                    ExtractionCandidate.is_valid.is_(True),
                    ExtractionCandidate.persistable.is_(True),
                    ExtractionCandidate.deduped.is_(False),
                )
                .order_by(ExtractionCandidate.chunk_id, ExtractionCandidate.id)
            )
        ).scalars().all())

        def source_order(candidate: ExtractionCandidate) -> tuple[int, int, str, str]:
            anchors = resolve_sources(candidate.raw_source, candidate.sources_json)
            if not anchors:
                return (2**31 - 1, 2**31 - 1, candidate.chunk_id, str(candidate.id))
            first = min(
                anchors,
                key=lambda anchor: (
                    anchor.page_number,
                    anchor.char_start if anchor.char_start is not None else 2**31 - 1,
                ),
            )
            return (
                first.page_number,
                first.char_start if first.char_start is not None else 2**31 - 1,
                candidate.chunk_id,
                str(candidate.id),
            )

        # Extraction windows can be processed concurrently and have
        # content-addressed chunk IDs, neither of which represents reading
        # order. Resolve the trusted source anchors and persist display order
        # in the order the tender presents the rows.
        rows.sort(key=source_order)

        # Keys already present for this version (reprocess idempotency).
        existing_keys = {
            key
            for (key,) in (
                await self._session.execute(
                    select(Requirement.promotion_key).where(
                        Requirement.document_version_id == version.id
                    )
                )
            ).all()
        }

        inserted = 0
        skipped = 0
        for display_order, row in enumerate(rows, start=1):
            inp: PromotionInput = to_promotion_input(row)
            recovered_by_fallback = row.verbatim_validation is not None
            if inp.promotion_key in existing_keys:
                # Unchanged requirement — preserve its existing review_state
                # (CP30.9: human-reviewed rows are never silently overwritten).
                skipped += 1
                continue

            requirement = Requirement(
                document_version_id=version.id,
                processing_run_id=run_id,
                promotion_key=inp.promotion_key,
                reconciliation_group_id=inp.reconciliation_group_id,
                requirement_type=inp.requirement_type,
                normalized_text=inp.normalized_text,
                raw_source=inp.raw_source,
                uncertainty=inp.uncertainty,
                clause_number=inp.clause_number,
                display_order=display_order,
                ocr_warning=inp.ocr_warning,
                review_state=(
                    RequirementReviewState.OCR_WARNING
                    if inp.ocr_warning
                    else RequirementReviewState.NEEDS_CLARIFICATION
                    if inp.uncertainty == "uncertain"
                    else RequirementReviewState.NEEDS_CLARIFICATION
                    if recovered_by_fallback
                    else RequirementReviewState.UNREVIEWED
                ),
            )
            self._session.add(requirement)
            await self._session.flush()

            sources: list[ResolvedSource] = resolve_sources(
                inp.raw_source,
                inp.sources_json,
                allow_exact=not recovered_by_fallback,
            )
            for src in sources:
                self._session.add(
                    RequirementSource(
                        requirement_id=requirement.id,
                        document_version_id=version.id,
                        page_number=src.page_number,
                        clause_number=src.clause_number,
                        char_start=src.char_start,
                        char_end=src.char_end,
                        bbox=src.bbox,
                        ocr_confidence=src.ocr_confidence,
                        location_type=src.location_type,
                        source_text=src.source_text,
                    )
                )
            await self._session.flush()
            existing_keys.add(inp.promotion_key)
            inserted += 1

        return inserted, skipped

    # ------------------------------------------------------------------
    # Page storage (CP19)
    # ------------------------------------------------------------------

    async def get_stored_object_key(
        self, auth: AuthContext, document_id: uuid.UUID, version_number: int
    ) -> str:
        """Return the ``storage_key`` for a version's stored object.

        Looks up the :class:`DocumentVersion` → :class:`StoredObject`
        chain, enforcing tenant isolation via *auth*.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )
        result = await self._session.execute(
            select(StoredObject).where(StoredObject.id == version.stored_object_id)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            raise DocumentNotFoundError(
                f"StoredObject {version.stored_object_id} not found"
            )
        return stored.storage_key

    async def store_pages(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        parse_result: ParseResult,
    ) -> list[DocumentPage]:
        """Persist parsed pages for a document version.

        Deletes any existing pages for this version (idempotent re-parse),
        then creates new :class:`DocumentPage` rows from *parse_result*.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )

        # Clear any previously parsed pages for this version (idempotent
        # re-parse; CP24 adds run-level idempotency on top of this).
        await self._session.execute(
            delete(DocumentPage).where(
                DocumentPage.document_version_id == version.id
            )
        )

        # CP23 structural cleanup is deterministic and version-scoped: a
        # header/footer line only qualifies as noise when it recurs across
        # multiple pages of the *same* version.  The raw ``extracted_text``
        # is never mutated — cleanup produces a separate ``cleaned_text``.
        cleanups = cleanup_pages(parse_result.pages)

        pages: list[DocumentPage] = []
        for idx, page_result in enumerate(parse_result.pages):
            cleanup = cleanups[idx]
            # Merge parse-time warnings with cleanup-recorded warnings.
            meta: dict[str, Any] = {}
            all_warnings = list(page_result.warnings or []) + list(cleanup.warnings)
            if all_warnings:
                meta["warnings"] = all_warnings
            if page_result.visual_verification_required:
                meta["visual_verification_required"] = True
            if cleanup.headers:
                meta["headers"] = list(cleanup.headers)
            if cleanup.footers:
                meta["footers"] = list(cleanup.footers)
            # Per-page extraction/parse errors stay visible (CP24): a failed
            # page must not silently disappear inside a "success".
            if page_result.error:
                meta["error"] = PAGE_TEXT_FAILURE

            page = DocumentPage(
                document_version_id=version.id,
                page_number=page_result.page_number,
                extracted_text=page_result.text if page_result.text else None,
                cleaned_text=cleanup.cleaned_text or None,
                ocr_needed=1 if page_result.ocr_needed else 0,
                structural_metadata=meta or None,
            )
            self._session.add(page)
            pages.append(page)

        await self._session.flush()
        return pages

    # ------------------------------------------------------------------
    # Rendered page assets (CP20)
    # ------------------------------------------------------------------

    async def store_rendered_pages(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        render_result: RenderResult,
        storage: ObjectStorageAdapter,
    ) -> list[DocumentPage]:
        """Persist rendered page images for a document version.

        For each successfully rendered page, stores the PNG in object
        storage under a deterministic, org/project-scoped key and records
        that key on the corresponding :class:`DocumentPage`
        (``rendered_image_object_key``).

        Pages that failed to render (empty image, ``error`` set) are left
        with a null image key and the failure is appended to the page's
        ``structural_metadata`` warnings.

        This is intentionally **best-effort and non-fatal**: a fatal
        render failure (``render_result.fatal_error``) or an individual
        storage error is recorded per-page without aborting the rest.  A
        null ``rendered_image_object_key`` simply means "no visual source
        for this page yet" — the text path from CP19 still stands.

        Source-version identity is preserved: keys are scoped to the
        version's org/project/document/version, and the rendered asset is
        a *derived* artifact (never treated as a new source version).
        """
        version = await self.get_version_or_raise(auth, document_id, version_number)
        project_id = await self._project_id_for(document_id)

        # Lazy import keeps a heavy storage/provider dependency out of the
        # core service import path.
        from tender_compliance_api.storage.keys import build_key

        result = await self._session.execute(
            select(DocumentPage).where(
                DocumentPage.document_version_id == version.id
            )
        )
        pages_by_num: dict[int, DocumentPage] = {
            p.page_number: p for p in result.scalars().all()
        }

        # Whole-document render failure: record the reason on every page
        # so reviewers can see the visual source is missing, then return.
        if render_result.fatal_error is not None:
            for existing_page in pages_by_num.values():
                _append_page_warning(
                    existing_page, PAGE_RENDER_FAILURE
                )
            await self._session.flush()
            return list(pages_by_num.values())

        for page_result in render_result.pages:
            page = pages_by_num.get(page_result.page_number)
            if page is None:
                continue

            if page_result.error is not None or not page_result.image_bytes:
                _append_page_warning(
                    page, PAGE_RENDER_FAILURE
                )
                continue

            try:
                key = build_key(
                    org_id=auth.organization_id,
                    project_id=project_id,
                    document_id=document_id,
                    version=version.version_number,
                    object_id=uuid.uuid5(
                        _RENDER_KEY_NAMESPACE,
                        f"{version.id}:{page_result.page_number}"
                        f":{render_result.render_dpi}",
                    ),
                    original_filename=f"page_{page_result.page_number}.png",
                )
                info = await storage.put(
                    key, page_result.image_bytes, page_result.content_type
                )
                page.rendered_image_object_key = info.key
            except Exception:  # noqa: BLE001 — best-effort, non-fatal
                _append_page_warning(page, PAGE_IMAGE_STORAGE_FAILURE)

        await self._session.flush()
        return list(pages_by_num.values())

    # ------------------------------------------------------------------
    # OCR (CP21)
    # ------------------------------------------------------------------

    async def apply_ocr(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        version_number: int,
        ocr_adapter: OcrAdapter,
        storage: ObjectStorageAdapter,
    ) -> list[DocumentPage]:
        """Run OCR on the version's pages flagged ``ocr_needed``.

        For each page whose ``ocr_needed`` is set, fetches the page's
        rendered image (``rendered_image_object_key`` from CP20) from
        object storage and runs *ocr_adapter* on it.  Recognized text is
        persisted on ``DocumentPage.extracted_text`` together with the
        adapter's confidence on ``ocr_confidence``; once a page has usable
        text ``ocr_needed`` is cleared.  The OCR provider name/version is
        recorded on the owning :class:`DocumentVersion`.

        Semantics / provenance:

        * ``ocr_needed`` stays ``True`` until the page has usable text.
          OCR that runs but produces no text therefore leaves the page
          flagged (so the version is correctly PARTIAL) and records a
          warning rather than silently presenting an empty page as
          "reviewed".
        * Provider-availability errors (e.g. a missing ``tesseract``
          binary) propagate to the per-page handler below as ordinary
          exceptions — they are recorded as a per-page warning and leave
          ``ocr_needed`` set (non-fatal, never fabricates text).
        * If a page has no rendered image (renderer not configured or
          rendering failed) it is skipped with a warning and keeps
          ``ocr_needed``.
        * When the adapter processes at least one page, ``version.ocr_name``
          and ``version.ocr_version`` are set from the adapter; otherwise
          they are left untouched (no OCR was actually used).
        * This is intentionally **best-effort and non-fatal**: a storage
          or OCR failure on one page never aborts the rest.
        """
        version = await self.get_version_or_raise(
            auth, document_id, version_number
        )

        result = await self._session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number)
        )
        pages = result.scalars().all()

        ocr_applied = False
        for page in pages:
            if not page.ocr_needed:
                continue

            key = page.rendered_image_object_key
            if not key:
                _append_page_warning(
                    page, "ocr skipped: no rendered image available"
                )
                continue

            try:
                image_bytes = await storage.get(key)
                ocr_result = await ocr_adapter.ocr(image_bytes)
            except Exception:  # noqa: BLE001 — per-page, non-fatal
                _append_page_warning(page, PAGE_OCR_FAILURE)
                ocr_applied = True
                continue

            if ocr_result.confidence is not None:
                page.ocr_confidence = ocr_result.confidence
            page.ocr_words = [
                {
                    "text": word.text,
                    "confidence": word.confidence,
                    "bbox": (
                        {
                            "x": word.bbox[0],
                            "y": word.bbox[1],
                            "width": word.bbox[2],
                            "height": word.bbox[3],
                        }
                        if word.bbox is not None
                        else None
                    ),
                }
                for word in ocr_result.words
            ] or None
            if ocr_result.text and ocr_result.text.strip():
                page.extracted_text = ocr_result.text
                page.ocr_needed = False
            else:
                # OCR ran but yielded no text — keep the page flagged for
                # review rather than presenting empty text as "certain".
                _append_page_warning(page, "ocr produced no recognizable text")
            ocr_applied = True

        if ocr_applied:
            version.ocr_name = ocr_adapter.name
            version.ocr_version = ocr_adapter.version

        await self._session.flush()
        return list(pages)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _project_id_for(self, document_id: uuid.UUID) -> uuid.UUID:
        """Return the project_id for a TenderDocument (no auth scoping —
        the caller has already verified ownership)."""
        result = await self._session.execute(
            select(TenderDocument.project_id).where(
                TenderDocument.id == document_id
            )
        )
        return result.scalar_one()

    async def _oem_project_id_for(self, document_id: uuid.UUID) -> uuid.UUID:
        """Return the project_id for an OemDocument (no auth scoping —
        the caller has already verified ownership)."""
        result = await self._session.execute(
            select(OemDocument.project_id).where(
                OemDocument.id == document_id
            )
        )
        return result.scalar_one()

    async def _project_exists(
        self, auth: AuthContext, project_id: uuid.UUID
    ) -> None:
        result = await self._session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise ProjectNotFoundError(
                f"project {project_id} not found in org {auth.organization_id}"
            )

    async def _set_processing(
        self, auth: AuthContext, version: DocumentVersion
    ) -> None:
        """QUEUED → PROCESSING transition."""
        try:
            version = await self.transition_to(
                auth,
                version.document_id,
                version.version_number,
                DocumentProcessingStatus.PROCESSING,
            )
        except TransitionError:
            # Already PROCESSING or another non-guardable state — proceed.
            pass

    async def _next_attempt(
        self, version_id: uuid.UUID, stage: ProcessingStage
    ) -> int:
        """Return the next attempt number for this version+stage."""
        result = await self._session.execute(
            select(func.max(ProcessingRun.attempt)).where(
                ProcessingRun.document_version_id == version_id,
                ProcessingRun.stage == stage,
            )
        )
        return (result.scalar_one() or 0) + 1

    async def _reconcile_version_status(
        self, auth: AuthContext, version: DocumentVersion
    ) -> None:
        """Recompute the version's ``processing_status`` from its runs.

        Rules (conservative — AGENTS.md: never promote partial to READY):

        * All expected stages completed → PARSED
        * Some stages completed, some permanently failed → PARTIAL
        * All expected stages permanently failed → FAILED
        * Any stage still running → stay PROCESSING
        * Any stage not yet attempted + others failed retryable → QUEUED
        * No runs at all → UPLOADED (no change)

        Expected stages: ``{PARSE, OCR, CLEANUP, EXTRACT}``.
        """
        result = await self._session.execute(
            select(ProcessingRun).where(
                ProcessingRun.document_version_id == version.id,
            )
        )
        runs = list(result.scalars().all())
        if not runs:
            return  # stays UPLOADED

        stage_results: dict[ProcessingStage, list[RunStatus]] = {}
        for run in runs:
            stage_results.setdefault(run.stage, []).append(run.status)

        expected_stages = {
            ProcessingStage.PARSE,
            ProcessingStage.OCR,
            ProcessingStage.CLEANUP,
            ProcessingStage.EXTRACT,
        }

        has_running = False
        completed_stages: set[ProcessingStage] = set()
        permanently_failed_stages: set[ProcessingStage] = set()
        retryable_failed_stages: set[ProcessingStage] = set()
        unattempted_stages: set[ProcessingStage] = set()

        for stage in expected_stages:
            statuses = stage_results.get(stage, [])
            if not statuses:
                unattempted_stages.add(stage)
            elif RunStatus.RUNNING in statuses:
                has_running = True
            elif RunStatus.COMPLETED in statuses:
                completed_stages.add(stage)
            else:
                # All runs for this stage are FAILED
                attempts = len([s for s in statuses if s == RunStatus.FAILED])
                if attempts >= self.MAX_RETRIES:
                    permanently_failed_stages.add(stage)
                else:
                    retryable_failed_stages.add(stage)

        # If any stage is still running, stay PROCESSING.
        if has_running:
            return

        total = len(expected_stages)

        # All expected stages completed → PARSED
        if len(completed_stages) == total:
            # If any pages still need OCR (native text untrustworthy),
            # the version is PARTIAL — OCR (CP21) hasn't filled the gap.
            ocr_count_result = await self._session.execute(
                select(func.count())
                .where(
                    DocumentPage.document_version_id == version.id,
                    DocumentPage.ocr_needed == 1,
                )
            )
            ocr_needed_count = ocr_count_result.scalar() or 0
            if ocr_needed_count > 0:
                await self._safe_transition(
                    auth, version, DocumentProcessingStatus.PARTIAL
                )
            else:
                await self._safe_transition(
                    auth, version, DocumentProcessingStatus.PARSED
                )
        # All expected stages permanently failed → FAILED
        elif len(permanently_failed_stages) == total:
            await self._safe_transition(
                auth, version, DocumentProcessingStatus.FAILED
            )
        # Some completed, some permanently failed → PARTIAL
        elif completed_stages and permanently_failed_stages:
            await self._safe_transition(
                auth, version, DocumentProcessingStatus.PARTIAL
            )
        # Some completed, but some still unattempted → stay PROCESSING
        # (more stages need to run before we can decide)
        elif completed_stages and unattempted_stages:
            return
        # Some permanently failed + some unattempted, none completed → QUEUED
        elif (permanently_failed_stages or retryable_failed_stages) and unattempted_stages:
            if version.processing_status in (
                DocumentProcessingStatus.PROCESSING,
                DocumentProcessingStatus.QUEUED,
            ):
                await self._safe_transition(
                    auth, version, DocumentProcessingStatus.QUEUED
                )
        # Some failed (retryable), none completed yet, none unattempted → QUEUED
        elif retryable_failed_stages and not permanently_failed_stages:
            if version.processing_status == DocumentProcessingStatus.PROCESSING:
                await self._safe_transition(
                    auth, version, DocumentProcessingStatus.QUEUED
                )

    async def _safe_transition(
        self,
        auth: AuthContext,
        version: DocumentVersion,
        target: DocumentProcessingStatus,
    ) -> None:
        """Attempt a transition without raising — used during reconciliation
        when the current state may already be the target or a terminal state."""
        if version.processing_status == target:
            return
        if _is_valid_transition(version.processing_status, target):
            version.processing_status = target
            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="document.status_transition",
                entity_type="document_version",
                entity_id=version.id,
                project_id=await self._project_id_for(version.document_id),
                metadata={
                    "document_id": str(version.document_id),
                    "version_number": version.version_number,
                    "from": version.processing_status.value,
                    "to": target.value,
                    "reason": "reconciliation",
                },
            )
        await self._session.flush()


def _now() -> datetime:
    """Return the current UTC timestamp.

    Wrapped so tests can monkeypatch if needed.
    """
    from datetime import UTC

    return datetime.now(UTC)
