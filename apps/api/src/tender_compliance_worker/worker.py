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
from tender_compliance_api.ocr.adapter import OcrAdapter
from tender_compliance_api.ocr.tesseract import TesseractOcrAdapter
from tender_compliance_api.parser import (
    CompositeParserAdapter,
    DocxParserAdapter,
    PypdfParserAdapter,
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
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.s3 import S3StorageAdapter
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
        while self._running:
            try:
                await self.run_once(queue_name)
            except KeyboardInterrupt:
                break
            except Exception:  # noqa: BLE001
                logger.exception("Worker error in run loop")
            await asyncio.sleep(1)

    def stop(self) -> None:
        self._running = False


def create_worker(
    *,
    queue: QueueAdapter | None = None,
    parser: ParserAdapter | None = None,
    renderer: RendererAdapter | None = None,
    storage: ObjectStorageAdapter | None = None,
    ocr: OcrAdapter | None = None,
    max_concurrency: int | None = None,
) -> Worker:
    """Create a :class:`Worker` with production defaults.

    Uses :class:`RedisQueueAdapter` when ``REDIS_URL`` is configured;
    otherwise falls back to :class:`FakeQueueAdapter`.  Defaults:
    :class:`CompositeParserAdapter` dispatching to
    :class:`PypdfParserAdapter` (PDF, CP19) and :class:`DocxParserAdapter`
    (DOCX, CP22), :class:`PymupdfRendererAdapter` (CP20), and
    :class:`TesseractOcrAdapter` (CP21).
    """
    settings = get_settings()
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
                "application/pdf": PypdfParserAdapter(),
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

    return Worker(
        queue=queue,
        session_factory=session_factory,
        processor=JobProcessor(
            session_factory,
            parser=parser,
            renderer=renderer,
            storage=storage,
            ocr=ocr,
        ),
        max_concurrency=max_concurrency or settings.max_concurrency,
    )


def _get_storage_adapter() -> ObjectStorageAdapter:
    """Return the storage adapter based on configuration."""
    settings = get_settings()
    if not settings.object_storage_endpoint:
        return FakeStorageAdapter()
    return S3StorageAdapter(
        endpoint_url=settings.object_storage_endpoint,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key,
        bucket=settings.object_storage_bucket,
        region=settings.object_storage_region,
    )


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
