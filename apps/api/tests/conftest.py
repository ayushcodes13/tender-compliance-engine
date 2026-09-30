"""Shared pytest fixtures for the API test suite."""

import asyncio

import pytest
from sqlalchemy.pool import StaticPool

from tender_compliance_api.db.session import close_engine, init_engine

# SQLite in-memory database for fast, self-contained session tests.
# StaticPool + check_same_thread=False ensures a single shared connection
# so all sessions see the same in-memory database.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
TEST_ENGINE_KWARGS = {
    "connect_args": {"check_same_thread": False},
    "poolclass": StaticPool,
}


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Initialize the test database engine for the entire test session.

    This guarantees a clean engine regardless of whether any prior test
    or app startup initialized one (e.g. via TestClient lifespan).
    """
    asyncio.run(close_engine())
    init_engine(TEST_DATABASE_URL, **TEST_ENGINE_KWARGS)
    yield
    asyncio.run(close_engine())
