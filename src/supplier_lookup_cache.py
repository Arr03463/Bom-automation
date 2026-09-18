import json
import os
import time
import uuid
from pathlib import Path

from manufacturer_aliases import normalize_manufacturer, normalize_part_number


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = PROJECT_ROOT / ".cache" / "supplier_lookup_cache.json"

LOCK_SUFFIX = ".lock"
DEFAULT_LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 30
LOCK_POLL_SECONDS = 0.05


def _lock_timeout_seconds():
    try:
        return float(
            os.getenv(
                "SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS",
                DEFAULT_LOCK_TIMEOUT_SECONDS,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_LOCK_TIMEOUT_SECONDS


class _FileLock:
    """
    Minimal advisory lock built on atomic directory-entry creation
    (O_CREAT | O_EXCL), so concurrent AutoBOM runs serialize their
    read-modify-write cycle on the shared cache file instead of racing each
    other. Works the same way on Windows and POSIX with no extra
    dependency.

    acquire() returns True/False rather than proceeding either way -- a
    caller must never treat a timed-out acquire as if it held the lock.

    Each holder writes a random owner token into the lock file. release()
    and stale reclamation both re-check that token before deleting the
    lock file, so a process can never delete a lock that a *different*
    holder currently owns (e.g. a lock this instance considered stale and
    already lost to a successor that re-acquired it).
    """

    def __init__(self, target_path, timeout=None):
        self.lock_path = Path(str(target_path) + LOCK_SUFFIX)
        self.timeout = timeout if timeout is not None else _lock_timeout_seconds()
        self._owner_token = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def acquired(self):
        return self._owner_token is not None

    def acquire(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        owner_token = f"{os.getpid()}:{uuid.uuid4().hex}"

        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, owner_token.encode("utf-8"))
                finally:
                    os.close(fd)
                self._owner_token = owner_token
                return True
            except FileExistsError:
                self._reclaim_if_stale()
                if time.monotonic() >= deadline:
                    # Give up without ever claiming ownership. The caller
                    # must treat this as "no lock" and skip the operation
                    # that required exclusivity -- never proceed as if
                    # locked.
                    return False
                time.sleep(LOCK_POLL_SECONDS)

    def _reclaim_if_stale(self):
        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except OSError:
            return

        if age < LOCK_STALE_SECONDS:
            return

        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def _current_owner_token(self):
        try:
            return self.lock_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def release(self):
        if self._owner_token is None:
            return

        # Only remove the lock file if it still holds the token we wrote.
        # If it holds a different token, this lock was reclaimed as stale
        # and re-acquired by another holder while we still thought we
        # owned it -- deleting it now would drop that holder's lock out
        # from under it.
        if self._current_owner_token() == self._owner_token:
            try:
                self.lock_path.unlink()
            except OSError:
                pass

        self._owner_token = None


def _read_json_file(path):
    path = Path(path)
    if not path.exists():
        return {}

    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")

    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.replace(str(tmp_path), str(path))
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


class SupplierLookupCache:
    def __init__(self):
        self.enabled = os.getenv("SUPPLIER_LOOKUP_CACHE_ENABLED", "true").lower() == "true"
        self.path = Path(os.getenv("SUPPLIER_LOOKUP_CACHE_PATH", str(DEFAULT_CACHE_PATH)))
        self.data = {}
        self._pending_updates = {}
        self.dirty = False

        if self.enabled:
            self.load()

    def load(self):
        self.data = _read_json_file(self.path)

    def get(self, key):
        if not self.enabled:
            return None
        return self.data.get(key)

    def set(self, key, value):
        if not self.enabled or value is None:
            return

        self.data[key] = value
        self._pending_updates[key] = value
        self.dirty = True

    def save(self):
        """
        Merge this run's updates into whatever is currently on disk rather
        than overwriting the whole file with our in-memory snapshot: under
        the lock, re-read the latest file, apply only the keys this run
        actually set, then atomically replace. Two runs updating different
        keys concurrently both keep their updates; two runs updating the
        exact same key still resolve last-write-wins for that key, which is
        the expected/acceptable semantics for a lookup cache.

        The read-merge-write is only ever performed while this call holds
        the lock. If the lock cannot be acquired within the timeout,
        persistence for this run is skipped entirely -- the sourcing
        result already computed in memory is unaffected, and this run's
        pending updates are simply not written to disk. Returns True if
        the cache was persisted, False if the save was skipped (disabled,
        nothing pending, or lock timeout).
        """
        if not self.enabled or not self.dirty:
            return False

        lock = _FileLock(self.path)
        if not lock.acquire():
            return False

        try:
            latest = _read_json_file(self.path)
            latest.update(self._pending_updates)
            _atomic_write_json(self.path, latest)
            self.data = latest
        except OSError:
            # A write failure (disk full, permissions, etc.) must not fail
            # the BOM run that already computed a correct sourcing result
            # in memory -- the cache is an optimization, not a
            # correctness dependency.
            return False
        finally:
            lock.release()

        self._pending_updates = {}
        self.dirty = False
        return True


def build_lookup_key(supplier_name, row):
    manufacturer = normalize_manufacturer(row.get("manufacturer", ""))
    mpn = normalize_part_number(row.get("mpn", ""))
    supplier_part_number = normalize_part_number(row.get("supplier_part_number", ""))

    return "|".join(
        [
            str(supplier_name or "").strip().lower(),
            manufacturer,
            mpn,
            supplier_part_number,
        ]
    )
