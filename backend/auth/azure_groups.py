"""Azure AD group -> AutoBOM role sourcing (READ path).

The SINGLE module owning Group access. Azure AD groups are the source of truth
for who has which role in production; AutoBOM's `users.roles` is a read-through
cache refreshed from here on each login (Azure mode only).

Phase 1 = READ ONLY. The future write path (manage group membership from
AutoBOM's Admin UI) is purely additive:
  - group name -> id resolution (`resolve_group_id`) is built now and reused
    unchanged for member writes;
  - `azure_ad_object_id` is captured on users now for later member-write calls;
  - add_member/remove_member land on the shared GraphClient later.
No schema or auth-flow change is needed to add writes.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import settings
from db.models import VALID_ROLES
from integrations.microsoft_graph import get_client

log = logging.getLogger("autobom.auth.groups")


def _role_for_group(display_name: str) -> Optional[str]:
    role = settings.azure_group_role_map.get(display_name)
    if role and role in VALID_ROLES:
        return role
    return None


def resolve_group_id(display_name: str) -> Optional[str]:
    """Group displayName -> object id. Needed to read members today and reused
    unchanged for member writes later. Returns None if Graph is unconfigured or
    the group doesn't exist."""
    client = get_client()
    if client is None:
        return None
    groups = client.get_all(
        "/groups",
        params={"$filter": f"displayName eq '{display_name}'", "$select": "id,displayName"},
    )
    return groups[0]["id"] if groups else None


def roles_for_user(azure_ad_object_id: str) -> list[str]:
    """Read the user's Azure AD group memberships and map AutoBOM-* groups to
    roles. Only VALID_ROLES are returned; unknown groups are ignored. Development
    is filtered out unless DEV_ROLE_ENABLED (kept off in Phase 1).

    Returns [] if Graph is unconfigured (caller decides how to handle)."""
    client = get_client()
    if client is None:
        return []
    # transitiveMemberOf catches nested group membership.
    memberships = client.get_all(
        f"/users/{azure_ad_object_id}/transitiveMemberOf/microsoft.graph.group",
        params={"$select": "id,displayName"},
    )
    roles: list[str] = []
    for g in memberships:
        role = _role_for_group(g.get("displayName", ""))
        if role and role not in roles:
            roles.append(role)
    dev_on = _dev_enabled()
    if not dev_on:
        roles = [r for r in roles if r != "development"]
    return roles


def _dev_enabled() -> bool:
    # Mirrors the frontend DEV_ROLE_ENABLED flag; off in Phase 1.
    import os
    return os.getenv("DEV_ROLE_ENABLED", "false").lower() == "true"
