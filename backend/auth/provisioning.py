"""Azure-mode login: role sourcing, auto-provision, read-through cache refresh.

Runs ONLY in production/Azure mode (creds present). On each SSO login:
  1. Read the user's Azure AD group memberships (auth/azure_groups).
  2. Map AutoBOM-* groups -> roles.
  3. No AutoBOM-* group -> reject (no access).
  4. Refresh users.roles (read-through cache), set role_source='azure_group',
     last_role_sync=now, capture azure_ad_object_id.
  5. If the user doesn't exist yet, auto-provision them.

users.roles is NEVER authoritative in Azure mode — it's a cache of AD truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth.azure_groups import roles_for_user
from auth.seed_users import AuthResult, landing_role
from db.models import RoleSource, User


@dataclass
class AzureClaims:
    oid: str            # Azure AD user object id
    email: str
    name: Optional[str] = None


def _new_user_id(email: str) -> str:
    # Deterministic local id from the email local-part; azure_ad_object_id is the
    # real cross-system key.
    local = email.split("@", 1)[0].replace(".", "-")
    return f"u-{local}"


def login_azure_user(db: Session, claims: AzureClaims) -> AuthResult:
    roles = roles_for_user(claims.oid)
    if not roles:
        return AuthResult(
            ok=False,
            error="You don't have AutoBOM access — contact your admin to add you to an AutoBOM-* group.",
        )

    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.azure_ad_object_id == claims.oid))
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == claims.email.lower()))

    if user is None:
        # Auto-provision.
        user = User(
            id=_new_user_id(claims.email),
            name=claims.name or claims.email,
            email=claims.email,
            roles=roles,
            primary_role=roles[0],
            overrides=[],
            active=True,
            role_source=RoleSource.azure_group.value,
            azure_ad_object_id=claims.oid,
            last_role_sync=now,
        )
        db.add(user)
    else:
        # Refresh the read-through cache from AD truth.
        user.roles = roles
        if not user.primary_role or user.primary_role not in roles:
            user.primary_role = roles[0]
        user.role_source = RoleSource.azure_group.value
        user.azure_ad_object_id = claims.oid
        user.last_role_sync = now

    db.flush()
    return AuthResult(ok=True, user=user, active_role=landing_role(user))
