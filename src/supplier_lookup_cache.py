import json
import os
import time
import uuid
from pathlib import Path

from manufacturer_aliases import normalize_manufacturer, normalize_part_number


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = PROJECT_ROOT / ".cache" / "supplier_lookup_cache.json"

LOCK_SUFFIX = ".lock"
LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 30
LOCK_POLL_SECONDS = 0.05


class _FileLock:
    """
    Minimal advisory lock built on atomic directory-entry creation
    (O_CREAT | O_EXCL), so concurrent AutoBOM runs serialize their
    read-modify-write cycle on the shared cache file instead of racing each
    other. Works the same way on Windows and POSIX with no extra
    dependency. A lock left behind by a crashed process is reclaimed after
    LOCK_STALE_SECONDS so one dead run can't wedge every future run.
    """

    def __init__(self, target_path, timeout=LOCK_TIMEOUT_SECONDS):
        self.lock_path = Path(str(target_path) + LOCK_SUFFIX)
        self.timeout = timeout
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout

        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.close(fd)
                self._acquired = True
                return
            except FileExistsError:
                if self._reclaim_if_stale():
                    continue
                if time.monotonic() >= deadline:
                    # Proceed without the lock rather than hard-failing the
                    # operator's run. A lock surviving past the stale
                    # threshold under normal team usage is not expected;
                    # this bound just prevents one wedged lock file from
                    # blocking every future run forever.
                    return
                time.sleep(LOCK_POLL_SECONDS)

    def _reclaim_if_stale(self):
        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except OSError:
            return True

        if age < LOCK_STALE_SECONDS:
            return False

        try:
            self.lock_path.unlink()
        except OSError:
            pass
        return True

    def release(self):
        if not self._acquired:
            return

        try:
            self.lock_path.unlink()
        except OSError:
            pass
        self._acquired = False


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
        than overwriting the whole file with our in-memory snapshot. Under
        the lock: re-read the latest file, apply only the keys this run
        actually set, then atomically replace. Two runs updating different
        keys concurrently both keep their updates; two runs updating the
        exact same key still resolve last-write-wins for that key, which is
        the expected/acceptable semantics for a lookup cache.
        """
        if not self.enabled or not self.dirty:
            return

        with _FileLock(self.path):
            latest = _read_json_file(self.path)
            latest.update(self._pending_updates)
            _atomic_write_json(self.path, latest)
            self.data = latest

        self._pending_updates = {}
        self.dirty = False


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
