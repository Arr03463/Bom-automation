"""Seed-user authentication (local/dev mode).

Mirrors the prototype's store.logIn exactly. In dev mode the ONLY accounts that
can log in are the three single-role login users (Designer / Production / Admin).
Every other seed user is inert referential data (roles == []) so foreign keys
resolve and the demo looks alive — but they are not login accounts.

Azure AD / Graph is NEVER called in this path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import User


@dataclass
class AuthResult:
    ok: bool
    user: Optional[User] = None
    active_role: Optional[str] = None
    error: Optional[str] = None


def landing_role(user: User) -> Optional[str]:
    roles = user.roles or []
    if user.primary_role and user.primary_role in roles:
        return user.primary_role
    return roles[0] if roles else None


def authenticate_by_email(db: Session, email: str) -> AuthResult:
    e = (email or "").strip().lower()
    if not e:
        return AuthResult(ok=False, error="Enter your work email.")
    user = db.scalar(select(User).where(func.lower(User.email) == e))
    if not user:
        return AuthResult(ok=False, error="We don't recognize that email. Try a seed user.")
    if not user.active:
        return AuthResult(ok=False, error="This account is deactivated. Contact an administrator.")
    if not (user.roles or []):
        # Inert referential user — resolvable record, but not a login account.
        return AuthResult(ok=False, error="This account has no AutoBOM role — it isn't a login account.")
    return AuthResult(ok=True, user=user, active_role=landing_role(user))
