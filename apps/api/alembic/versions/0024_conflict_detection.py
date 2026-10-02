"""CP56 — Conflict and contradiction detection.

Adds the ``conflicts`` table for persistent, auditable conflict records
that result from comparing vendor facts across multiple OEM evidence sources
for the same tender requirement.

Design:
* ``conflict_type`` classifies the contradiction: ``parameter_value``
  (same parameter, different numeric values across evidence), ``concept_mismatch``
  (e.g. accuracy vs resolution for the same requirement), or
  ``tender_vendor`` (tender says CE-marked, evidence says not).
* ``sources`` JSON preserves ALL conflicting source descriptions — both/all
  conflicting claims are kept, never silently discarded.
* ``tender_claim`` preserves the relevant requirement text for side-by-side
  comparison.
* ``resolution`` is a ``ConflictResolution`` enum (unresolved / accepted /
  rejected) so reviewers can record their decision.
* ``requirement_id`` links the conflict back to the tender requirement so
  the matrix and compliance assessment can surface it.
"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_conflict_detection"
down_revision: str | None = "0023_qualitative_reasoning"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "conflicts",
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
            "conflict_type",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "parameter",
            sa.String(128),
            nullable=True,
        ),
        sa.Column(
            "entity",
            sa.String(256),
            nullable=True,
        ),
        # JSON array of source descriptors — each is a dict with
        # evidence_id, vendor_spec_id, source_text, value, unit, etc.
        # Preserves ALL conflicting sources.
        sa.Column(
            "sources",
            sa.JSON(),
            nullable=False,
        ),
        # The relevant requirement text — preserved for side-by-side review.
        sa.Column(
            "tender_claim",
            sa.String(2048),
            nullable=True,
        ),
        # Tender vendor spec ID — the spec that the conflict originates from.
        sa.Column(
            "tender_vendor_spec_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("vendor_specs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "resolution",
            sa.String(32),
            nullable=False,
            server_default="unresolved",
        ),
        sa.Column(
            "resolution_notes",
            sa.String(2048),
            nullable=True,
        ),
        sa.Column(
            "resolved_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_at",
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
            "ix_conflicts_requirement", "requirement_id"
        ),
        sa.Index(
            "ix_conflicts_type", "conflict_type"
        ),
        sa.Index(
            "ix_conflicts_resolution", "resolution"
        ),
    )


def downgrade() -> None:
    op.drop_table("conflicts")
