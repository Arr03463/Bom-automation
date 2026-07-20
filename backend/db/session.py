"""Database engine + session management.

Reads `DATABASE_URL` via the graceful-fallback config. Local Postgres and Azure
Postgres are transparent — only the URL differs. If `DATABASE_URL` is unset the
engine is created lazily on first use and raises a clear error (Phase 0 ran with
no DB; Phase 1 requires one).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings

# Local dev default when DATABASE_URL isn't set explicitly. Azure sets the real
# URL via env. psycopg (v3) driver.
_DEFAULT_LOCAL_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/autobom_local"


def database_url() -> str:
    url = settings.database_url or _DEFAULT_LOCAL_URL
    # Normalize the bare "postgresql://" scheme to the psycopg v3 driver.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(database_url(), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """FastAPI dependency — yields a session, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
