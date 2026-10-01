"""Add RequirementRevision table and updated_at on requirements (CP38).

Creates the ``requirement_revisions`` table for immutable edit history
(CP38).  Each row captures the *previous* normalized_text, the actor, a
note, and the ``updated_at`` snapshot used for optimistic concurrency.

Also adds an ``updated_at`` column to the ``requirements`` table to track
when normalized_text was last edited by a human.

Revision ID: 0015_requirement_revisions
Revises: 0014_extraction_constraints
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_requirement_revisions"
down_revision: str | None = "0014_extraction_constraints"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add updated_at to requirements (nullable — existing rows have no edits).
    op.add_column(
        "requirements",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "requirement_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requirement_id", sa.UUID(), nullable=False),
        sa.Column(
            "previous_normalized_text", sa.String(length=2048), nullable=False
        ),
        sa.Column(
            "updated_at_at_edit",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_req_revisions_requirement",
        "requirement_revisions",
        ["requirement_id"],
        unique=False,
    )
    op.create_index(
        "ix_req_revisions_actor",
        "requirement_revisions",
        ["actor_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_req_revisions_actor", table_name="requirement_revisions"
    )
    op.drop_index(
        "ix_req_revisions_requirement", table_name="requirement_revisions"
    )
    op.drop_table("requirement_revisions")
    op.drop_column("requirements", "updated_at")
