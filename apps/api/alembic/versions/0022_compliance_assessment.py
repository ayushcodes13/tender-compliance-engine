"""CP54 — ComplianceAssessment model and status semantics.

Adds the ``compliance_assessments`` table for deterministic system
assessments of tender requirements against vendor evidence.

Design:
* Every assessment is tied to a ``requirement`` and optionally an
  ``evidence`` / ``vendor_spec`` row.  ``evidence_id`` and
  ``vendor_spec_id`` are nullable (NOT_DEMONSTRATED has no evidence).
* ``suggested_status`` is the system's deterministic verdict; ``status``
  is the final (human-confirmed or same-as-suggested) status.
* Assessments are versioned: new evidence/specs → new row with incremented
  ``assessment_version`` (never modifies previous rows — append-only).
* ``comparison_result_json`` stores the full CP53 ComparisonResult for
  auditability — every status is traceable to its inputs.
* ``is_confirmed_by_human`` separates system suggestion from final approval.
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_compliance_assessment"
down_revision: str | None = "0021_vendor_spec_extraction"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_assessments",
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
            "vendor_spec_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("vendor_specs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "suggested_status",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("reason_text", sa.String(2048), nullable=True),
        sa.Column("comparison_result_json", sa.JSON(), nullable=True),
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
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "requirement_id",
            "assessment_version",
            name="uq_compliance_assessments_requirement_version",
        ),
        sa.Index(
            "ix_compliance_assessments_project", "project_id"
        ),
        sa.Index(
            "ix_compliance_assessments_requirement", "requirement_id"
        ),
        sa.Index(
            "ix_compliance_assessments_status", "status"
        ),
    )


def downgrade() -> None:
    op.drop_table("compliance_assessments")
