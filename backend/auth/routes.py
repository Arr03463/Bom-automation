"""Auth routes — /api/auth/*. Same UX in both modes; only the source differs.

Local mode  (settings.azure_enabled False): seed-user email login.
Azure mode  (settings.azure_enabled True):  Microsoft SSO + AD-group role sourcing.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import azure_ad
from auth import session as session_mod
from auth.deps import current_user, get_session, user_public
from auth.provisioning import AzureClaims, login_azure_user
from auth.seed_users import authenticate_by_email, landing_role
from config import settings
from db.models import User
from db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user: User, active_role: Optional[str]) -> None:
    token = session_mod.issue(user.id, active_role)
    response.set_cookie(value=token, **session_mod.cookie_kwargs())


@router.get("/login")
def login(db: Session = Depends(get_db)):
    """Describe the login mode. Azure -> the Microsoft auth URL to redirect to.
    Seed -> the three login accounts the picker can offer."""
    cfg = azure_ad.get_config()
    if cfg is not None:
        state = secrets.token_urlsafe(16)
        return {"mode": "azure", "authUrl": azure_ad.authorization_url(cfg, state)}
    # Seed mode: surface the login-capable users (roles non-empty).
    users = db.scalars(select(User).where(User.active.is_(True))).all()
    login_users = [
        {"id": u.id, "name": u.name, "email": u.email, "role": (u.roles or [None])[0]}
        for u in users if (u.roles or [])
    ]
    return {"mode": "seed", "users": login_users}


@router.post("/login")
def login_seed(response: Response, email: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Seed-user login. Rejected in Azure mode (SSO is the only path there)."""
    if azure_ad.get_config() is not None:
        raise HTTPException(status_code=400, detail="Seed login is disabled in Azure mode; use Microsoft SSO.")
    result = authenticate_by_email(db, email)
    if not result.ok:
        raise HTTPException(status_code=401, detail=result.error)
    _set_session_cookie(response, result.user, result.active_role)
    return user_public(result.user, result.active_role)


@router.get("/callback")
def callback(request: Request, code: str, db: Session = Depends(get_db)):
    """Azure SSO redirect target. Exchange code -> claims -> provision/refresh."""
    cfg = azure_ad.get_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail="Azure SSO is not configured.")
    tokens = azure_ad.exchange_code(cfg, code)
    claims = tokens.get("id_token_claims", {}) or {}
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn")
    oid = claims.get("oid")
    if not oid or not email:
        raise HTTPException(status_code=400, detail="Azure token missing oid/email claims.")
    result = login_azure_user(db, AzureClaims(oid=oid, email=email, name=claims.get("name")))
    if not result.ok:
        db.rollback()
        raise HTTPException(status_code=403, detail=result.error)
    db.commit()
    redirect = RedirectResponse(url=settings.frontend_url, status_code=302)
    _set_session_cookie(redirect, result.user, result.active_role)
    return redirect


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(session_mod.COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/role")
def switch_role(
    response: Response,
    role: str = Body(..., embed=True),
    user: Optional[User] = Depends(current_user),
):
    """Switch the active role, scoped to roles the user actually holds."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if role not in (user.roles or []):
        raise HTTPException(status_code=403, detail="You don't hold that role.")
    _set_session_cookie(response, user, role)
    return user_public(user, role)


@router.get("/me")
def me(request: Request, user: Optional[User] = Depends(current_user)):
    if user is None:
        return {"user": None, "auth_mode": "azure-ad" if settings.azure_enabled else "seed-users"}
    sess = get_session(request) or {}
    active = sess.get("role") or landing_role(user)
    return {"user": user_public(user, active), "auth_mode": "azure-ad" if settings.azure_enabled else "seed-users"}
