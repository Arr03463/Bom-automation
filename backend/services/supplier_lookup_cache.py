import json
import os
import time
from pathlib import Path

from services.manufacturer_aliases import normalize_manufacturer, normalize_part_number


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = PROJECT_ROOT / ".cache" / "supplier_lookup_cache.json"
DEFAULT_TTL_SECONDS = 21600  # 6 hours


class SupplierLookupCache:
    def __init__(self):
        self.enabled = os.getenv("SUPPLIER_LOOKUP_CACHE_ENABLED", "true").lower() == "true"
        self.path = Path(os.getenv("SUPPLIER_LOOKUP_CACHE_PATH", str(DEFAULT_CACHE_PATH)))
        self.ttl_seconds = int(
            os.getenv("SUPPLIER_LOOKUP_CACHE_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
        )
        self.data = {}
        self.dirty = False

        if self.enabled:
            self.load()

    def load(self):
        if not self.path.exists():
            self.data = {}
            return

        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.data = {}

    def get(self, key):
        if not self.enabled:
            return None

        entry = self.data.get(key)
        if entry is None:
            return None

        cached_at = entry.get("cached_at", 0) if isinstance(entry, dict) else 0

        if time.time() - cached_at < self.ttl_seconds:
            return entry.get("value") if isinstance(entry, dict) else entry

        # Stale entry: treat as a miss and drop it from the cache.
        del self.data[key]
        self.dirty = True
        return None

    def set(self, key, value):
        if not self.enabled or value is None:
            return

        self.data[key] = {"value": value, "cached_at": time.time()}
        self.dirty = True

    def save(self):
        if not self.enabled or not self.dirty:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
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
