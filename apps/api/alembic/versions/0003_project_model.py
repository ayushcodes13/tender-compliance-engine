"""Add Project model and project_id on audit_logs (CP09).

Tables changed:

* ``projects`` — a tender-response workspace owned by an organization.
  ``status`` is a workflow enum (draft … archived) — **not** vendor
  compliance.  Phase 2 compliance assessment does not exist yet.
* ``audit_logs.project_id`` — nullable FK to ``projects.id`` so project-
  scoped events can be recorded.  Existing org-level events remain valid.

Migration notes:

* ``audit_logs.project_id`` is added via ``batch_alter_table`` because
  SQLite cannot add a foreign-key constraint with a standalone ``ALTER
  TABLE`` (Alembic's batch mode uses a copy-and-move strategy on SQLite
  and plain ``ALTER TABLE`` on PostgreSQL).

Revision ID: 0003_project_model
Revises: 0002_organization_identity_audit
Create Date: 2026-10-01

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_project_model"
down_revision: str | None = "0002_organization_identity_audit"
branch_labels: str | None = None
depends_on: str | None = None

_PROJECT_STATUS_ENUM = sa.Enum(
    "draft",
    "tender_uploaded",
    "documents_processing",
    "requirements_extracted",
    "review_in_progress",
    "matrix_ready",
    "exported",
    "archived",
    name="project_status",
)


def upgrade() -> None:
    """Create projects table and add project_id to audit_logs."""
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("external_tender_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            _PROJECT_STATUS_ENUM,
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_projects_organization_id"), "projects", ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_projects_org_status", "projects", ["organization_id", "status"],
        unique=False,
    )

    # audit_logs.project_id is nullable (org-level events may not have a project).
    # batch_alter_table is required on SQLite — standalone ALTER TABLE cannot
    # add a foreign-key constraint there.
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", sa.UUID(), nullable=True)
        )
        batch_op.create_index(
            op.f("ix_audit_logs_project_id"), ["project_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_audit_logs_project_id", "projects",
            ["project_id"], ["id"], ondelete="CASCADE",
        )


def downgrade() -> None:
    """Drop projects table and remove project_id from audit_logs."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint(
            "fk_audit_logs_project_id", type_="foreignkey"
        )
        batch_op.drop_index(op.f("ix_audit_logs_project_id"))
        batch_op.drop_column("project_id")

    op.drop_index("ix_projects_org_status", table_name="projects")
    op.drop_index(op.f("ix_projects_organization_id"), table_name="projects")
    op.drop_table("projects")

    _PROJECT_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
