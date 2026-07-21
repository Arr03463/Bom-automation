"""AutoBOM configuration — graceful-fallback loader.

Single source of truth for every environment-driven setting. The whole
local-first / Azure-ready story lives here: each Azure-facing capability is
gated on whether its credential holds a *real* value or a placeholder/empty.

Rule (from AutoBOM_Deployment_Readiness.md):
    "If the credential isn't set, fall back to a local behavior that doesn't
     need it. No branching config, no separate code paths — just 'does this
     env var have a real value or not.'"

Later phases import `settings` and ask e.g. `settings.graph_enabled` to decide
between the live Microsoft Graph write and the console-log fallback. The code
path is the same; only this flag differs.

Env var names follow the real repo `.env` + the Supplier API Integration Guide
(MOUSER_SEARCH_API_KEY, MOUSER_CART_API_KEY, DIGIKEY_CLIENT_ID/SECRET,
PARTSBOX_API_KEY) — NOT the deployment doc's older single-MOUSER_API_KEY sketch.
"""

from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

from dotenv import load_dotenv

# Repo root is one level up from backend/. The real .env lives there (same file
# the POC uses), so local dev shares one credential file.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Precedence (lowest → highest): the real process environment (e.g. Azure App
# Service settings) wins over everything, then `.env.local` (optional
# developer-local overrides) wins over the base `.env`.
#   - `.env`       : the local credential file (already present in this repo).
#   - `.env.local` : optional; override individual vars without editing `.env`.
load_dotenv(REPO_ROOT / ".env", override=False)          # base file
load_dotenv(REPO_ROOT / ".env.local", override=True)     # optional overrides win
# Note: load_dotenv never overrides vars already set in the real environment
# unless override=True AND the file defines them; process env set before start
# still takes ultimate precedence because we never override an unset-in-file var.

# Marker prefixes used by placeholder values in .env.example / templates.
# A value starting with any of these is treated as "not configured".
_PLACEHOLDER_PREFIXES = ("<paste", "<from", "<same", "<autogen", "<generate",
                         "<sheet", "<postgres", "<your", "changeme", "xxxx")


def is_real(value: str | None) -> bool:
    """True only when `value` is a usable credential, not empty/placeholder."""
    if value is None:
        return False
    v = value.strip()
    if not v:
        return False
    lowered = v.lower()
    return not any(lowered.startswith(p) for p in _PLACEHOLDER_PREFIXES)


def _get(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def mask(value: str | None) -> str:
    """Mask a secret to its last 4 chars for safe logging (never log full keys)."""
    if not value:
        return "<unset>"
    v = value.strip()
    return ("*" * max(0, len(v) - 4)) + v[-4:] if len(v) > 4 else "****"


class Settings:
    """Read-only view over the environment. Instantiated once as `settings`."""

    # ---- App / environment ---------------------------------------------------
    @property
    def env(self) -> str:
        return _get("ENV", "development") or "development"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def backend_url(self) -> str:
        return _get("BACKEND_URL", "http://localhost:8000")

    @property
    def frontend_url(self) -> str:
        return _get("FRONTEND_URL", "http://localhost:3000")

    @property
    def session_secret(self) -> str:
        return _get("SESSION_SECRET", "local-dev-secret-doesnt-matter")

    @property
    def cors_origins(self) -> list[str]:
        # Frontend dev server + configured frontend URL, de-duplicated.
        origins = {"http://localhost:3000", "http://127.0.0.1:3000", self.frontend_url}
        return [o for o in origins if o]

    # ---- Database ------------------------------------------------------------
    @property
    def database_url(self) -> str | None:
        url = _get("DATABASE_URL")
        return url if is_real(url) else None

    # ---- Azure AD / SSO (graceful fallback → seed users) ---------------------
    @cached_property
    def azure_enabled(self) -> bool:
        return all(is_real(_get(k)) for k in (
            "AZURE_AD_CLIENT_ID", "AZURE_AD_CLIENT_SECRET", "AZURE_TENANT_ID"))

    # ---- Microsoft Graph -----------------------------------------------------
    @cached_property
    def graph_configured(self) -> bool:
        """App-only Graph creds present (tenant/client/secret). Enough for
        reading Azure AD group memberships. Does NOT require the sheet id."""
        return all(is_real(_get(k)) for k in (
            "MICROSOFT_GRAPH_TENANT_ID", "MICROSOFT_GRAPH_CLIENT_ID",
            "MICROSOFT_GRAPH_CLIENT_SECRET"))

    @cached_property
    def graph_enabled(self) -> bool:
        """Full sheet-writer config: Graph creds + the purchasing workbook id.
        When False the purchasing sheet writer logs to console (graceful fallback)."""
        return self.graph_configured and is_real(_get("ONEDRIVE_PURCHASING_SHEET_ID"))

    # ---- Bucket flush (ONE switch, mirrors the azure_enabled pattern) --------
    @property
    def flush_mode(self) -> str:
        """dry_run (default) | live. The single production-readiness switch:
        add keys + flip this. Same code path in both modes."""
        return (_get("FLUSH_MODE", "dry_run") or "dry_run").strip().lower()

    @property
    def flush_live(self) -> bool:
        return self.flush_mode == "live"

    @property
    def legacy_flush_flags(self) -> dict:
        """Deprecated per-client flags — surfaced for visibility only. The
        orchestrator's dry_run decision is authoritative and is passed DOWN into
        the clients; these no longer control the flush."""
        return {
            "MOUSER_CART_DRY_RUN": _get("MOUSER_CART_DRY_RUN"),
            "SUPPLIER_DRY_RUN": _get("SUPPLIER_DRY_RUN"),
            "DIGIKEY_MYLISTS_ENABLED": _get("DIGIKEY_MYLISTS_ENABLED"),
        }

    # Azure AD group name -> AutoBOM role. Admin may override the naming later.
    @property
    def azure_group_role_map(self) -> dict:
        return {
            "AutoBOM-Designers": "designer",
            "AutoBOM-Production": "production",
            "AutoBOM-Admins": "admin",
            "AutoBOM-Development": "development",
        }

    # ---- Supplier / inventory APIs (same in local + Azure modes) -------------
    @cached_property
    def mouser_search_enabled(self) -> bool:
        return is_real(_get("MOUSER_SEARCH_API_KEY"))

    @cached_property
    def mouser_cart_enabled(self) -> bool:
        return is_real(_get("MOUSER_CART_API_KEY"))

    @cached_property
    def digikey_enabled(self) -> bool:
        return is_real(_get("DIGIKEY_CLIENT_ID")) and is_real(_get("DIGIKEY_CLIENT_SECRET"))

    @cached_property
    def partsbox_enabled(self) -> bool:
        return is_real(_get("PARTSBOX_API_KEY"))

    def status(self) -> dict:
        """Non-secret capability snapshot for /api/health and Admin observability.

        Never includes secret values — only whether each integration is live or
        running in local-fallback mode.
        """
        return {
            "env": self.env,
            "mode": "azure" if self.azure_enabled else "local",
            "database": "postgres" if self.database_url else "not-configured",
            "auth": "azure-ad" if self.azure_enabled else "seed-users",
            "graph_sheet_writer": "live" if self.graph_enabled else "console-fallback",
            "suppliers": {
                "mouser_search": self.mouser_search_enabled,
                "mouser_cart": self.mouser_cart_enabled,
                "digikey": self.digikey_enabled,
                "partsbox": self.partsbox_enabled,
            },
        }


settings = Settings()
