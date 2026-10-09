"""Preserve long source section labels during extraction persistence.

Revision ID: 0036_unbounded_clause_labels
Revises: 0035_worker_audit_actor
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0036_unbounded_clause_labels"
down_revision: str | None = "0035_worker_audit_actor"
branch_labels: str | None = None
depends_on: str | None = None

_COLUMNS = {
    "extraction_candidates": ("clause_number", "group_hint"),
    "requirements": ("clause_number",),
    "requirement_sources": ("clause_number",),
}


def upgrade() -> None:
    """Store free-form section labels without truncation or row failures."""
    for table_name, column_names in _COLUMNS.items():
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in column_names:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.String(length=64),
                    type_=sa.Text(),
                    existing_nullable=True,
                )


def downgrade() -> None:
    """Refuse to narrow labels if that would discard persisted source data."""
    bind = op.get_bind()
    for table_name, column_names in _COLUMNS.items():
        table = sa.table(table_name, *(sa.column(name) for name in column_names))
        for column_name in column_names:
            has_long_value = bind.execute(
                sa.select(sa.func.count())
                .select_from(table)
                .where(sa.func.length(table.c[column_name]) > 64)
            ).scalar_one()
            if has_long_value:
                raise RuntimeError(
                    f"Cannot downgrade {table_name}.{column_name}: "
                    "values longer than 64 characters would be truncated"
                )

    for table_name, column_names in _COLUMNS.items():
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in column_names:
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.Text(),
                    type_=sa.String(length=64),
                    existing_nullable=True,
                )
