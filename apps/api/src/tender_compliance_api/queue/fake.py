"""In-memory fake queue adapter for testing (CP18).

Mirrors the :class:`QueueAdapter` contract without requiring Redis.
Not safe for production use — single-process only.
"""

from __future__ import annotations

import dataclasses
import time

from tender_compliance_api.queue.adapter import (
    DEFAULT_QUEUE,
    QueueAdapter,
    QueuedJob,
    QueueMessage,
)


@dataclasses.dataclass
class _FakeJob:
    job_id: str
    payload: dict[str, object]
    attempt: int
    claimed: bool = False
    claimed_at: float = 0.0
    released_at: float = 0.0  # earliest time the job is available again


class FakeQueueAdapter(QueueAdapter):
    """Thread-unsafe in-memory queue for tests.

    Honors ``delay`` by recording ``released_at``; :meth:`dequeue` skips
    jobs whose ``released_at`` is in the future.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[_FakeJob]] = {}
        self._jobs: dict[str, _FakeJob] = {}

    async def enqueue(
        self,
        queue: str,
        job_id: str,
        message: QueueMessage,
        *,
        delay: int = 0,
    ) -> None:
        # Idempotent: skip if the job already exists and is not claimed.
        existing = self._jobs.get(job_id)
        if existing is not None and not existing.claimed:
            return
        if existing is not None and existing.claimed:
            # Re-enqueue — overwrite old job data.
            self._jobs.pop(job_id, None)
            for q in self._queues:
                self._queues[q] = [
                    j for j in self._queues[q] if j.job_id != job_id
                ]

        job = _FakeJob(
            job_id=job_id,
            payload=dataclasses.asdict(message),
            attempt=message.attempt,
            released_at=time.monotonic() + delay,
        )
        self._jobs[job_id] = job
        self._queues.setdefault(queue, []).append(job)

    async def dequeue(
        self, queue: str, visibility_timeout: int = 300
    ) -> QueuedJob | None:
        now = time.monotonic()
        jobs = self._queues.get(queue, [])
        for job in jobs:
            if not job.claimed and job.released_at <= now:
                job.claimed = True
                job.claimed_at = now
                return QueuedJob(
                    job_id=job.job_id,
                    payload=job.payload,
                    attempt=job.attempt,
                    queue=queue,
                )
        return None

    async def acknowledge(self, queue: str, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None:
            self._queues.setdefault(queue, [])
            self._queues[queue] = [
                j for j in self._queues[queue] if j.job_id != job_id
            ]

    async def release(self, queue: str, job_id: str, delay: int = 0) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.claimed = False
            job.released_at = time.monotonic() + delay

    async def size(self, queue: str = DEFAULT_QUEUE) -> int:
        return len(self._jobs)

    # --- Test helpers ---

    def reset(self) -> None:
        """Clear all jobs (for test isolation)."""
        self._queues.clear()
        self._jobs.clear()
