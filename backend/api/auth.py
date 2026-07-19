"""Auth routes — Phase 0 stub.

Only the shape exists here. Phase 1 implements the graceful-fallback auth:
seed-user login when `settings.azure_enabled` is False, Microsoft SSO when it's
True — same login/session/logout UX either way. Until then the prototype keeps
running its own client-side seed auth (store.jsx), so `/api/auth/me` reports no
server session yet.
"""

from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me() -> dict:
    # No server-side session in Phase 0. The frontend prototype still drives
    # login locally; this endpoint gets its real body in Phase 1.
    return {"user": None, "auth_mode": "azure-ad" if settings.azure_enabled else "seed-users"}
