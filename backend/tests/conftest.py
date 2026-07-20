"""Pytest fixtures — run against the dedicated autobom_test Postgres DB.

DATABASE_URL is forced to the test DB BEFORE any backend module imports (so the
engine binds to it). Each test gets a clean, isolated schema.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make backend/ importable and pin the test DB before importing backend modules.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/autobom_test",
)
# Ensure local/seed auth mode during tests (no Azure).
for _k in ("AZURE_AD_CLIENT_ID", "AZURE_AD_CLIENT_SECRET", "AZURE_TENANT_ID"):
    os.environ.pop(_k, None)

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.base import Base  # noqa: E402
import db.models  # noqa: F401,E402  (register tables)
from db.session import engine  # noqa: E402


@pytest.fixture(autouse=True)
def clean_schema():
    """Every test starts on a freshly created schema (via metadata)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Session:
    """Session wrapped in an outer transaction + savepoint, so even commits made
    inside the test (e.g. seed_all) are rolled back afterwards."""
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()
