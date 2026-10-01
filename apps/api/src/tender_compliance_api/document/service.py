"""Document domain: processing state machine and version persistence (CP17).

Business rules for document-version processing states live here — not in routes.
Every method takes a verified :class:`AuthContext` so tenant isolation is
enforced in one place, consistent with :mod:`tender_compliance_api.project`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    ExtractionCandidate,
    ExtractionDiagnostics,
    ExtractionReconciliation,
    ExtractionRun,
    ExtractionRunStatus,
    ProcessingRun,
    ProcessingStage,
    Project,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    RunStatus,
    StoredObject,
    TenderDocument,
)
from tender_compliance_api.extraction.adapter import LlmCallResult
from tender_compliance_api.extraction.constraint_parser import (
    ParsedConstraint,
    parse_constraint,
)
from tender_compliance_api.extraction.diagnostics import compute_diagnostics
from tender_compliance_api.extraction.extractor import CandidateRecord, ExtractionOutcome
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
from tender_compliance_api.parser.cleanup import cleanup_pages
from tender_compliance_api.project.service import ProjectNotFoundError
from tender_compliance_api.queue import make_job_id

if TYPE_CHECKING:
    from tender_compliance_api.ocr.adapter import OcrAdapter
    from tender_compliance_api.parser.adapter import ParseResult
    from tender_compliance_api.renderer.adapter import RenderResult
    from tender_compliance_api.storage.adapter import ObjectStorageAdapter


#: Deterministic namespace for rendered-image object keys, so that
#: re-rendering the same version/page/DPI overwrites the same storage key
#: instead of producing duplicate blobs (CP20 idempotency).
_RENDER_KEY_NAMESPACE = uuid.UUID("00000000-0000-5000-8000-000000000042")


class DocumentNotFoundError(Exception):
    """Raised when a TenderDocument or DocumentVersion is not found or not owned."""


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
        numeric constraints (CP33).

        The requirement is loaded tenant-scoped (via the document version) so the
        caller cannot read another organization's data.  Returns zero or more
        :class:`ParsedConstraint` records, each anchored to the requirement's
        verbatim ``raw_source``.  This is a read-only parse: persistence of the
        resulting constraints (and their normalization-state transitions) is the
        responsibility of CP34.

        Deterministic & reproducible: the same ``raw_source`` always yields the
        same output.
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
        return parse_constraint(
            raw_source,
            ocr_warning=bool(requirement.ocr_warning),
        )

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
            error_message=call.error_message,
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
        - assigns review_state UNREVIEWED (Phase 1; OCR_WARNING is reserved for
          CP35 reviewer assignment — OCR-derived candidates are UNCERTAIN and
          therefore non-persistable since CP28),
        - uses a stable ``promotion_key`` so reprocessing an unchanged version
          does not duplicate a row (``inserted`` count stays 0) and never
          overwrites a human-reviewed requirement.

        Returns ``(inserted, skipped)`` where ``skipped`` counts candidates
        whose requirement already existed (preserved with their existing
        review_state).
        """

        version = await self.get_version_or_raise(auth, document_id, version_number)

        rows = (
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
        ).scalars().all()

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
        for row in rows:
            inp: PromotionInput = to_promotion_input(row)
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
                ocr_warning=inp.ocr_warning,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            self._session.add(requirement)
            await self._session.flush()

            sources: list[ResolvedSource] = resolve_sources(
                inp.raw_source, inp.sources_json
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
            if cleanup.headers:
                meta["headers"] = list(cleanup.headers)
            if cleanup.footers:
                meta["footers"] = list(cleanup.footers)
            # Per-page extraction/parse errors stay visible (CP24): a failed
            # page must not silently disappear inside a "success".
            if page_result.error:
                meta["error"] = page_result.error

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
                    existing_page, f"render failed: {render_result.fatal_error}"
                )
            await self._session.flush()
            return list(pages_by_num.values())

        for page_result in render_result.pages:
            page = pages_by_num.get(page_result.page_number)
            if page is None:
                continue

            if page_result.error is not None or not page_result.image_bytes:
                _append_page_warning(
                    page, f"render failed: {page_result.error}"
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
            except Exception as exc:  # noqa: BLE001 — best-effort, non-fatal
                _append_page_warning(page, f"image store failed: {exc!r}")

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
            except Exception as exc:  # noqa: BLE001 — per-page, non-fatal
                _append_page_warning(page, f"ocr failed: {exc!r}")
                ocr_applied = True
                continue

            if ocr_result.confidence is not None:
                page.ocr_confidence = ocr_result.confidence
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
