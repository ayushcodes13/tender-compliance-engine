"""Shared pytest fixtures for the API test suite."""

import asyncio
import contextlib
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from tender_compliance_api.db.session import close_engine, get_session, init_engine

API_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = API_ROOT / "alembic.ini"
ALEMBIC_DIR = API_ROOT / "alembic"

# File-based SQLite so that the Alembic migration engine and the application's
# session engine share the same on-disk database.  In-memory SQLite gives each
# connection its own database, making migrations invisible to the app engine.
TEST_DB_PATH = API_ROOT / "test.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Initialize the test database engine and apply migrations for the
    entire test session.

    Migrations are applied via Alembic (``alembic upgrade head``) so tests
    run against the real migration-produced schema, not
    ``metadata.create_all()`` (per AGENTS.md / BYND-REUSE-AUDIT.md).
    The database file is removed at session end.
    """
    asyncio.run(close_engine())
    TEST_DB_PATH.unlink(missing_ok=True)
    init_engine(TEST_DATABASE_URL)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    command.upgrade(config, "head")
    yield
    asyncio.run(close_engine())
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clear_fake_storage():
    """Clear the FakeStorageAdapter's class-level dict between tests.

    The adapter uses class-level storage (so that export-then-download
    roundtrips work across separate dependency instantiations).  Tests
    that seed their own storage instances must not see data from other
    tests.
    """
    from tender_compliance_api.storage.fake import FakeStorageAdapter

    FakeStorageAdapter._store.clear()
    FakeStorageAdapter._meta.clear()
    yield


@pytest.fixture(autouse=True)
def _isolate_test_storage(monkeypatch):
    """Ensure tests use ``FakeStorageAdapter``, not the real S3/MinIO backend.

    The project ``~/.env`` (used for local hosting) configures
    ``OBJECT_STORAGE_ENDPOINT`` so the API talks to MinIO.  During tests we
    must not contact real object storage, so the env-var is overridden to
    empty strings (which take priority over the ``.env`` file in
    pydantic-settings) and the ``lru_cache`` on :func:`get_settings` is
    cleared so the change takes effect for every test.

    See AGENTS.md: uploaded documents are untrusted — tests must not depend
    on external infrastructure.
    """
    # Empty string — env vars take priority over the .env file in
    # pydantic-settings, so this overrides OBJECT_STORAGE_ENDPOINT=http://localhost:9000
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "")

    from tender_compliance_api.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session_cm():
    """Return an async context manager yielding a fresh :class:`AsyncSession`.

    Convenience wrapper around :func:`get_session` so test functions don't
    need to import ``asynecontextmanager`` themselves.

    Usage::

        def test_something(session_cm):
            async def _run():
                async with session_cm() as session:
                    ...
            asyncio.run(_run())
    """
    return contextlib.asynccontextmanager(get_session)
