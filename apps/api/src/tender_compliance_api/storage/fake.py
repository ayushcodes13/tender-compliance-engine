"""In-memory fake object-storage adapter (CP12).

Used by tests and local development without a running MinIO/S3 instance.
All objects live in a **class-level** dictionary so that a single logical
store persists across ``FakeStorageAdapter()`` instantiations within the
same process — this matters for request/response roundtrips (e.g. export
then download) where FastAPI creates a new dependency each time.

Not suitable for production or multi-process deployments.
"""

from __future__ import annotations

import hashlib
import time

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter


class FakeStorageAdapter(ObjectStorageAdapter):
    """Process-local in-memory store for testing and local development.

    Data is stored at the **class level** so that multiple instances share
    the same underlying dict — this allows roundtrip tests (write then
    read in separate request scopes) to work correctly.
    """

    _store: dict[str, bytes] = {}
    _meta: dict[str, dict[str, object]] = {}

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
