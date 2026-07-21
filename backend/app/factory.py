"""FastAPI application factory.

Phase 0 wires only the shell: CORS for the Vite dev server, the health route,
and the auth stub. Domain routers (Programs, Projects, BOMs, Builds, buckets,
receiving, …) mount here in later phases via `include_router`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.health import router as health_router
from api.suppliers import router as suppliers_router
from api.bootstrap import router as bootstrap_router
from api.sourcing import router as sourcing_router
from api.boms import router as boms_router
from api.entities import router as entities_router
from api.inventory import router as inventory_router
from api.purchasing import router as purchasing_router
from auth.routes import router as auth_router

log = logging.getLogger("autobom")


def _configure_logging() -> None:
    """Make AutoBOM's own logging work under ANY ASGI runner.

    This used to live only in main.py, so `uvicorn app.factory:app` (or gunicorn,
    or a container entrypoint) started the app with the autobom.* loggers at the
    root default — silently swallowing every INFO line: supplier call traces,
    DigiKey token refreshes, and the purchasing sheet's console-fallback rows.
    The sheet fallback exists precisely so the batch is inspectable without
    touching Josh's real workbook; invisible logs defeat it.

    Attach a handler to the 'autobom' logger itself (not the root) so we never
    fight uvicorn's own logging configuration.
    """
    lvl = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    log.setLevel(lvl)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        log.addHandler(h)
    log.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings.status()
    log.info("AutoBOM backend starting — mode=%s auth=%s graph=%s db=%s",
             s["mode"], s["auth"], s["graph_sheet_writer"], s["database"])
    log.info("Suppliers configured: %s", s["suppliers"])
    yield


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="AutoBOM Backend",
        version="0.1.0",
        description="Local-first, Azure-ready backend for AutoBOM.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All API routes live under /api so the Vite dev server can proxy one prefix.
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(suppliers_router, prefix="/api")
    app.include_router(bootstrap_router, prefix="/api")
    app.include_router(sourcing_router, prefix="/api")
    app.include_router(boms_router, prefix="/api")
    app.include_router(entities_router, prefix="/api")
    app.include_router(inventory_router, prefix="/api")
    app.include_router(purchasing_router, prefix="/api")

    return app


app = create_app()
