"""Tests for the object-storage adapter layer (CP12).

Uses the in-memory :class:`FakeStorageAdapter` for round-trip and
isolation tests, and verifies the ``StoredObject`` DB model plus
key-scoping helpers.
"""

import asyncio
import hashlib
import uuid

from tender_compliance_api.db import StoredObject
from tender_compliance_api.storage import (
    FakeStorageAdapter,
    ObjectStorageAdapter,
    build_key,
)

# ---------------------------------------------------------------------------
# Key scoping
# ---------------------------------------------------------------------------


class TestBuildKey:
    def test_basic_key(self) -> None:
        org = uuid.uuid4()
        proj = uuid.uuid4()
        key = build_key(org_id=org, project_id=proj)
        assert key.startswith(f"{org}/{proj}/")
        parts = key.split("/")
        assert len(parts) == 3
        uuid.UUID(parts[2])  # raises if not a valid UUID

    def test_preserves_extension(self) -> None:
        key = build_key(
            org_id=uuid.uuid4(), project_id=uuid.uuid4(),
            original_filename="tender.pdf",
        )
        assert key.endswith(".pdf")

    def test_document_and_version_in_key(self) -> None:
        org = uuid.uuid4()
        proj = uuid.uuid4()
        doc = uuid.uuid4()
        key = build_key(
            org_id=org, project_id=proj, document_id=doc, version=2,
        )
        parts = key.split("/")
        assert parts[0] == str(org)
        assert parts[1] == str(proj)
        assert parts[2] == str(doc)
        assert parts[3] == "2"

    def test_two_orgs_never_collide(self) -> None:
        org_a = uuid.UUID("11111111-0000-0000-0000-000000000001")
        org_b = uuid.UUID("22222222-0000-0000-0000-000000000002")
        proj = uuid.uuid4()
        key_a = build_key(org_id=org_a, project_id=proj)
        key_b = build_key(org_id=org_b, project_id=proj)
        assert key_a != key_b
        assert key_a.split("/")[0] != key_b.split("/")[0]

    def test_two_files_same_name_dont_collide(self) -> None:
        org = uuid.uuid4()
        proj = uuid.uuid4()
        key_a = build_key(
            org_id=org, project_id=proj, original_filename="doc.pdf",
        )
        key_b = build_key(
            org_id=org, project_id=proj, original_filename="doc.pdf",
        )
        assert key_a != key_b


# ---------------------------------------------------------------------------
# FakeStorageAdapter round-trip and behaviour
# ---------------------------------------------------------------------------


def test_fake_put_get_round_trip() -> None:
    """Upload then download returns identical bytes."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        data = b"Hello, Tender Compliance Engine!"
        info = await adapter.put("test/key", data, "text/plain")
        assert info.content_length == len(data)
        assert info.content_type == "text/plain"
        result = await adapter.get("test/key")
        assert result == data

    asyncio.run(_run())


def test_fake_checksum_is_application_computed() -> None:
    """SHA-256 is computed from the actual bytes, not from the provider."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        data = b"checksum me"
        info = await adapter.put("k", data, "application/pdf")
        expected = hashlib.sha256(data).hexdigest()
        assert info.checksum_sha256 == expected

    asyncio.run(_run())


def test_fake_head_returns_metadata() -> None:
    """head() returns metadata without necessarily returning the body."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        data = b"head me"
        await adapter.put("head-key", data, "image/png")
        info = await adapter.head("head-key")
        assert info.key == "head-key"
        assert info.content_type == "image/png"
        assert info.content_length == len(data)
        assert info.checksum_sha256 == hashlib.sha256(data).hexdigest()

    asyncio.run(_run())


def test_fake_delete_removes_object() -> None:
    """After delete, get() raises KeyError."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        await adapter.put("doomed", b"temp", "text/plain")
        await adapter.delete("doomed")
        try:
            await adapter.get("doomed")
            raise AssertionError("Expected KeyError after delete")  # pragma: no cover
        except KeyError:
            pass

    asyncio.run(_run())


def test_fake_delete_idempotent() -> None:
    """delete() on a non-existent key must not raise."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        await adapter.delete("nonexistent")

    asyncio.run(_run())


def test_fake_read_access_returns_url() -> None:
    """read_access() returns a URL-like string."""

    async def _run() -> None:
        adapter = FakeStorageAdapter()
        data = b"access me"
        info = await adapter.put("rl", data, "text/plain")
        url = await adapter.read_access(info.key)
        assert url.startswith("mem://")

    asyncio.run(_run())


def test_fake_is_object_storage_adapter() -> None:
    """FakeStorageAdapter must implement the abstract interface."""
    adapter = FakeStorageAdapter()
    assert isinstance(adapter, ObjectStorageAdapter)


# ---------------------------------------------------------------------------
# StoredObject model + DB persistence
# ---------------------------------------------------------------------------


def test_stored_object_persist_and_retrieve(session_cm) -> None:
    """StoredObject can be written and read back from the database."""

    async def _run() -> None:
        org_id = uuid.uuid4()
        project_id = uuid.uuid4()
        data = b"file content here"
        checksum = hashlib.sha256(data).hexdigest()

        async with session_cm() as session:
            obj = StoredObject(
                organization_id=org_id,
                project_id=project_id,
                storage_key=build_key(
                    org_id=org_id,
                    project_id=project_id,
                    original_filename="doc.pdf",
                ),
                filename="doc.pdf",
                content_type="application/pdf",
                content_length=len(data),
                checksum_sha256=checksum,
                etag="deadbeef",
            )
            session.add(obj)
            await session.commit()

        async with session_cm() as session:
            fetched = await session.get(StoredObject, obj.id)
            assert fetched is not None
            assert fetched.checksum_sha256 == checksum
            assert fetched.content_length == len(data)
            assert fetched.organization_id == org_id

    asyncio.run(_run())
