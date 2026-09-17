import json
import os
from pathlib import Path

from manufacturer_aliases import normalize_manufacturer, normalize_part_number


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = PROJECT_ROOT / ".cache" / "supplier_lookup_cache.json"


class SupplierLookupCache:
    def __init__(self):
        self.enabled = os.getenv("SUPPLIER_LOOKUP_CACHE_ENABLED", "true").lower() == "true"
        self.path = Path(os.getenv("SUPPLIER_LOOKUP_CACHE_PATH", str(DEFAULT_CACHE_PATH)))
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
        return self.data.get(key)

    def set(self, key, value):
        if not self.enabled or value is None:
            return

        self.data[key] = value
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
