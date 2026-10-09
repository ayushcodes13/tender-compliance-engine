"""Persist append-only reviewer decisions for coverage findings.

Revision ID: 0037_coverage_finding_reviews
Revises: 0036_unbounded_clause_labels
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0037_coverage_finding_reviews"
down_revision: str | None = "0036_unbounded_clause_labels"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "coverage_finding_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_quote_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "decision IN ('covered_by_requirement', 'not_in_scope')",
            name="ck_coverage_finding_reviews_decision",
        ),
    )
    op.create_index(
        "ix_coverage_finding_reviews_version_finding",
        "coverage_finding_reviews",
        ["document_version_id", "page_number", "source_quote_sha256", "created_at"],
    )
    op.create_index(
        "ix_coverage_finding_reviews_actor",
        "coverage_finding_reviews",
        ["actor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_coverage_finding_reviews_actor", table_name="coverage_finding_reviews")
    op.drop_index(
        "ix_coverage_finding_reviews_version_finding",
        table_name="coverage_finding_reviews",
    )
    op.drop_table("coverage_finding_reviews")
