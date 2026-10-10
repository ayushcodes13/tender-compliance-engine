"""Worker polling loop and CLI entry point (CP18).

The :class:`Worker` dequeues jobs from a :class:`QueueAdapter`,
processes them via :class:`~tender_compliance_worker.processor.JobProcessor`,
and handles retries/acknowledgements.

Run with::

    python -m tender_compliance_worker --max-concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import cast

from tender_compliance_api.config import get_settings
from tender_compliance_api.db.session import init_engine
from tender_compliance_api.extraction.adapter import LlmAdapter
from tender_compliance_api.extraction.dev_adapter import DevLlmAdapter
from tender_compliance_api.extraction.openai_adapter import OpenAiLlmAdapter
from tender_compliance_api.ocr.adapter import OcrAdapter
from tender_compliance_api.ocr.tesseract import TesseractOcrAdapter
from tender_compliance_api.parser import (
    CompositeParserAdapter,
    DocxParserAdapter,
    PyMuPDFParserAdapter,
)
from tender_compliance_api.parser.adapter import ParserAdapter
from tender_compliance_api.queue import (
    DEFAULT_QUEUE,
    FakeQueueAdapter,
    QueueAdapter,
    QueuedJob,
    RedisQueueAdapter,
)
from tender_compliance_api.renderer import PymupdfRendererAdapter
from tender_compliance_api.renderer.adapter import RendererAdapter
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.factory import create_storage_adapter
from tender_compliance_worker.processor import JobProcessor, SessionFactory

logger = logging.getLogger(__name__)


class Worker:
    """Background worker that polls a queue and processes jobs.

    Args:
        queue: The queue adapter (RedisQueueAdapter or FakeQueueAdapter).
        session_factory: Callable that returns an async context manager
            yielding an ``AsyncSession``.
        processor: The :class:`JobProcessor` that handles job logic.
        max_concurrency: Maximum simultaneous jobs to process.
        visibility_timeout: Seconds before a claimed job is re-delivered.
    """

    def __init__(
        self,
        queue: QueueAdapter,
        session_factory: SessionFactory,
        processor: JobProcessor | None = None,
        *,
        max_concurrency: int = 4,
        visibility_timeout: int = 300,
    ) -> None:
        self._queue = queue
        self._session_factory = session_factory
        self._processor = processor or JobProcessor(session_factory)
        self._max_concurrency = max_concurrency
        self._visibility_timeout = visibility_timeout
        self._running = False
        self._queue_name = DEFAULT_QUEUE

    async def run_once(self, queue_name: str = DEFAULT_QUEUE) -> int:
        """Process one polling cycle.

        Dequeue up to ``max_concurrency`` jobs, process them concurrently,
        and acknowledge each.  Returns the number of jobs processed.
        """
        jobs: list[QueuedJob] = []
        while len(jobs) < self._max_concurrency:
            job = await self._queue.dequeue(
                queue_name, self._visibility_timeout
            )
            if job is None:
                break
            jobs.append(job)

        if not jobs:
            return 0

        results = await asyncio.gather(
            *(self._processor.process(j) for j in jobs),
            return_exceptions=True,
        )

        for job, result in zip(jobs, results, strict=True):
            if isinstance(result, Exception):
                logger.error(
                    "Job %s failed: %s — re-enqueueing",
                    job.job_id, result,
                )
                await self._handle_failure(job, result)
            else:
                await self._queue.acknowledge(self._queue_name, job.job_id)

        return len(jobs)

    async def _handle_failure(self, job: QueuedJob, error: Exception) -> None:
        """Release or permanently fail a job that errored during processing."""
        from tender_compliance_worker.processor import record_failure

        attempt = int(str(job.payload.get("attempt", 1)))
        if attempt >= 5:
            logger.error(
                "Job %s permanently failed after %s attempts",
                job.job_id, attempt,
            )
            await record_failure(self._session_factory, job, error)
            await self._queue.acknowledge(self._queue_name, job.job_id)
        else:
            delay = min(2 ** attempt, 60)
            await self._queue.release(self._queue_name, job.job_id, delay=delay)
            logger.info(
                "Job %s re-enqueued (attempt %s, delay %ss)",
                job.job_id, attempt, delay,
            )

    async def run(self, queue_name: str = DEFAULT_QUEUE) -> None:
        """Run the worker loop until cancelled."""
        self._running = True
        self._queue_name = queue_name
        logger.info(
            "Worker started (concurrency=%d, queue=%s)",
            self._max_concurrency, queue_name,
        )
        heartbeat_task: asyncio.Task[None] | None = None
        if isinstance(self._queue, RedisQueueAdapter):
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            while self._running:
                try:
                    await self.run_once(queue_name)
                except KeyboardInterrupt:
                    break
                except Exception:  # noqa: BLE001
                    logger.exception("Worker error in run loop")
                await asyncio.sleep(1)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self) -> None:
        """Renew the processing-worker lease independently of job duration."""
        assert isinstance(self._queue, RedisQueueAdapter)
        while self._running:
            try:
                await self._queue.heartbeat_worker()
            except Exception:  # noqa: BLE001
                logger.exception("Could not publish worker heartbeat")
            await asyncio.sleep(3)

    def stop(self) -> None:
        self._running = False


def create_worker(
    *,
    queue: QueueAdapter | None = None,
    parser: ParserAdapter | None = None,
    renderer: RendererAdapter | None = None,
    storage: ObjectStorageAdapter | None = None,
    ocr: OcrAdapter | None = None,
    llm: LlmAdapter | None = None,
    max_concurrency: int | None = None,
) -> Worker:
    """Create a :class:`Worker` with production defaults.

    Production validates its durable database, Redis queue, object storage,
    model credential, and pilot auth mode before constructing the worker.
    Development may still fall back to :class:`FakeQueueAdapter`.  When
    ``OPENAI_API_KEY`` is absent in development, a deterministic
    :class:`DevLlmAdapter` is used so the full extraction pipeline is
    exercisable locally without network access.  Defaults:
    :class:`CompositeParserAdapter` dispatching to
    :class:`PyMuPDFParserAdapter` (PDF, CP19) and :class:`DocxParserAdapter`
    (DOCX, CP22), :class:`PymupdfRendererAdapter` (CP20), and
    :class:`TesseractOcrAdapter` (CP21).  The LLM extraction default is
    :class:`OpenAiLlmAdapter` (``gpt-4o`` per ``docs/review.md``).
    """
    settings = get_settings()
    settings.validate_runtime_configuration()
    if queue is None:
        if settings.redis_url:
            queue = RedisQueueAdapter(settings.redis_url)
        else:
            queue = FakeQueueAdapter()

    # Lazily import so the module-level import doesn't depend on DB init.

    session_factory = _get_session_factory()

    if parser is None:
        parser = CompositeParserAdapter(
            {
                "application/pdf": PyMuPDFParserAdapter(),
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document": DocxParserAdapter(),
            }
        )

    if renderer is None:
        renderer = PymupdfRendererAdapter()

    if storage is None:
        storage = _get_storage_adapter()

    if ocr is None:
        # TesseractOcrAdapter construction never touches the binary, so this
        # cannot fail at import/construct time; a missing ``tesseract``
        # binary surfaces lazily as a per-page non-fatal warning during OCR.
        ocr = TesseractOcrAdapter()

    if llm is None:
        if settings.app_env != "development" and not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for the production worker. "
                "Set it in the environment before starting the stack."
            )
        if settings.app_env == "development" and not settings.openai_api_key:
            # Local development without a configured model: use the deterministic
            # DevLlmAdapter so the full extraction pipeline is exercisable
            # end-to-end without network access to a provider.  DevLlmAdapter
            # applies rule-based extraction that respects the CP25
            # source-substring boundary (raw_source is always a verbatim line
            # from the trusted window text).
            llm = DevLlmAdapter()
        else:
            llm = OpenAiLlmAdapter()

    return Worker(
        queue=queue,
        session_factory=session_factory,
        processor=JobProcessor(
            session_factory,
            parser=parser,
            renderer=renderer,
            storage=storage,
            ocr=ocr,
            llm=llm,
            verbatim_validation_fallback_enabled=(
                settings.verbatim_validation_fallback_enabled
            ),
            obligation_coverage_audit_enabled=(
                settings.obligation_coverage_audit_enabled
            ),
        ),
        max_concurrency=max_concurrency or settings.max_concurrency,
    )


def _get_storage_adapter() -> ObjectStorageAdapter:
    """Return the storage adapter based on configuration."""
    return create_storage_adapter()


def _get_session_factory() -> SessionFactory:
    """Return the app's session factory, initializing the engine if needed."""
    from tender_compliance_api.db.session import _session_factory as _sf

    if _sf is None:
        init_engine()
        from tender_compliance_api.db.session import _session_factory as sf
        assert sf is not None  # guaranteed after init_engine()
        return cast(SessionFactory, sf)
    return cast(SessionFactory, _sf)


def main() -> None:
    """CLI entry point: ``python -m tender_compliance_worker``."""
    parser = argparse.ArgumentParser(
        description="Tender Compliance Engine background worker",
    )
    parser.add_argument(
        "--max-concurrency", type=int, default=4,
        help="Maximum simultaneous jobs (default: 4)",
    )
    parser.add_argument(
        "--queue", type=str, default=DEFAULT_QUEUE,
        help="Queue name to poll (default: document_processing)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    worker = create_worker(max_concurrency=args.max_concurrency)
    try:
        asyncio.run(worker.run(args.queue))
    except KeyboardInterrupt:
        logger.info("Worker shutting down")
