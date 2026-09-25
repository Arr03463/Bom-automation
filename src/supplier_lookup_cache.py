import json
import os
import uuid
from pathlib import Path

from file_lock import FileLock as _FileLock
from file_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, LOCK_STALE_SECONDS
from manufacturer_aliases import normalize_manufacturer, normalize_part_number


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = PROJECT_ROOT / ".cache" / "supplier_lookup_cache.json"


def default_cache_path():
    """
    AUTOBOM_CACHE_ROOT lets a deployment put runtime cache data outside
    the source checkout, the same way AUTOBOM_RUNS_ROOT does for run
    directories (see run_workspace.resolve_runs_root()). The more
    specific SUPPLIER_LOOKUP_CACHE_PATH (an exact file path, pre-existing)
    still takes priority when set -- this only changes the *default* used
    when that isn't.
    """
    cache_root = os.getenv("AUTOBOM_CACHE_ROOT", "").strip()
    if cache_root:
        return Path(cache_root) / "supplier_lookup_cache.json"
    return DEFAULT_CACHE_PATH


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
        self.path = Path(os.getenv("SUPPLIER_LOOKUP_CACHE_PATH", str(default_cache_path())))
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

        lock = _FileLock(self.path, timeout=_lock_timeout_seconds())
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
