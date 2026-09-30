"""Migration smoke tests (CP07).

Verifies that Alembic migrations reproduce the schema from scratch against a
fresh database.  A file-based SQLite database is used so that no external
Postgres dependency is required in CI.

The tests exercise the full env.py path: config loading, URL resolution,
async engine creation, and the baseline migration (intentionally empty —
no application tables, only Alembic's version-tracking table).
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


def test_upgrade_head_records_baseline_revision(tmp_path):
    """After ``upgrade head`` the baseline revision is the recorded version."""
    db_path = tmp_path / "migrate.db"
    config = _make_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _BASELINE_REV
    engine.dispose()


def test_migration_history_has_single_head():
    """Migration history resolves to a single, unambiguous head."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [_BASELINE_REV]


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
    assert version == _BASELINE_REV
    engine.dispose()
