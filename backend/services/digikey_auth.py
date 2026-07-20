"""DigiKey OAuth token management (guide §2.2, §2.5).

The POC re-authenticated on essentially every run (a fresh DigiKeyClient per
call, no expiry tracking). This module fixes that: a thread-safe, process-wide
cache of the 2-legged (client-credentials) access token, refreshed proactively
~30s before its 10-minute expiry and reactively on a 401.

Sandbox vs production is selected by DIGIKEY_ENV (guide §1) unless explicit
DIGIKEY_BASE_URL / DIGIKEY_TOKEN_URL are set.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from services.supplier_base import http_request, raise_for_status

_PROD_HOST = "https://api.digikey.com"
_SANDBOX_HOST = "https://sandbox-api.digikey.com"


def _host() -> str:
    if os.getenv("DIGIKEY_BASE_URL", "").strip():
        return os.getenv("DIGIKEY_BASE_URL").strip()
    return _SANDBOX_HOST if os.getenv("DIGIKEY_ENV", "production").strip().lower() == "sandbox" else _PROD_HOST


def _token_url() -> str:
    if os.getenv("DIGIKEY_TOKEN_URL", "").strip():
        return os.getenv("DIGIKEY_TOKEN_URL").strip()
    return f"{_host()}/v1/oauth2/token"


class DigiKeyAuth:
    """Thread-safe 2-legged token cache."""

    def __init__(self):
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
        self.base_url = _host()
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def token(self, force_refresh: bool = False) -> str:
        if self.dry_run:
            return "dry-run-token"
        with self._lock:
            # Refresh ~30s before actual expiry, or when forced (post-401).
            if not force_refresh and self._token and time.time() < self._expires_at - 30:
                return self._token
            if not self.client_id or not self.client_secret:
                raise ValueError("Missing DigiKey credentials in .env")
            resp = http_request(
                "POST", _token_url(), supplier="digikey-auth",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            raise_for_status(resp, "DigiKey access token request failed")
            data = resp.json()
            self._token = data.get("access_token")
            if not self._token:
                raise ValueError("DigiKey did not return an access token.")
            self._expires_at = time.time() + int(data.get("expires_in", 600))
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = 0.0


_auth_singleton: Optional[DigiKeyAuth] = None
_singleton_lock = threading.Lock()


def get_auth() -> DigiKeyAuth:
    """Process-wide shared token cache (so the token is reused across clients)."""
    global _auth_singleton
    with _singleton_lock:
        if _auth_singleton is None:
            _auth_singleton = DigiKeyAuth()
    return _auth_singleton


def reset_auth() -> None:
    """Test hook — drop the singleton so env changes take effect."""
    global _auth_singleton
    with _singleton_lock:
        _auth_singleton = None
