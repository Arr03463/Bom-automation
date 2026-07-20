"""Capability model — backend port of frontend permissions.jsx.

Two layers (unchanged from the prototype):
  L1 — role defaults (CAPS[role])
  L2 — user-level additive overrides (user.overrides)

Only the four VALID_ROLES exist here. Legacy manager/readonly/executive are
gone: no capability logic ever encounters a legacy role string. Development caps
stay defined but are only reachable by a user whose roles include 'development'
(gated by DEV_ROLE_ENABLED at the seed/sourcing layer).
"""

from __future__ import annotations

# Role -> default capabilities (mirrors CAPS in permissions.jsx, valid roles only).
CAPS: dict[str, set[str]] = {
    "designer": {
        "collection.create", "collection.edit", "collection.requestOrder",
        "part.search", "part.addToCollection", "bom.respondException",
        "comment", "project.create",
    },
    "production": {
        "part.search", "bom.upload", "bom.validate", "bom.editLine", "bom.runSourcing",
        "bom.sendException", "bom.createPackage", "bom.submitToPurchasing",
        "dev.handshake.respond", "comment", "project.create",
    },
    "development": {
        "part.search",
        "dev.collection.create", "dev.collection.edit", "dev.collection.generateOutcome",
        "dev.investigation.create", "dev.recommendation.create",
        "dev.rework.create", "dev.firmware.create",
        "dev.handshake.send", "dev.handshake.respond",
        "comment",
    },
    "admin": {
        "admin.users", "admin.roles", "admin.permissions", "admin.workflow",
        "admin.suppliers", "admin.settings", "admin.audit", "admin.override", "comment",
    },
}


def effective_caps(roles: list[str] | None, overrides: list[str] | None) -> list[str]:
    """Resolve the effective capability set for a user (one or more roles +
    additive overrides). Unknown/legacy role strings contribute nothing."""
    caps: set[str] = set()
    for r in roles or []:
        caps |= CAPS.get(r, set())
    for c in overrides or []:
        caps.add(c)
    return sorted(caps)


def can(cap: str, roles: list[str] | None, overrides: list[str] | None = None) -> bool:
    return cap in effective_caps(roles, overrides)
