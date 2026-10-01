"""S3-compatible object-storage adapter (CP12).

Concrete implementation wrapping ``boto3`` for S3-compatible providers
such as MinIO.  All boto3 usage is confined to this module so that
application services never import provider SDKs directly.

The adapter is async by delegation: each public method delegates the
blocking boto3 call to ``asyncio.to_thread`` so the FastAPI event loop
stays unblocked.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from boto3 import client as boto3_client  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from tender_compliance_api.storage.adapter import ObjectInfo, ObjectStorageAdapter

logger = logging.getLogger(__name__)


class S3StorageAdapter(ObjectStorageAdapter):
    """Object-storage adapter backed by an S3-compatible endpoint.

    Args:
        endpoint_url: S3 endpoint (e.g. ``http://localhost:9000`` for MinIO).
        access_key: Access key ID.
        secret_key: Secret access key.
        bucket: Bucket name.
        region: AWS region name (default ``us-east-1``).
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3_client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist.

        Safe to call at startup; idempotency relies on
        ``BucketAlreadyOwnedByYou`` / ``BucketAlreadyExists`` being caught.
        """
        await asyncio.to_thread(self._safe_create_bucket)

    def _safe_create_bucket(self) -> None:
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise

    # ------------------------------------------------------------------
    # ObjectStorageAdapter interface
    # ------------------------------------------------------------------

    async def put(
        self, key: str, data: bytes, content_type: str
    ) -> ObjectInfo:
        checksum = hashlib.sha256(data).hexdigest()

        def _put() -> str | None:
            response = self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ChecksumAlgorithm="SHA256",  # informational; we compute our own
            )
            return response.get("ETag", "").strip('"') or None

        etag = await asyncio.to_thread(_put)
        return ObjectInfo(
            key=key,
            content_type=content_type,
            content_length=len(data),
            checksum_sha256=checksum,
            etag=etag,
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            return bytes(body)

        return await asyncio.to_thread(_get)

    async def head(self, key: str) -> ObjectInfo:
        def _head() -> ObjectInfo:
            response = self._client.head_object(
                Bucket=self._bucket, Key=key
            )
            etag = (response.get("ETag") or "").strip('"') or None
            content_length = int(response.get("ContentLength", 0))
            return ObjectInfo(
                key=key,
                content_type=response.get("ContentType", ""),
                content_length=content_length,
                checksum_sha256="",  # unknown from provider alone
                etag=etag,
            )

        return await asyncio.to_thread(_head)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code != "NoSuchKey":
                    raise

        await asyncio.to_thread(_delete)

    async def read_access(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for downloading the object."""
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return str(url)
