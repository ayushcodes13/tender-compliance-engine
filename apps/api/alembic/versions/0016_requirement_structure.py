"""CP39 — Requirement structure: relations, categories, notes, display_order, mandatory, superseded.

Adds:
- ``requirement_relations`` table (SPLIT_INTO / MERGED_INTO / SUPERSEDES).
- ``requirement_notes`` table (reviewer notes persisted separately from normalized text).
- ``categories`` table (project-scoped hierarchical categories).
- ``requirement_categories`` association table (many-to-many Requirement <-> Category).
- Columns on ``requirements``: ``display_order`` (int nullable), ``mandatory``
  (bool nullable tri-state), ``superseded`` (bool default false).

Revision history: these columns are additive; existing rows get server
defaults (NULL for display_order/mandatory, FALSE for superseded) so the
migration is data-safe and reversible.

``relation_type`` uses a non-native enum (VARCHAR) so the migration is
SQLite-compatible in CI while the ORM ``Enum(RequirementRelationType,
name=...)`` maps the Python enum to/from string values.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0016_requirement_structure"
down_revision = "0015_requirement_revisions"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


# Non-native enum (VARCHAR on SQLite, native on PostgreSQL).
_RELATION_TYPE_ENUM = sa.Enum(
    "split_into",
    "merged_into",
    "supersedes",
    name="requirement_relation_type",
    native_enum=False,
)


def upgrade() -> None:
    # Add columns to requirements.
    op.add_column("requirements", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("requirements", sa.Column("mandatory", sa.Boolean(), nullable=True))
    op.add_column(
        "requirements",
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Create the relation_type enum type (idempotent).

    # Create requirement_relations table.
    op.create_table(
        "requirement_relations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_requirement_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_requirement_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relation_type",
            _RELATION_TYPE_ENUM,
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_req_relations_source", "requirement_relations", ["source_requirement_id"]
    )
    op.create_index(
        "ix_req_relations_target", "requirement_relations", ["target_requirement_id"]
    )
    op.create_index(
        "ix_req_relations_version", "requirement_relations", ["document_version_id"]
    )

    # Create requirement_notes table.
    op.create_table(
        "requirement_notes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requirement_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("text", sa.String(length=2048), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_req_notes_requirement", "requirement_notes", ["requirement_id"])
    op.create_index("ix_req_notes_actor", "requirement_notes", ["actor_id"])

    # Create categories table.
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_categories_project", "categories", ["project_id"])
    op.create_index("ix_categories_parent", "categories", ["parent_id"])

    # Create requirement_categories association table.
    op.create_table(
        "requirement_categories",
        sa.Column(
            "requirement_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_requirement_categories_category", "requirement_categories", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_requirement_categories_category", table_name="requirement_categories")
    op.drop_table("requirement_categories")
    op.drop_index("ix_categories_parent", table_name="categories")
    op.drop_index("ix_categories_project", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_req_notes_actor", table_name="requirement_notes")
    op.drop_index("ix_req_notes_requirement", table_name="requirement_notes")
    op.drop_table("requirement_notes")
    op.drop_index("ix_req_relations_version", table_name="requirement_relations")
    op.drop_index("ix_req_relations_target", table_name="requirement_relations")
    op.drop_index("ix_req_relations_source", table_name="requirement_relations")
    op.drop_table("requirement_relations")

    _RELATION_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)

    # Remove columns from requirements.
    with op.batch_alter_table("requirements") as batch:
        batch.drop_column("display_order")
        batch.drop_column("mandatory")
        batch.drop_column("superseded")
