"""CP58 — Human compliance review and audit.

Adds the ``assessment_comments`` table, which stores reviewer comments and
notes attached to a specific ``ComplianceAssessment`` (CP54) version.

This migration is additive — it does NOT modify the append-only
``compliance_assessments`` table.  Override/reopen/versioning semantics are
implemented in the service layer by creating new assessment rows, not by
schema changes.
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_human_review_audit"
down_revision: str | None = "0025_missing_evidence_clarifications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "assessment_comments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("compliance_assessments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "author_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "comment_type",
            sa.String(32),
            nullable=False,
            server_default="comment",
        ),
        sa.Column(
            "comment",
            sa.String(4096),
            nullable=False,
        ),
        sa.Column(
            "assessment_version",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Index(
            "ix_assessment_comments_assessment", "assessment_id"
        ),
        sa.Index(
            "ix_assessment_comments_project", "project_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("assessment_comments")
