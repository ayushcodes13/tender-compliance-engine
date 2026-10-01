"""Job processing business logic (CP18, CP19).

``JobProcessor`` transforms a :class:`QueuedJob` into concrete
``ProcessingRun`` rows and ``DocumentVersion`` state transitions.
It is deliberately separated from the polling loop so it can be
unit-tested without Redis.

For CP19 the PARSE stage performs real PDF text extraction via a
:class:`ParserAdapter`, storing one :class:`DocumentPage` per page.
The OCR, CLEANUP, and EXTRACT stages remain placeholders — they are
completed as no-ops until their respective checkpoints implement
real behavior.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    ProcessingRun,
    ProcessingStage,
    RunStatus,
)
from tender_compliance_api.document import DocumentNotFoundError, DocumentService
from tender_compliance_api.parser.adapter import ParserAdapter
from tender_compliance_api.queue import QueuedJob
from tender_compliance_api.storage.adapter import ObjectStorageAdapter

logger = logging.getLogger(__name__)

#: The system worker's actor ID — a fixed UUID for audit trails.
WORKER_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000100")

#: OCR identity recorded on the version (configured for CP19, actual OCR
#: engine will be invoked in CP21).
OCR_NAME = "tesseract"
OCR_VERSION = "5.4"

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
            Defaults to :class:`PypdfParserAdapter`.
        storage: :class:`ObjectStorageAdapter` used to read the original
            document bytes from storage.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        parser: ParserAdapter | None = None,
        storage: ObjectStorageAdapter | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._parser = parser or _default_parser()
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
                raise ValueError(
                    f"DocumentVersion {version_id} not found in org {org_id}"
                )

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
                        # PARSE failed — record parser identity and stop.
                        version.parser_name = self._parser.name
                        version.parser_version = self._parser.version
                        version.ocr_name = OCR_NAME
                        version.ocr_version = OCR_VERSION
                        await session.commit()
                        return
                else:
                    # Placeholder stages (CP21+): complete as no-op.
                    await svc.complete_run(
                        auth,
                        document_id=version.document_id,
                        version_number=version.version_number,
                        stage=stage,
                        run_id=run_id,
                        error_type=None,
                        error_message=None,
                    )

            # Record parser identity on the version.
            version.parser_name = self._parser.name
            version.parser_version = self._parser.version
            version.ocr_name = OCR_NAME
            version.ocr_version = OCR_VERSION

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

        # Parse the PDF.
        parse_result = await self._parser.parse(data, version.mime_type)

        if parse_result.fatal_error is not None:
            # Fatal parse error — mark the run as failed.
            await svc.complete_run(
                auth,
                document_id=version.document_id,
                version_number=version.version_number,
                stage=ProcessingStage.PARSE,
                run_id=run_id,
                error_type="ParseError",
                error_message=parse_result.fatal_error,
            )
            return False

        # Store parsed pages.
        await svc.store_pages(
            auth,
            document_id=version.document_id,
            version_number=version.version_number,
            parse_result=parse_result,
        )

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

    async def _get_version(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> DocumentVersion | None:
        result = await session.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        return result.scalar_one_or_none()

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
    """Return the default production parser (pypdf)."""
    from tender_compliance_api.parser.pypdf import PypdfParserAdapter

    return PypdfParserAdapter()


def _default_storage() -> ObjectStorageAdapter:
    """Return the default production storage adapter (S3 or fake)."""
    from tender_compliance_api.config import get_settings

    s = get_settings()
    if not s.object_storage_endpoint:
        from tender_compliance_api.storage.fake import FakeStorageAdapter

        return FakeStorageAdapter()
    from tender_compliance_api.storage.s3 import S3StorageAdapter

    return S3StorageAdapter(
        endpoint_url=s.object_storage_endpoint,
        access_key=s.object_storage_access_key,
        secret_key=s.object_storage_secret_key,
        bucket=s.object_storage_bucket,
        region=s.object_storage_region,
    )


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
            error_message=str(error)[:1024],
        )
        await session.commit()
