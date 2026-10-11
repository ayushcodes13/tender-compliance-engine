"""Regression coverage for Redis-backed processing job recovery."""

from __future__ import annotations

import asyncio
import json

from tender_compliance_api.queue.adapter import DEFAULT_QUEUE, QueueMessage
from tender_compliance_api.queue.redis import RedisQueueAdapter


class _StubRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.keys: set[str] = set()

    async def exists(self, key: str) -> int:
        return int(key in self.hashes or key in self.keys)

    async def lpos(self, key: str, value: str) -> int | None:
        try:
            return self.lists[key].index(value)
        except (KeyError, ValueError):
            return None

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        self.hashes[key] = mapping

    async def lpush(self, key: str, value: str) -> int:
        items = self.lists.setdefault(key, [])
        items.insert(0, value)
        return len(items)


def _message() -> QueueMessage:
    return QueueMessage(
        document_version_id="version-1",
        document_id="document-1",
        organization_id="organization-1",
        version_number=1,
        stage="parse",
        run_id="run-1",
        attempt=1,
    )


def test_enqueue_repairs_orphaned_unclaimed_job() -> None:
    async def run() -> None:
        client = _StubRedis()
        adapter = RedisQueueAdapter()
        adapter._client = client
        client.hashes["tc:job:run-1"] = {
            "job_id": "run-1",
            "payload": json.dumps({"stage": "parse"}),
            "attempt": "1",
        }

        await adapter.enqueue(DEFAULT_QUEUE, "run-1", _message())

        assert client.lists["tc:queue:document_processing"] == ["run-1"]
        assert json.loads(client.hashes["tc:job:run-1"]["payload"])["run_id"] == "run-1"

    asyncio.run(run())


def test_duplicate_enqueue_does_not_duplicate_existing_queue_entry() -> None:
    async def run() -> None:
        client = _StubRedis()
        adapter = RedisQueueAdapter()
        adapter._client = client

        await adapter.enqueue(DEFAULT_QUEUE, "run-1", _message())
        await adapter.enqueue(DEFAULT_QUEUE, "run-1", _message())

        assert client.lists["tc:queue:document_processing"] == ["run-1"]

    asyncio.run(run())
