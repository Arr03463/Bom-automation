"""Session tokens — signed, stateless, same in both auth modes.

A session is a signed JSON blob (itsdangerous) carrying the user id and the
active role, delivered as an HttpOnly cookie. Signed with SESSION_SECRET.
"""

from __future__ import annotations

from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import settings

COOKIE_NAME = "autobom_session"
MAX_AGE_SECONDS = 60 * 60 * 12  # 12h


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="autobom.session")


def issue(user_id: str, active_role: Optional[str]) -> str:
    return _serializer().dumps({"uid": user_id, "role": active_role})


def read(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        return _serializer().loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def cookie_kwargs() -> dict:
    """Consistent cookie flags. secure=True only in production (HTTPS)."""
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.is_production,
        "max_age": MAX_AGE_SECONDS,
        "path": "/",
    }
