"""Migration smoke tests (CP07, extended by CP08).

Verifies that Alembic migrations reproduce the schema from scratch against a
fresh database.  A file-based SQLite database is used so that no external
Postgres dependency is required in CI.

The tests exercise the full env.py path: config loading, URL resolution,
async engine creation, the baseline migration (intentionally empty —
no application tables), and subsequent schema migrations.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command

API_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = API_ROOT / "alembic.ini"
ALEMBIC_DIR = API_ROOT / "alembic"

_BASELINE_REV = "0001_initial_baseline"
_HEAD_REV = "0035_worker_audit_actor"

# Tables introduced by CP08..CP58 migrations (one table per checkpoint).
_APP_TABLES = {
    "organizations", "users", "memberships", "audit_logs", "projects",
    "stored_objects", "tender_documents", "document_versions",
    "processing_runs", "document_pages", "extraction_runs",
    "extraction_candidates", "extraction_reconciliations",
    "requirements", "requirement_sources", "extraction_diagnostics",
    "requirement_constraints", "requirement_revisions",
    "requirement_relations", "requirement_notes", "categories",
    "requirement_categories", "export_artifacts",
    "extraction_window_audits",
    "oem_documents", "oem_document_versions",
    "oem_text_segments", "evidence", "evidence_locations",
    "vendor_specs", "compliance_assessments",
    "qualitative_assessments",
    "conflicts",
    "clarification_requests", "deviations",
    "assessment_comments", "submissions",
}


def _make_config(db_url: str) -> Config:
    """Build an Alembic Config pointed at ``db_url`` and our script location."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def test_upgrade_head_creates_version_table(tmp_path):
    """``alembic upgrade head`` runs against a fresh SQLite database."""
    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert "alembic_version" in tables
    engine.dispose()


def test_upgrade_head_creates_app_tables(tmp_path):
    """``alembic upgrade head`` creates all application tables on a fresh DB."""
    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert _APP_TABLES.issubset(tables)
    candidate_columns = {
        column["name"] for column in inspector.get_columns("extraction_candidates")
    }
    assert "verbatim_validation" in candidate_columns
    window_audit_columns = {
        column["name"] for column in inspector.get_columns("extraction_window_audits")
    }
    assert {
        "coverage_status",
        "coverage_error_category",
        "potential_omissions",
    }.issubset(window_audit_columns)
    engine.dispose()


def test_upgrade_head_records_head_revision(tmp_path):
    """After ``upgrade head`` the head revision is the recorded version."""
    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _HEAD_REV
    engine.dispose()


def test_upgrade_head_seeds_reserved_worker_audit_actor(tmp_path) -> None:
    """Fresh databases contain the user row required by worker audit FKs."""
    from tender_compliance_worker.processor import WORKER_ACTOR_ID

    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        worker = conn.execute(
            text(
                "SELECT auth_provider, auth_provider_user_id, full_name "
                "FROM users WHERE id = :worker_id"
            ),
            {"worker_id": WORKER_ACTOR_ID.hex},
        ).one()
    assert worker == (
        "system",
        "tender-compliance-document-worker",
        "Tender Compliance document worker",
    )
    engine.dispose()


def test_worker_actor_migration_downgrade_removes_its_reserved_identity(
    tmp_path,
) -> None:
    """The migration down/up cycle manages only its reserved system identity."""
    from tender_compliance_worker.processor import WORKER_ACTOR_ID

    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    command.downgrade(config, "0034_obligation_coverage_audit")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        worker_count: int = conn.execute(
            text("SELECT count(*) FROM users WHERE id = :worker_id"),
            {"worker_id": WORKER_ACTOR_ID.hex},
        ).scalar_one()
    assert worker_count == 0
    engine.dispose()


def test_migration_history_has_single_head():
    """Migration history resolves to a single, unambiguous head."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [_HEAD_REV]


def test_varchar_backed_enum_columns_do_not_request_native_postgres_types() -> None:
    """ORM enum adapters match columns created as VARCHAR by migrations."""
    from sqlalchemy import Enum as SqlAlchemyEnum

    from tender_compliance_api.db.models import Base

    varchar_backed_columns = {
        "assessment_comments.comment_type",
        "clarification_requests.status",
        "compliance_assessments.status",
        "compliance_assessments.suggested_status",
        "conflicts.resolution",
        "deviations.deviation_type",
        "deviations.status",
        "export_artifacts.export_format",
        "export_artifacts.status",
        "extraction_runs.status",
        "qualitative_assessments.verdict",
        "requirement_constraints.normalization_state",
        "requirement_relations.relation_type",
        "requirements.review_state",
        "submissions.status",
        "vendor_specs.extraction_method",
        "vendor_specs.normalization_state",
    }

    for qualified_name in varchar_backed_columns:
        table_name, column_name = qualified_name.split(".")
        column_type = Base.metadata.tables[table_name].columns[column_name].type
        assert isinstance(column_type, SqlAlchemyEnum), qualified_name
        assert not column_type.native_enum, qualified_name


def test_upgrade_downgrade_upgrade_roundtrip(tmp_path):
    """A full upgrade -> downgrade -> upgrade cycle reproduces the schema.

    Verifies that downgrading to base clears the version and that
    re-upgrading restores it deterministically.
    """
    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _HEAD_REV
    engine.dispose()
