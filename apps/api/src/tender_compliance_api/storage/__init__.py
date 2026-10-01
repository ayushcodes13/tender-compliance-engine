"""Object-storage adapter package (CP12).

Exports the abstract interface, key-scoping helpers, and concrete
implementations (S3/MinIO and in-memory fake).
"""

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter
from tender_compliance_api.storage.fake import FakeStorageAdapter
from tender_compliance_api.storage.keys import build_key, parse_key
from tender_compliance_api.storage.s3 import S3StorageAdapter

__all__ = [
    "ObjectInfo",
    "ObjectStorageAdapter",
    "FakeStorageAdapter",
    "S3StorageAdapter",
    "build_key",
    "parse_key",
]
