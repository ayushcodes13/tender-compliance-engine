"""Redis-backed queue adapter (CP18).

Uses a simple Redis LIST-based queue with a HASH for job metadata and
a short-lived lock key for claiming.  Jobs are enqueued with a
deterministic ``job_id`` so re-enqueueing after a crash is idempotent.

Security: only identifiers travel on the queue, never document bodies.
"""

from __future__ import annotations

import json
from typing import Any, cast

import redis.asyncio as redis

from tender_compliance_api.queue.adapter import (
    DEFAULT_VISIBILITY_TIMEOUT,
    QueueAdapter,
    QueuedJob,
    QueueMessage,
)

#: Key prefix namespace for all queue keys.
_KEY_PREFIX = "tc"
_WORKER_HEARTBEAT_KEY = f"{_KEY_PREFIX}:worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 15

#: The Redis client is typed as ``Any`` because redis-py's async stubs
#: report ``Awaitable[T] | T`` for pipeline-overloaded methods, which
#: mypy strict mode rejects.  This is a well-known limitation of
#: redis-py type stubs (see redis-py #2683).
_REDIS_ANY: Any


def _job_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}:job:{job_id}"


def _queue_key(queue: str) -> str:
    return f"{_KEY_PREFIX}:queue:{queue}"


def _claim_key(job_id: str) -> str:
    return f"{_KEY_PREFIX}:claim:{job_id}"


def _message_to_dict(message: QueueMessage) -> dict[str, object]:
    """Convert QueueMessage to a plain dict for JSON serialization."""
    return {
        "document_version_id": message.document_version_id,
        "document_id": message.document_id,
        "organization_id": message.organization_id,
        "version_number": message.version_number,
        "stage": message.stage,
        "run_id": message.run_id,
        "attempt": message.attempt,
    }


class RedisQueueAdapter(QueueAdapter):
    """Production queue adapter backed by Redis.

    Constructor takes a Redis URL.  In tests, fall back to
    :class:`FakeQueueAdapter` when no URL is configured.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._client: Any = None

    @classmethod
    def from_config(cls, redis_url: str) -> RedisQueueAdapter:
        return cls(redis_url=redis_url)

    async def _get_client(self) -> Any:
        if self._client is None:
            self._client = redis.from_url(  # type: ignore[no-untyped-call]
                self._redis_url or "redis://localhost:6379/0"
            )
        return self._client

    async def enqueue(
        self,
        queue: str,
        job_id: str,
        message: QueueMessage,
        *,
        delay: int = 0,
    ) -> None:
        client = await self._get_client()
        job_key = _job_key(job_id)
        queue_key = _queue_key(queue)

        # Idempotent while queued or claimed. If a worker died after popping a
        # job, the metadata hash can outlive its claim even though no queue
        # entry remains. In that case, restore the queue entry so API retries
        # can recover the job instead of reporting a false queued state.
        exists = await client.exists(job_key)
        claim_exists = await client.exists(_claim_key(job_id))
        if exists:
            if claim_exists:
                return
            queue_position = await client.lpos(queue_key, job_id)
            if queue_position is not None:
                return

        # Store job metadata.
        await client.hset(
            job_key,
            mapping={
                "job_id": job_id,
                "payload": json.dumps(_message_to_dict(message)),
                "attempt": str(message.attempt),
            },
        )
        await client.lpush(queue_key, job_id)

    async def dequeue(
        self, queue: str, visibility_timeout: int = DEFAULT_VISIBILITY_TIMEOUT
    ) -> QueuedJob | None:
        client = await self._get_client()
        queue_key = _queue_key(queue)

        # Blocking pop with a 5-second poll timeout.
        result = await client.brpop(queue_key, timeout=5)
        if result is None:
            return None

        _, job_id_raw = result
        if isinstance(job_id_raw, bytes):
            job_id = job_id_raw.decode("utf-8")
        else:
            job_id = str(job_id_raw)

        # Try to claim the job with a TTL (visibility timeout).
        claim_key = _claim_key(job_id)
        claimed = await client.set(claim_key, "1", nx=True, ex=visibility_timeout)
        if not claimed:
            # Another worker already claimed it — skip.
            return None

        # Load job metadata.
        job_data = await client.hgetall(_job_key(job_id))
        if not job_data:
            await client.delete(claim_key)
            return None

        payload_raw = job_data.get(b"payload", b"{}")
        if isinstance(payload_raw, bytes):
            payload_raw = payload_raw.decode("utf-8")
        payload = json.loads(payload_raw)
        attempt_raw = job_data.get(b"attempt", b"1")
        if isinstance(attempt_raw, bytes):
            attempt_raw = attempt_raw.decode("utf-8")
        attempt = int(attempt_raw)

        return QueuedJob(
            job_id=job_id,
            payload=payload,
            attempt=attempt,
            queue=queue,
        )

    async def acknowledge(self, queue: str, job_id: str) -> None:
        client = await self._get_client()
        await client.delete(_job_key(job_id), _claim_key(job_id))

    async def release(self, queue: str, job_id: str, delay: int = 0) -> None:
        client = await self._get_client()
        # Remove the claim so the job is visible again.
        await client.delete(_claim_key(job_id))
        # Re-enqueue at the head of the queue.
        await client.lpush(_queue_key(queue), job_id)

    async def size(self, queue: str) -> int:
        client = await self._get_client()
        return cast(int, await client.llen(_queue_key(queue)))

    async def heartbeat_worker(self) -> None:
        """Keep a bounded Redis lease while this worker is polling."""
        client = await self._get_client()
        await client.set(_WORKER_HEARTBEAT_KEY, "alive", ex=WORKER_HEARTBEAT_TTL_SECONDS)

    async def worker_ready(self) -> bool:
        """Report whether any worker has renewed its polling lease recently."""
        client = await self._get_client()
        return bool(await client.exists(_WORKER_HEARTBEAT_KEY))

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except AttributeError:
                await self._client.close()
            self._client = None
