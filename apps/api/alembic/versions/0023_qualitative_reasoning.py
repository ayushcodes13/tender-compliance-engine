"""CP55 — Evidence-backed qualitative reasoning.

Adds the ``qualitative_assessments`` table for source-bounded qualitative
reasoning results that accompany the deterministic numeric comparisons from
CP53/CP54.  A qualitative assessment is produced only from cited, accepted
evidence — it never fabricates support and never re-evaluates numeric
verdicts (those remain authoritative).

Design:
* Tied to ``requirement`` and optionally to ``evidence`` and a
  ``compliance_assessment`` (the numeric result it augments).
* ``verdict`` is a ``QualitativeVerdict`` enum: support / mismatch /
  unsupported / conflict / insufficient_evidence / uncertain.
* ``attribution_mismatches`` JSON records entity / scope / condition
  mismatches between the requirement and the evidence.
* ``evidence_ids`` JSON records the UUIDs of every evidence item the
  reasoning consulted — nothing more.
* ``source_contradiction`` flags when multiple cited sources disagree.
* ``model_version``, ``prompt_version``, ``reasoning_version`` are recorded
  for reproducibility/auditability.
* Assessments are versioned (append-only): a new run creates a new row with
  incremented ``assessment_version``.
* ``is_confirmed_by_human`` separates system suggestion from final approval.
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_qualitative_reasoning"
down_revision: str | None = "0022_compliance_assessment"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "qualitative_assessments",
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
            "evidence_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("evidence.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "compliance_assessment_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("compliance_assessments.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "verdict",
            sa.String(32),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("reason_text", sa.String(2048), nullable=True),
        sa.Column(
            "attribution_mismatches",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "evidence_ids",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "source_contradiction",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "model_version",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "prompt_version",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "reasoning_version",
            sa.String(64),
            nullable=False,
        ),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column(
            "is_confirmed_by_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "reviewer_id",
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
        sa.UniqueConstraint(
            "requirement_id",
            "assessment_version",
            name="uq_qualitative_assessments_requirement_version",
        ),
        sa.Index(
            "ix_qualitative_assessments_project", "project_id"
        ),
        sa.Index(
            "ix_qualitative_assessments_requirement", "requirement_id"
        ),
        sa.Index(
            "ix_qualitative_assessments_verdict", "verdict"
        ),
        sa.Index(
            "ix_qualitative_assessments_compliance", "compliance_assessment_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("qualitative_assessments")
