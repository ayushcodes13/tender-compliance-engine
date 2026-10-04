"""Create the configured object-storage adapter in one place."""

from __future__ import annotations

from tender_compliance_api.config import Settings, get_settings
from tender_compliance_api.storage.adapter import ObjectStorageAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.filesystem import FileSystemStorageAdapter
from tender_compliance_api.storage.s3 import S3StorageAdapter


def create_storage_adapter(settings: Settings | None = None) -> ObjectStorageAdapter:
    """Return S3, durable local filesystem, or in-memory development storage."""
    cfg = settings or get_settings()
    if cfg.object_storage_endpoint:
        return S3StorageAdapter(
            endpoint_url=cfg.object_storage_endpoint,
            access_key=cfg.object_storage_access_key,
            secret_key=cfg.object_storage_secret_key,
            bucket=cfg.object_storage_bucket,
            region=cfg.object_storage_region,
        )
    if cfg.object_storage_local_path:
        return FileSystemStorageAdapter(cfg.object_storage_local_path)
    return FakeStorageAdapter()


async def initialize_storage_adapter(
    settings: Settings | None = None,
) -> ObjectStorageAdapter:
    """Create storage and verify/initialize provider prerequisites."""
    storage = create_storage_adapter(settings)
    if isinstance(storage, S3StorageAdapter):
        await storage.ensure_bucket()
    await storage.ready()
    return storage
