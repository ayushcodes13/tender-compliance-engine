"""Object-storage adapter package (CP12).

Exports the abstract interface, key-scoping helpers, and concrete
implementations (durable filesystem, S3-compatible, and in-memory fake).
"""

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.filesystem import FileSystemStorageAdapter
from tender_compliance_api.storage.keys import build_key, parse_key
from tender_compliance_api.storage.s3 import S3StorageAdapter

__all__ = [
    "ObjectInfo",
    "ObjectStorageAdapter",
    "FakeStorageAdapter",
    "FileSystemStorageAdapter",
    "S3StorageAdapter",
    "build_key",
    "parse_key",
]
