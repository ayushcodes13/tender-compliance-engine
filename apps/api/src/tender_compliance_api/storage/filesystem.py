"""Durable local-filesystem object storage for single-host pilots.

The adapter keeps the same ObjectStorageAdapter contract as S3 while storing
objects beneath one configured root directory.  It is intended for a private,
single-host Docker deployment where API and worker mount the same named volume.
Cloud/public deployments can continue to use the S3 adapter.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter


class FileSystemStorageAdapter(ObjectStorageAdapter):
    """Persist objects and metadata under a single guarded filesystem root."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, key: str) -> Path:
        normalized = key.replace("\\", "/").strip()
        if not normalized or normalized.startswith("/"):
            raise ValueError("storage key must be a non-empty relative path")
        path = (self._root / normalized).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("storage key escapes configured root") from exc
        return path

    @staticmethod
    def _meta_path(path: Path) -> Path:
        return path.with_name(path.name + ".tce-meta.json")

    async def ready(self) -> None:
        await asyncio.to_thread(self._ready_sync)

    def _ready_sync(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        probe = self._root / ".tce-ready"
        probe.write_bytes(b"ready")
        probe.unlink(missing_ok=True)

    async def put(self, key: str, data: bytes, content_type: str) -> ObjectInfo:
        return await asyncio.to_thread(self._put_sync, key, data, content_type)

    def _put_sync(self, key: str, data: bytes, content_type: str) -> ObjectInfo:
        path = self._object_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256(data).hexdigest()
        etag = hashlib.md5(data).hexdigest()  # noqa: S324 - non-security content tag

        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_bytes(data)
        os.replace(temp, path)

        meta: dict[str, Any] = {
            "content_type": content_type,
            "content_length": len(data),
            "checksum_sha256": checksum,
            "etag": etag,
        }
        meta_path = self._meta_path(path)
        meta_temp = meta_path.with_name(f".{meta_path.name}.{uuid.uuid4().hex}.tmp")
        meta_temp.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
        os.replace(meta_temp, meta_path)

        return ObjectInfo(
            key=key,
            content_type=content_type,
            content_length=len(data),
            checksum_sha256=checksum,
            etag=etag,
        )

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._object_path(key).read_bytes)

    async def head(self, key: str) -> ObjectInfo:
        return await asyncio.to_thread(self._head_sync, key)

    def _head_sync(self, key: str) -> ObjectInfo:
        path = self._object_path(key)
        data = path.read_bytes()
        meta_path = self._meta_path(path)
        meta: dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return ObjectInfo(
            key=key,
            content_type=str(meta.get("content_type", "application/octet-stream")),
            content_length=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            etag=str(meta["etag"]) if meta.get("etag") else None,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        path = self._object_path(key)
        path.unlink(missing_ok=True)
        self._meta_path(path).unlink(missing_ok=True)

    async def read_access(self, key: str, expires_in: int = 3600) -> str:
        del expires_in
        path = self._object_path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.as_uri()
