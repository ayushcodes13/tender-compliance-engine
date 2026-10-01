"""Add RequirementConstraint + normalization state enum (CP32).

One row per structured value (parameter/operator/numeric-or-lower/upper bounds,
unit, tolerance, qualitative condition) carried by a persisted Requirement.
Multiple constraints may attach to one requirement. Stored alongside its
verbatim ``raw_fragment`` so every structured value is auditable against its
source. Normalization state starts ``unnormalized`` (CP33/CP34 populate parsed
fields + transition the state). No document bodies; Phase 1 only.

``normalization_state`` is stored as a VARCHAR (SQLite-compatible, mirroring
CP30 review_state/location_type and CP26 extraction_runs.status) — the ORM
``Enum(..., name=...)`` maps the Python enum to/from string values.

Revision ID: 0014_extraction_constraints
Revises: 0013_extraction_diagnostics
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_extraction_constraints"
down_revision: str | None = "0013_extraction_diagnostics"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_constraints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requirement_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("parameter", sa.String(length=128), nullable=False),
        sa.Column("operator", sa.String(length=16), nullable=True),
        sa.Column("numeric_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("lower_bound", sa.Numeric(18, 6), nullable=True),
        sa.Column("upper_bound", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("tolerance", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "qualitative_condition", sa.String(length=512), nullable=True
        ),
        sa.Column(
            "normalization_state",
            sa.String(length=32),
            nullable=False,
            server_default="unnormalized",
        ),
        sa.Column("raw_fragment", sa.String(length=2048), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_requirement_constraints_requirement",
        "requirement_constraints",
        ["requirement_id"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_constraints_version",
        "requirement_constraints",
        ["document_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirement_constraints_version",
        table_name="requirement_constraints",
    )
    op.drop_index(
        "ix_requirement_constraints_requirement",
        table_name="requirement_constraints",
    )
    op.drop_table("requirement_constraints")
    # No separate ENUM type was created (stored as VARCHAR); nothing to drop.
