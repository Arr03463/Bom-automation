"""Azure AD SSO (user login) — graceful fallback.

`get_config()` returns None when Azure AD creds are absent/placeholder → the
routes fall back to seed-user login. When present, it returns an MSAL config for
the authorization-code (3-legged) user sign-in flow.

This is the USER SSO path (who is signing in). Reading their group memberships
for role sourcing is a separate concern handled by auth/azure_groups.py via the
app-only Graph client. Both are gated by the same switch: settings.azure_enabled.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import msal

from config import settings

# Delegated scopes for user sign-in. openid/profile/email identify the user.
LOGIN_SCOPES = ["User.Read"]


@dataclass
class AzureADConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"


def get_config() -> Optional[AzureADConfig]:
    """None => local mode (seed users). A config => Azure SSO mode."""
    if not settings.azure_enabled:
        return None
    return AzureADConfig(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_AD_CLIENT_ID"],
        client_secret=os.environ["AZURE_AD_CLIENT_SECRET"],
        redirect_uri=os.getenv("AZURE_AD_REDIRECT_URI", f"{settings.backend_url}/api/auth/callback"),
    )


def _app(cfg: AzureADConfig) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        cfg.client_id, authority=cfg.authority, client_credential=cfg.client_secret
    )


def authorization_url(cfg: AzureADConfig, state: str) -> str:
    return _app(cfg).get_authorization_request_url(
        LOGIN_SCOPES, state=state, redirect_uri=cfg.redirect_uri
    )


def exchange_code(cfg: AzureADConfig, code: str) -> dict:
    """Exchange an auth code for tokens + id-token claims (incl. email, oid)."""
    result = _app(cfg).acquire_token_by_authorization_code(
        code, scopes=LOGIN_SCOPES, redirect_uri=cfg.redirect_uri
    )
    if "access_token" not in result:
        raise RuntimeError(f"Azure AD code exchange failed: {result.get('error_description', result.get('error'))}")
    return result
