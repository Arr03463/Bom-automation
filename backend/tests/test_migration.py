"""Alembic baseline migration builds the schema, and models match it (no drift)."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from db.base import Base
import db.models  # noqa: F401
from db.session import engine

BACKEND_DIR = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users", "programs", "projects", "boms", "bom_lines", "bom_versions", "builds",
    "collections", "collection_items", "requests", "batches", "cpn_issuance",
    "pushbacks", "notifications", "comments", "storage_location_metadata",
    "audit", "force_waivers", "configuration", "suppliers",
}


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "db" / "migrations"))
    return cfg


def _reset_to_empty():
    """Truly empty DB: drop the model tables AND alembic_version. The version
    table is not part of Base.metadata, so a stale stamp would otherwise make
    `upgrade head` a silent no-op and the schema would never be built."""
    from sqlalchemy import text
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_migration_upgrade_builds_all_tables():
    # Start truly clean so alembic builds from empty.
    _reset_to_empty()
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"

    # Stamped at the current head (0001 baseline + later incremental migrations).
    from alembic.script import ScriptDirectory
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        from sqlalchemy import text
        assert conn.execute(text("select version_num from alembic_version")).scalar() == head

    command.downgrade(cfg, "base")
    insp = inspect(engine)
    assert EXPECTED_TABLES.isdisjoint(set(insp.get_table_names()))


def test_models_match_migration_no_drift():
    """After upgrade head, the ORM metadata should match the DB (autogenerate
    would emit nothing)."""
    _reset_to_empty()
    command.upgrade(_alembic_config(), "head")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diffs = compare_metadata(ctx, Base.metadata)

    # Ignore any noise that isn't a real table/column add/remove.
    structural = [
        d for d in diffs
        if (isinstance(d, tuple) and d and d[0] in {
            "add_table", "remove_table", "add_column", "remove_column",
        })
    ]
    assert not structural, f"schema drift: {structural}"

    command.downgrade(_alembic_config(), "base")
