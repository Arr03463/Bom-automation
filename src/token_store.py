import contextlib
import os
from pathlib import Path

import requests

from file_lock import FileLock

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The operation this lock protects (DigiKeyClient.get_user_access_token()'s
# read-refresh-write cycle) includes a single HTTP POST with a 30s request
# timeout. The stale-reclaim threshold must stay comfortably longer than
# that so a legitimately slow-but-live refresh is never mistaken for an
# abandoned lock and reclaimed by a second waiter mid-request -- 4x the
# request timeout is a simple, conservative margin, not a distributed-lock
# scheme.
TOKEN_LOCK_STALE_SECONDS = 120


class TokenStoreError(Exception):
    """
    Raised by a TokenStore backend when it cannot durably read/write a
    value -- a network failure, an unreachable host, an auth failure
    against the store itself, etc. Deliberately distinct from returning
    None: None means "no token has ever been stored here", while this
    means "the store could not be reached and we don't actually know".
    Callers must not treat the two the same way (see
    DigiKeyClient._current_refresh_token()).
    """


class TokenStore:
    """Persists a single rotating secret value (e.g. an OAuth refresh token)."""

    def get(self, key):
        raise NotImplementedError

    def set(self, key, value):
        raise NotImplementedError

    def lock(self, timeout=None):
        """
        Context manager serializing a read-refresh-write cycle across
        concurrent callers. Backends with no real cross-process
        contention (in-process memory) or no supported coordination
        primitive (a generic HTTPS key/value endpoint) return a no-op --
        see the class docstrings below for what actually protects each
        backend against a lost update.
        """
        return contextlib.nullcontext()


class MemoryTokenStore(TokenStore):
    """
    In-process only. Used when no writable persistent location is
    configured or available -- notably Streamlit Community Cloud, which
    does not expose writable persistent storage for secrets. A rotated
    token survives for the life of the running process only; it is lost on
    restart/redeploy, and the operator must refresh DIGIKEY_REFRESH_TOKEN
    through the host's secret manager if that happens.

    Single-process by construction (see
    _get_shared_memory_token_store), so there is no concurrent-writer
    scenario for lock() to protect against.
    """

    def __init__(self, initial=None):
        self._values = dict(initial or {})

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value):
        self._values[key] = value
        return True


class EnvFileTokenStore(TokenStore):
    """
    Rewrites a KEY=value line in a local .env file. Appropriate for local
    development against a writable, non-shared working copy of the
    repository. Never appropriate for a hosted multi-user deployment,
    since the file is shared repository state and the host filesystem may
    not be writable at all.
    """

    def __init__(self, env_path=None):
        self.env_path = Path(env_path) if env_path else PROJECT_ROOT / ".env"

    def get(self, key):
        if not self.env_path.exists():
            return None

        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue

            existing_key, _, value = line.partition("=")
            if existing_key.strip() == key:
                return value.strip()

        return None

    def set(self, key, value):
        lines = (
            self.env_path.read_text(encoding="utf-8").splitlines()
            if self.env_path.exists()
            else []
        )

        for index, line in enumerate(lines):
            if line.strip().startswith("#") or "=" not in line:
                continue

            existing_key, _ = line.split("=", 1)
            if existing_key.strip() == key:
                lines[index] = f"{key}={value}"
                self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True

        lines.append(f"{key}={value}")
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    def lock(self, timeout=None):
        return FileLock(self.env_path, timeout=timeout, stale_after=TOKEN_LOCK_STALE_SECONDS)


class FileTokenStore(TokenStore):
    """
    Writes each key to its own file under a directory outside the
    repository working tree -- e.g. a mounted persistent volume that some
    hosts (but not Streamlit Community Cloud) provide. Not tied to any
    specific hosting platform.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def get(self, key):
        path = self.directory / key
        if not path.exists():
            return None

        value = path.read_text(encoding="utf-8").strip()
        return value or None

    def set(self, key, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / key
        tmp_path = path.with_suffix(path.suffix + ".tmp")

        tmp_path.write_text(str(value), encoding="utf-8")
        os.replace(str(tmp_path), str(path))
        return True

    def lock(self, timeout=None):
        self.directory.mkdir(parents=True, exist_ok=True)
        # One shared lock file per directory (not per key): today there is
        # exactly one key in practice (DIGIKEY_REFRESH_TOKEN), and a
        # per-directory lock is simpler than inventing per-key lock paths.
        return FileLock(
            self.directory / "_rotation", timeout=timeout, stale_after=TOKEN_LOCK_STALE_SECONDS
        )


class HttpTokenStore(TokenStore):
    """
    Generic HTTPS key-value backend for hosts with no writable persistent
    filesystem (e.g. Streamlit Community Cloud). Deliberately vendor-
    agnostic: it PUTs/GETs a JSON {"value": ...} body against
    f"{base_url}/{key}" with a bearer token, which is the shape most small
    hosted key-value/secrets services expose. Picking an actual service is
    a deployment decision for the team (see
    Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md) -- this class
    only needs that shape to exist somewhere reachable over HTTPS.

    Failures raise TokenStoreError rather than returning None, so a
    network/auth problem with the store is never confused with "nothing
    has been stored yet" (see DigiKeyClient._current_refresh_token()).

    lock() is a no-op here: coordinating a lock against a generic HTTP
    endpoint would require assuming a specific conditional-write/ETag
    capability this class does not assume any particular vendor provides.
    If the chosen backend supports conditional writes, a subclass can
    override lock() to use them. Absent that, DigiKey's own rejection of
    an already-used refresh token is the safety net against a lost race
    (see get_user_access_token()) -- a losing process gets a clear,
    surfaced error instead of silently corrupting the stored token.
    """

    def __init__(self, base_url=None, api_key=None, timeout=10):
        self.base_url = (base_url or os.getenv("DIGIKEY_TOKEN_STORE_URL", "")).strip().rstrip("/")
        self.api_key = api_key or os.getenv("DIGIKEY_TOKEN_STORE_API_KEY", "").strip()
        self.timeout = timeout

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get(self, key):
        if not self.base_url:
            raise TokenStoreError("DIGIKEY_TOKEN_STORE_URL is not configured.")

        try:
            response = requests.get(
                f"{self.base_url}/{key}", headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise TokenStoreError(f"Token store request failed: {exc}") from exc

        if response.status_code == 404:
            return None

        if response.status_code >= 400:
            raise TokenStoreError(f"Token store returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise TokenStoreError("Token store returned a non-JSON response.") from exc

        if isinstance(payload, dict):
            return payload.get("value")
        return None

    def set(self, key, value):
        if not self.base_url:
            raise TokenStoreError("DIGIKEY_TOKEN_STORE_URL is not configured.")

        try:
            response = requests.put(
                f"{self.base_url}/{key}",
                headers=self._headers(),
                json={"value": value},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TokenStoreError(f"Token store request failed: {exc}") from exc

        if response.status_code >= 400:
            raise TokenStoreError(f"Token store returned HTTP {response.status_code}.")

        return True


# A single MemoryTokenStore, lazily created and reused for the life of the
# process. Every DigiKeyClient() built without an explicit token_store
# calls build_token_store(); if each call returned a fresh
# MemoryTokenStore(), a rotated token set by one client instance would be
# invisible to the next one constructed a moment later, even though both
# are running in the very same process. This module-level handle is the
# token_store abstraction's own internal state (not an unrelated
# application global) -- it exists specifically to give the "memory"
# backend the process-lifetime persistence its name promises.
_shared_memory_token_store = None


def _get_shared_memory_token_store():
    global _shared_memory_token_store
    if _shared_memory_token_store is None:
        _shared_memory_token_store = MemoryTokenStore()
    return _shared_memory_token_store


def reset_shared_memory_token_store():
    """Clear the process-wide memory store. Exposed for tests; also usable
    if an operator ever needs to force-drop an in-memory token by hand."""
    global _shared_memory_token_store
    _shared_memory_token_store = None


def build_token_store():
    """
    Backend selection, generic across local and hosted use:

    - DIGIKEY_TOKEN_STORE=env_file (optionally with DIGIKEY_TOKEN_STORE_ENV_PATH
      to target a non-default .env location): rewrite the local .env file
      (today's behavior). This is also the default when a local .env file
      exists, so local development keeps working with no configuration
      change.
    - DIGIKEY_TOKEN_STORE=file (with DIGIKEY_TOKEN_STORE_PATH=<dir>): for a
      host that provides a writable persistent directory outside the repo.
    - DIGIKEY_TOKEN_STORE=http (with DIGIKEY_TOKEN_STORE_URL and
      DIGIKEY_TOKEN_STORE_API_KEY): for a host with no writable persistent
      filesystem at all (e.g. Streamlit Community Cloud) -- see
      HttpTokenStore and
      Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md.
    - DIGIKEY_TOKEN_STORE=memory, or no .env file and no explicit setting:
      in-process only, shared across every DigiKeyClient() built in this
      process (see _get_shared_memory_token_store). Documented as
      non-persistent across restarts.
    """
    backend = os.getenv("DIGIKEY_TOKEN_STORE", "").strip().lower()
    env_file_path = os.getenv("DIGIKEY_TOKEN_STORE_ENV_PATH", "").strip()
    resolved_env_path = Path(env_file_path) if env_file_path else PROJECT_ROOT / ".env"

    if not backend:
        backend = "env_file" if resolved_env_path.exists() else "memory"

    if backend == "env_file":
        return EnvFileTokenStore(resolved_env_path)

    if backend == "file":
        directory = os.getenv("DIGIKEY_TOKEN_STORE_PATH", "").strip()
        if directory:
            return FileTokenStore(directory)
        return _get_shared_memory_token_store()

    if backend == "http":
        base_url = os.getenv("DIGIKEY_TOKEN_STORE_URL", "").strip()
        if base_url:
            return HttpTokenStore(base_url=base_url)
        return _get_shared_memory_token_store()

    return _get_shared_memory_token_store()
