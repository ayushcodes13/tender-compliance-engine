"""In-memory fake object-storage adapter (CP12).

Used by tests and local development without a running MinIO/S3 instance.
All objects live in a process-local dictionary and are lost when the
adapter is garbage-collected.
"""

from __future__ import annotations

import hashlib
import time

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter


class FakeStorageAdapter(ObjectStorageAdapter):
    """Thread-safe-enough in-memory store for testing.

    Not suitable for production or multi-process deployments.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._meta: dict[str, dict[str, object]] = {}

    async def put(
        self, key: str, data: bytes, content_type: str
    ) -> ObjectInfo:
        checksum = hashlib.sha256(data).hexdigest()
        etag = hashlib.md5(data).hexdigest()
        self._store[key] = data
        self._meta[key] = {
            "content_type": content_type,
            "content_length": len(data),
            "etag": etag,
            "stored_at": time.time(),
        }
        return ObjectInfo(
            key=key,
            content_type=content_type,
            content_length=len(data),
            checksum_sha256=checksum,
            etag=etag,
        )

    async def get(self, key: str) -> bytes:
        return self._store[key]

    async def head(self, key: str) -> ObjectInfo:
        meta = self._meta[key]
        data = self._store[key]
        return ObjectInfo(
            key=key,
            content_type=meta["content_type"],  # type: ignore[arg-type]
            content_length=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            etag=meta["etag"],  # type: ignore[arg-type]
        )

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._meta.pop(key, None)

    async def read_access(self, key: str, expires_in: int = 3600) -> str:
        # Placeholder URL; not functional but satisfies the interface contract.
        return f"mem://{key}?expires={int(time.time()) + expires_in}"
