"""Project-level column types.

The types here are small, explicit wrappers around SQLAlchemy primitives that
enforce deterministic storage behaviour the stock types do not guarantee on
every supported backend.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import UUID as _SaUUID
from sqlalchemy import String, TypeDecorator


class TcuUUID(TypeDecorator[Any]):
    """A :class:`uuid.UUID` column that round-trips safely on every backend.

    Why this exists
    ---------------
    :class:`sqlalchemy.UUID` (with ``as_uuid=True``) stores values through the
    dialect's native UUID type when one exists (PostgreSQL) — correct by
    construction.  On backends *without* a native UUID type (SQLite, used by
    the test suite and by direct local development), SQLAlchemy falls back to
    emitting the UUID's ``hex`` representation (the 32 hex digits *without*
    dashes) into a column whose declared type ("UUID") carries **NUMERIC
    affinity** on SQLite.

    NUMERIC affinity silently coerces a value whose text is an all-decimal
    literal into a Python ``int``.  That happens to include the deterministic
    single-workspace bootstrap IDs
    ``00000000-0000-0000-0000-000000000001`` / ``...002`` (their ``hex`` is
    ``"00000000000000000000000000000001"``), which SQLite stores as the
    integer ``1``.  The stock ``UUID`` result processor then calls
    ``uuid.UUID(1)`` — crashing with ``AttributeError: 'int' object has no
    attribute 'replace'`` — the first time any code reads such a row back over
    a fresh connection (e.g. the *second* single-workspace request, when the
    bootstrapped owner already exists).  Random ``uuid4`` values are unaffected
    because their hex contains non-decimal characters and stay text, which is
    why the test suite (random UUIDs) never caught this.

    The fix
    -------
    * bind param: coerce to the canonical, dash-separated ``str(uuid)``.  The
      dashes make the literal non-numeric, so it is preserved as text even
      under NUMERIC affinity;
    * SQLite DDL uses ``VARCHAR(36)`` (TEXT affinity) via a dialect variant so
      there is no implicit numeric coercion path to begin with;
    * result param: coerce the stored text back to :class:`uuid.UUID`;
    * PostgreSQL path is byte-for-byte unchanged — the native ``UUID`` type and
      its processors are used, so production storage/encoding is untouched.

    No Alembic migration is required: on PostgreSQL the generated DDL is still
    ``UUID`` (the variant only switches for SQLite), and SQLite databases in
    this project are always built fresh from the models (tests / local dev).
    """

    impl = _SaUUID(as_uuid=True)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Use a TEXT-affinity variant on SQLite; native UUID elsewhere."""
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(36))
        return dialect.type_descriptor(self.impl)

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            # Canonical, dash-separated form ("00000000-...-0001") is never a
            # numeric literal, so SQLite keeps it as TEXT.
            return str(value)
        # PostgreSQL: hand the native adapter the uuid.UUID it understands.
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            if isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(value)
        # PostgreSQL: the native adapter already returned a uuid.UUID.
        return value


__all__ = ["TcuUUID"]
