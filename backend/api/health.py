"""Health + capability status endpoint.

`GET /api/health` is what Phase 0 verification hits to confirm the backend is
up, and it doubles as the local-vs-azure mode indicator (no secrets exposed).
"""

from fastapi import APIRouter

from config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "autobom-backend", **settings.status()}
