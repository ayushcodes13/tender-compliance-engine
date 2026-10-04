"""Provider-agnostic object-storage adapter abstraction (CP12).

This module defines the *port* (abstract interface) that application
services depend on.  Concrete implementations (S3/MinIO, in-memory fake)
live in sibling modules.  The interface is intentionally narrow so that
Phase-2 concerns (presigning for browser uploads, lifecycle policies, etc.)
can be added later without widening the contract prematurely.

Design notes:

* Checksums are computed **by the application** — the adapter returns the
  SHA-256 it computed from the bytes it actually received, not a value
  trusted from the provider.
* The adapter deals purely in opaque ``key`` strings.  Key *scoping*
  (org/project/document/version) lives in :mod:`tender_compliance_api.storage.keys`
  so that routing logic is testable in isolation.
* ``read_access`` returns a URL string.  For S3 it is a presigned URL;
  for the fake it is a non-functional placeholder.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectInfo:
    """Metadata returned by the adapter about a stored object.

    ``checksum_sha256`` is computed by the adapter from the actual bytes
    written — it is never taken from the provider.
    """

    key: str
    content_type: str
    content_length: int
    checksum_sha256: str
    etag: str | None = None


class ObjectStorageAdapter(ABC):
    """Abstract interface every storage provider implementation must satisfy.

    Methods are ``async`` so the FastAPI service layer can call them
    without ``asyncio.to_thread`` at every call site.  Sync providers
    (e.g. boto3) are bridged inside the concrete implementation.
    """

    async def ready(self) -> None:
        """Raise when the backing storage is unavailable.

        The default implementation is a no-op for in-memory/test providers.
        Production providers should perform a lightweight provider-level check.
        """
        return None

    @abstractmethod
    async def put(
        self, key: str, data: bytes, content_type: str
    ) -> ObjectInfo:
        """Upload ``data`` to ``key`` and return verified metadata."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Download and return the full object bytes at ``key``."""

    @abstractmethod
    async def head(self, key: str) -> ObjectInfo:
        """Return metadata for ``key`` without downloading the body."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the object at ``key``.  No-op if it does not exist."""

    @abstractmethod
    async def read_access(self, key: str, expires_in: int = 3600) -> str:
        """Return a URL granting temporary read access to ``key``.

        For S3 providers this is a presigned URL.  The returned URL
        expires after ``expires_in`` seconds.
        """
