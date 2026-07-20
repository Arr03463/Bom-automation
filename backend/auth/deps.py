"""FastAPI auth dependencies."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth import session as session_mod
from auth.permissions import effective_caps
from db.models import User
from db.session import get_db


def get_session(request: Request) -> Optional[dict]:
    return session_mod.read(request.cookies.get(session_mod.COOKIE_NAME))


def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    sess = get_session(request)
    if not sess:
        return None
    return db.get(User, sess.get("uid"))


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def user_public(user: User, active_role: Optional[str] = None) -> dict:
    """Serialize a user for the frontend, including effective capabilities."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles or [],
        "primaryRole": user.primary_role,
        "overrides": user.overrides or [],
        "activeRole": active_role,
        "caps": effective_caps(user.roles, user.overrides),
        "roleSource": user.role_source,
        "active": user.active,
    }
