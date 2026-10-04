"""Queue adapter abstractions (CP18).

Provides a provider-agnostic interface for enqueueing and dequeuing
document-processing jobs.  Only job identifiers travel on the queue —
never full document bodies (per AGENTS.md security rules).
"""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass

#: Default queue name for document-processing jobs.
DEFAULT_QUEUE = "document_processing"

#: How long a claimed job is invisible before it is re-delivered (seconds).
DEFAULT_VISIBILITY_TIMEOUT = 300


@dataclass
class QueuedJob:
    """A job retrieved from the queue, ready for processing."""

    job_id: str
    payload: dict[str, object]
    attempt: int
    queue: str


@dataclass
class QueueMessage:
    """Payload enqueued for a processing job.

    Only identifiers are serialized — never raw document bytes.
    """

    document_version_id: str
    document_id: str
    organization_id: str
    version_number: int
    stage: str
    run_id: str
    attempt: int = 1


def make_job_id(
    document_version_id: str,
    stage: str,
    namespace: str = "tender",
) -> uuid.UUID:
    """Generate a deterministic job ID from (namespace, version, stage).

    Idempotency: re-enqueuing the same namespace+version+stage returns the
    same job ID, so the queue can deduplicate.

    The ``namespace`` prefix (default ``"tender"``) separates tender and
    OEM document spaces so their job IDs never collide even if UUIDs
    coincide.
    """
    return uuid.uuid5(
        uuid.UUID("00000000-0000-5000-8000-000000000000"),
        f"{namespace}:{document_version_id}:{stage}",
    )


class QueueAdapter(abc.ABC):
    """Abstract interface for a background-job queue.

    Implementations must be safe to call from concurrent workers and
    must support idempotent enqueue (same job_id is not duplicated).
    """

    @abc.abstractmethod
    async def enqueue(
        self,
        queue: str,
        job_id: str,
        message: QueueMessage,
        *,
        delay: int = 0,
    ) -> None:
        """Enqueue *message* with a deterministic *job_id*.

        If a job with the same ``job_id`` already exists (and is not
        already claimed), the call is a no-op.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def dequeue(
        self, queue: str, visibility_timeout: int = DEFAULT_VISIBILITY_TIMEOUT
    ) -> QueuedJob | None:
        """Claim and return the next available job, or ``None`` on timeout."""
        raise NotImplementedError

    @abc.abstractmethod
    async def acknowledge(self, queue: str, job_id: str) -> None:
        """Mark *job_id* as permanently processed; remove it from the queue."""
        raise NotImplementedError

    @abc.abstractmethod
    async def release(self, queue: str, job_id: str, delay: int = 0) -> None:
        """Release a claimed job back to the queue for retry (with *delay*)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def size(self, queue: str) -> int:
        """Return the approximate number of jobs (available + in-flight)."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release provider resources when the adapter owns any.

        In-memory providers do not need cleanup; network-backed providers may
        override this method.
        """
        return None
