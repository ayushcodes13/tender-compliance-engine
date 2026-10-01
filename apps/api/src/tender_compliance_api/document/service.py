"""Document domain: processing state machine and version persistence (CP17).

Business rules for document-version processing states live here — not in routes.
Every method takes a verified :class:`AuthContext` so tenant isolation is
enforced in one place, consistent with :mod:`tender_compliance_api.project`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    ProcessingRun,
    ProcessingStage,
    Project,
    RunStatus,
    TenderDocument,
)
from tender_compliance_api.project.service import ProjectNotFoundError


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
