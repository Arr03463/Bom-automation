import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from sourcing_engine import (
    SUPPLIER_CACHE_SCHEMA_VERSION,
    SupplierResult,
    _supplier_result_to_cache,
    source_row,
)
from supplier_lookup_cache import SupplierLookupCache, build_lookup_key


class SupplierCacheValidityTests(unittest.TestCase):
    """
    Regression coverage for Q3 (no expiration / cache key omits
    required_qty) and Q4 (a malformed cache entry suppresses a valid
    live lookup) from
    Documentation/AutoBOM_QAQC_State_Cache_Deep_Dive_Report.md.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_cache_validity_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self._old_env = {
            "SUPPLIER_LOOKUP_CACHE_ENABLED": os.environ.get("SUPPLIER_LOOKUP_CACHE_ENABLED"),
            "SUPPLIER_LOOKUP_CACHE_PATH": os.environ.get("SUPPLIER_LOOKUP_CACHE_PATH"),
        }
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "true"
        os.environ["SUPPLIER_LOOKUP_CACHE_PATH"] = str(self.temp_dir / "supplier_lookup_cache.json")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, old_value in self._old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    def _row(self, required_qty="10"):
        return {
            "mpn": "ABC123",
            "manufacturer": "Yageo",
            "supplier_part_number": "",
            "required_qty": required_qty,
        }

    def _mouser_result(self, stock=500, supplier_part_number="603-CACHED"):
        return SupplierResult(
            supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=stock,
            supplier_part_number=supplier_part_number,
        )

    def test_unexpired_cache_entry_is_reused_without_a_live_lookup(self):
        row = self._row()
        cache = SupplierLookupCache()
        cache.set(build_lookup_key("mouser", row), _supplier_result_to_cache(self._mouser_result()))

        calls = []
        decision = source_row(
            row,
            lambda r: calls.append(r) or self._mouser_result(stock=1),
            lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(len(calls), 0)
        self.assertEqual(decision["supplier_part_number"], "603-CACHED")

    def test_expired_cache_entry_triggers_a_live_lookup(self):
        row = self._row()
        cache = SupplierLookupCache()
        key = build_lookup_key("mouser", row)
        stale_entry = _supplier_result_to_cache(self._mouser_result())
        stale_entry["cached_at"] = 0.0  # the Unix epoch -- always older than any TTL.
        cache.set(key, stale_entry)

        calls = []

        def mouser_lookup(r):
            calls.append(r)
            return self._mouser_result(stock=999, supplier_part_number="603-FRESH")

        decision = source_row(
            row, mouser_lookup, lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["supplier_part_number"], "603-FRESH")

    def test_old_schema_entry_without_version_wrapper_fails_open_to_live_lookup(self):
        """
        A cache file written before this schema-version/TTL wrapper
        existed stores the bare asdict() shape directly -- must not be
        misinterpreted as a fresh, valid entry.
        """
        row = self._row()
        cache = SupplierLookupCache()
        cache.set(build_lookup_key("mouser", row), {
            "supplier": "Mouser", "manufacturer": "Yageo", "mpn": "ABC123",
            "stock": 500, "supplier_part_number": "603-OLD-SCHEMA",
        })

        calls = []

        def mouser_lookup(r):
            calls.append(r)
            return self._mouser_result(stock=999, supplier_part_number="603-FRESH")

        decision = source_row(
            row, mouser_lookup, lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["supplier_part_number"], "603-FRESH")

    def test_wrong_schema_version_fails_open_to_live_lookup(self):
        row = self._row()
        cache = SupplierLookupCache()
        entry = _supplier_result_to_cache(self._mouser_result())
        entry["schema_version"] = SUPPLIER_CACHE_SCHEMA_VERSION + 1
        cache.set(build_lookup_key("mouser", row), entry)

        calls = []
        decision = source_row(
            row,
            lambda r: calls.append(r) or self._mouser_result(stock=999, supplier_part_number="603-FRESH"),
            lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["supplier_part_number"], "603-FRESH")

    def test_malformed_value_payload_fails_open_to_live_lookup_not_a_false_no_match(self):
        """Q4: extra/incompatible fields inside the wrapped value must
        not be treated as a confirmed 'supplier has no match'."""
        row = self._row()
        cache = SupplierLookupCache()
        entry = _supplier_result_to_cache(self._mouser_result())
        entry["value"] = {"this_is_not": "a_valid_supplier_result_shape"}
        cache.set(build_lookup_key("mouser", row), entry)

        calls = []
        decision = source_row(
            row,
            lambda r: calls.append(r) or self._mouser_result(stock=999, supplier_part_number="603-FRESH"),
            lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["selected_supplier"], "Mouser")
        self.assertEqual(decision["supplier_part_number"], "603-FRESH")

    def test_a_successful_live_lookup_overwrites_a_malformed_persistent_entry(self):
        row = self._row()
        cache = SupplierLookupCache()
        key = build_lookup_key("mouser", row)
        entry = _supplier_result_to_cache(self._mouser_result())
        entry["value"] = {"garbage": True}
        cache.set(key, entry)

        source_row(
            row, lambda r: self._mouser_result(stock=999, supplier_part_number="603-FRESH"), lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(cache.get(key)["value"]["supplier_part_number"], "603-FRESH")

    def test_different_required_quantities_do_not_share_a_cached_result(self):
        row_small_qty = self._row(required_qty="1")
        row_large_qty = self._row(required_qty="1000")

        cache = SupplierLookupCache()
        cache.set(
            build_lookup_key("mouser", row_small_qty),
            _supplier_result_to_cache(self._mouser_result(stock=1, supplier_part_number="603-SMALL-QTY")),
        )

        calls = []

        def mouser_lookup(r):
            calls.append(r)
            return self._mouser_result(stock=5000, supplier_part_number="603-LARGE-QTY")

        decision = source_row(
            row_large_qty, mouser_lookup, lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        # A cache entry for qty=1 must never be reused for qty=1000 --
        # a fresh, quantity-aware lookup is required.
        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["supplier_part_number"], "603-LARGE-QTY")
        self.assertEqual(decision["selected_supplier"], "Mouser")

    def test_configurable_ttl_env_var_is_honored(self):
        row = self._row()
        cache = SupplierLookupCache()
        key = build_lookup_key("mouser", row)
        entry = _supplier_result_to_cache(self._mouser_result())
        entry["cached_at"] = entry["cached_at"] - 10  # 10 seconds old.
        cache.set(key, entry)

        calls = []
        with patch.dict(os.environ, {"SUPPLIER_LOOKUP_CACHE_TTL_SECONDS": "5"}):
            decision = source_row(
                row,
                lambda r: calls.append(r) or self._mouser_result(stock=999, supplier_part_number="603-FRESH"),
                lambda r: None,
                persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(decision["supplier_part_number"], "603-FRESH")


if __name__ == "__main__":
    unittest.main()
