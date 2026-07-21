"""DigiKey 3-legged (user) token manager — the MyLists auth path.

Why this module exists
----------------------
The previous inline implementation (`DigiKeyClient.get_user_access_token`) had
three failure modes that made a manual re-auth inevitable:

1. **Refresh-token rotation race.** DigiKey ROTATES the refresh token on every
   exchange — the old one dies the moment a new one is issued. The old code did
   a full exchange on *every* MyLists request (`headers()` is called per call),
   so a flush that created a list and added parts burned two rotations back to
   back, and two concurrent calls would race and invalidate each other. That is
   how the token ended up `401 Invalid RefreshToken`.
2. **Static-token shadowing.** A `DIGIKEY_ACCESS_TOKEN` in .env was returned
   forever with no expiry check, so once it aged out (~30 min) every call 401'd
   and the working refresh path was never even tried.
3. **No reactive refresh.** Nothing retried a 401 with a fresh token.

This module fixes all three: ONE exchange, cached until shortly before expiry,
rotation persisted immediately under a lock, shared across processes via a
small cache file, and an explicit `invalidate()` for reactive 401 retry.

The refresh token is the durable credential — if it is lost, a human must
re-authorize via `backend/scripts/digikey_oauth_setup.py`. Everything here is
built around never losing it.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from services.supplier_base import http_request

log = logging.getLogger("autobom.digikey.userauth")

REPO_ROOT = Path(__file__).resolve().parents[2]
# Shared across processes so a second worker reuses the live token instead of
# triggering another rotation. Holds a bearer token -> .cache/ is gitignored.
TOKEN_CACHE_PATH = REPO_ROOT / ".cache" / "digikey_user_token.json"

# Refresh this far before actual expiry so an in-flight flush never straddles it.
EARLY_REFRESH_SECONDS = 120
# DigiKey user access tokens are ~30 min; only used if expires_in is absent.
DEFAULT_TTL_SECONDS = 1800


def _mask(token: str | None) -> str:
    return f"...{token[-4:]}" if token and len(token) > 4 else "(none)"


class DigiKeyUserAuth:
    """Thread-safe, process-wide 3-legged token cache with rotation persistence."""

    def __init__(self):
        self._lock = threading.RLock()
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._last_error: Optional[str] = None
        self._last_refresh_at: Optional[float] = None
        self._load_disk_cache()

    # --- properties read live from env so a re-auth mid-session takes effect --
    @property
    def dry_run(self) -> bool:
        return os.getenv("SUPPLIER_DRY_RUN", "true").strip().lower() == "true"

    @property
    def refresh_token(self) -> str:
        return os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip()

    @property
    def static_token(self) -> str:
        """Manual override. Only honored when there is NO refresh token — a
        static token cannot self-heal, so it must never shadow the refresh path."""
        return os.getenv("DIGIKEY_ACCESS_TOKEN", "").strip()

    # --- disk cache (cross-process token sharing) ---------------------------
    def _load_disk_cache(self) -> None:
        try:
            data = json.loads(TOKEN_CACHE_PATH.read_text())
        except (OSError, ValueError):
            return
        # Only trust the cache if it belongs to the refresh token we hold now.
        if data.get("refresh_fingerprint") != self._fingerprint():
            return
        if float(data.get("expires_at", 0)) > time.time() + EARLY_REFRESH_SECONDS:
            self._token = data.get("access_token")
            self._expires_at = float(data["expires_at"])
            log.debug("digikey user token loaded from disk cache %s", _mask(self._token))

    def _save_disk_cache(self) -> None:
        try:
            TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_CACHE_PATH.write_text(json.dumps({
                "access_token": self._token,
                "expires_at": self._expires_at,
                "refresh_fingerprint": self._fingerprint(),
            }))
        except OSError as exc:                       # cache is an optimization
            log.debug("could not write digikey token cache: %s", exc)

    def _fingerprint(self) -> str:
        rt = self.refresh_token
        return rt[-8:] if len(rt) > 8 else ""

    # --- main entry point ---------------------------------------------------
    def token(self, force_refresh: bool = False) -> str:
        if self.dry_run:
            return "dry-run-token"
        with self._lock:
            if not force_refresh and self._token and time.time() < self._expires_at - EARLY_REFRESH_SECONDS:
                return self._token
            if not self.refresh_token:
                if self.static_token:
                    log.warning("Using static DIGIKEY_ACCESS_TOKEN — it cannot self-refresh "
                                "and will 401 once it expires. Run digikey_oauth_setup.py.")
                    return self.static_token
                self._last_error = "no refresh token"
                raise ValueError(
                    "DigiKey MyLists requires 3-legged OAuth. Set DIGIKEY_REFRESH_TOKEN "
                    "(run backend/scripts/digikey_oauth_setup.py) after authorizing this app."
                )
            return self._exchange()

    def _exchange(self) -> str:
        """Trade the refresh token for an access token, persisting the rotation.

        Caller must hold the lock. The rotated refresh token is written to .env
        BEFORE the access token is handed out: if the process died in between we
        would otherwise be holding a dead refresh token with no way back.
        """
        current = self.refresh_token
        from services.digikey_auth import _token_url
        resp = http_request(
            "POST", _token_url(), supplier="digikey-user-auth",
            data={
                "client_id": os.getenv("DIGIKEY_CLIENT_ID", "").strip(),
                "client_secret": os.getenv("DIGIKEY_CLIENT_SECRET", "").strip(),
                "refresh_token": current,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30,
        )
        if resp.status_code >= 400:
            detail = (resp.text or "").strip()[:300]
            self._last_error = f"{resp.status_code} {detail}"
            if "invalid_grant" in detail or resp.status_code in (400, 401):
                raise RuntimeError(
                    "DigiKey refresh token is no longer valid (it expires after ~90 days of "
                    "disuse, and is invalidated if a rotation was lost). Re-authorize with: "
                    f"python backend/scripts/digikey_oauth_setup.py — detail: {detail}"
                )
            raise RuntimeError(f"DigiKey user token request failed: {resp.status_code} {detail}")

        data = resp.json()
        token = data.get("access_token")
        if not token:
            self._last_error = "no access_token in response"
            raise ValueError("DigiKey did not return a user access token.")

        rotated = (data.get("refresh_token") or "").strip()
        if rotated and rotated != current:
            persist_refresh_token(rotated)           # persist BEFORE using
            log.info("DigiKey refresh token rotated -> %s (persisted)", _mask(rotated))

        self._token = token
        self._expires_at = time.time() + int(data.get("expires_in", DEFAULT_TTL_SECONDS) or DEFAULT_TTL_SECONDS)
        self._last_refresh_at = time.time()
        self._last_error = None
        self._save_disk_cache()
        log.info("DigiKey user token refreshed %s (valid %ds)", _mask(token),
                 int(self._expires_at - time.time()))
        return token

    def invalidate(self) -> None:
        """Drop the cached access token so the next call re-exchanges (401 path)."""
        with self._lock:
            self._token = None
            self._expires_at = 0.0
            try:
                TOKEN_CACHE_PATH.unlink(missing_ok=True)
            except OSError:
                pass

    # --- observability (Admin system status) --------------------------------
    def status(self) -> dict:
        with self._lock:
            expires_in = int(self._expires_at - time.time()) if self._token else 0
            if self.dry_run:
                state = "dry_run"
            elif not self.refresh_token and not self.static_token:
                state = "not_configured"
            elif not self.refresh_token:
                state = "static_token_no_refresh"
            elif self._last_error:
                state = "error"
            else:
                state = "ok"
            return {
                "state": state,
                "canSelfRefresh": bool(self.refresh_token),
                "cached": bool(self._token),
                "expiresInSeconds": max(0, expires_in),
                "lastRefreshAt": self._last_refresh_at,
                "lastError": self._last_error,
            }


def persist_refresh_token(value: str) -> bool:
    """Write the rotated refresh token back to .env.

    Appends when the key is absent — the previous helper silently no-op'd in
    that case, which would drop a rotation on the floor and lock us out.
    """
    env_path = REPO_ROOT / ".env"
    try:
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        for i, line in enumerate(lines):
            if line.strip().startswith("#") or "=" not in line:
                continue
            if line.split("=", 1)[0].strip() == "DIGIKEY_REFRESH_TOKEN":
                lines[i] = f"DIGIKEY_REFRESH_TOKEN={value}"
                break
        else:
            lines.append(f"DIGIKEY_REFRESH_TOKEN={value}")
        env_path.write_text("\n".join(lines) + "\n")
    except OSError as exc:
        log.error("FAILED to persist rotated DigiKey refresh token: %s — the next "
                  "refresh will fail and need a manual re-auth.", exc)
        return False
    os.environ["DIGIKEY_REFRESH_TOKEN"] = value      # in-process view stays current
    return True


_singleton: Optional[DigiKeyUserAuth] = None
_singleton_lock = threading.Lock()


def get_user_auth() -> DigiKeyUserAuth:
    """Process-wide shared cache — one exchange serves every MyLists call."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = DigiKeyUserAuth()
    return _singleton


def reset_user_auth() -> None:
    """Test hook — drop the singleton so env changes take effect."""
    global _singleton
    with _singleton_lock:
        _singleton = None
