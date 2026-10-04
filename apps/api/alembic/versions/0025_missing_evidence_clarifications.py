"""CP57 — Missing evidence, clarification questions, and deviations.

Adds two tables:

``clarification_requests`` — tracks questions posed when evidence is
insufficient or ambiguous, or when a conflict has been detected that
requires human input before a compliance assessment can proceed.

``deviations`` — records when a vendor specification or proposal
deviates from the original tender requirement (different scope, value
out-of-range, missing capability, etc.).
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_missing_evidence_clarifications"
down_revision: str | None = "0024_conflict_detection"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Alembic creates its internal version column as VARCHAR(32) by default.
    # This repository predates the PostgreSQL production smoke test and this
    # revision identifier is 36 characters long. Widen the version column
    # before Alembic records this revision so a fresh PostgreSQL migration
    # chain can continue without rewriting historical revision identifiers.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )

    # —  — clarification_requests —  —
    op.create_table(
        "clarification_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "requirement_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "question",
            sa.String(2048),
            nullable=False,
        ),
        sa.Column(
            "context",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "related_evidence_ids",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "related_conflict_ids",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "asked_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "answer",
            sa.String(4096),
            nullable=True,
        ),
        sa.Column(
            "answered_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Index(
            "ix_clarification_requests_project", "project_id"
        ),
        sa.Index(
            "ix_clarification_requests_requirement", "requirement_id"
        ),
        sa.Index(
            "ix_clarification_requests_status", "status"
        ),
    )

    # —  — deviations —  —
    op.create_table(
        "deviations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "requirement_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "deviation_type",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "original_requirement",
            sa.String(2048),
            nullable=False,
        ),
        sa.Column(
            "proposed_alternative",
            sa.String(2048),
            nullable=True,
        ),
        sa.Column(
            "rationale",
            sa.String(2048),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column(
            "proposed_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "reviewed_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "review_notes",
            sa.String(2048),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Index(
            "ix_deviations_project", "project_id"
        ),
        sa.Index(
            "ix_deviations_requirement", "requirement_id"
        ),
        sa.Index(
            "ix_deviations_status", "status"
        ),
    )


def downgrade() -> None:
    op.drop_table("deviations")
    op.drop_table("clarification_requests")
