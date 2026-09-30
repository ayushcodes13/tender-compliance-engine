"""Declarative base for ORM models.

This module defines the single declarative base that all domain models
register onto via ``Base.metadata``.  Alembic (CP07) ties its autogenerate
target to this metadata.

No application tables exist yet.  The first tables arrive in subsequent
checkpoints (CP08+).  This module only provides the registry — it does not
create any tables.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all Tender Compliance Engine models."""
