import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TokenStore:
    """Persists a single rotating secret value (e.g. an OAuth refresh token)."""

    def get(self, key):
        raise NotImplementedError

    def set(self, key, value):
        raise NotImplementedError


class MemoryTokenStore(TokenStore):
    """
    In-process only. Used when no writable persistent location is
    configured or available -- notably Streamlit Community Cloud, which
    does not expose writable persistent storage for secrets. A rotated
    token survives for the life of the running process only; it is lost on
    restart/redeploy, and the operator must refresh DIGIKEY_REFRESH_TOKEN
    through the host's secret manager if that happens.
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
    - DIGIKEY_TOKEN_STORE=memory, or no .env file and no explicit setting
      (e.g. Streamlit Community Cloud): in-process only. Documented as
      non-persistent across restarts -- see MemoryTokenStore.
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
        return MemoryTokenStore()

    return MemoryTokenStore()
