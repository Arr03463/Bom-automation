import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from sourcing_engine import SupplierResult, _supplier_result_to_cache, source_row
from supplier_lookup_cache import SupplierLookupCache, build_lookup_key


class DisabledSupplierCacheBypassTests(unittest.TestCase):
    """
    Regression coverage for
    Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md:
    a supplier disabled via `enabled_sources` must never be satisfied
    from a stale cached result left over from an earlier (enabled) run --
    a no-op lookup callable alone is not sufficient, because
    _cached_supplier_lookup() used to check the cache before ever
    considering the lookup function at all. These tests populate the
    persistent cache first (an empty-cache test cannot reproduce this
    defect, per the correction report).
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_sourcing_cache_test_"))
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

    def _row(self, mpn="ABC123", manufacturer="Yageo", required_qty="10"):
        return {
            "mpn": mpn,
            "manufacturer": manufacturer,
            "supplier_part_number": "",
            "required_qty": required_qty,
        }

    def _cache_with(self, supplier_name, row, result):
        cache = SupplierLookupCache()
        key = build_lookup_key(supplier_name, row)
        cache.set(key, _supplier_result_to_cache(result))
        return cache

    def test_a_digikey_only_ignores_cached_mouser(self):
        row = self._row()
        cache = self._cache_with(
            "mouser",
            row,
            SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500,
                supplier_part_number="603-CACHED",
            ),
        )

        mouser_calls = []
        digikey_calls = []

        def mouser_lookup(r):
            mouser_calls.append(r)
            return None

        def digikey_lookup(r):
            digikey_calls.append(r)
            return SupplierResult(
                supplier="DigiKey", manufacturer="Yageo", mpn="ABC123", stock=200,
                supplier_part_number="ABC123-ND",
            )

        decision = source_row(
            row, mouser_lookup, digikey_lookup,
            persistent_cache=cache, run_cache={}, enabled_sources={"digikey"},
        )

        self.assertEqual(decision["selected_supplier"], "DigiKey")
        self.assertEqual(decision["sourcing_status"], "sourced_digikey")
        self.assertEqual(len(digikey_calls), 1)
        self.assertEqual(len(mouser_calls), 0)
        self.assertNotIn("603-CACHED", decision["supplier_part_number"])

    def test_b_mouser_only_ignores_cached_digikey(self):
        row = self._row()
        cache = self._cache_with(
            "digikey",
            row,
            SupplierResult(
                supplier="DigiKey", manufacturer="Yageo", mpn="ABC123", stock=500,
                supplier_part_number="ABC123-ND-CACHED",
            ),
        )

        mouser_calls = []
        digikey_calls = []

        def mouser_lookup(r):
            mouser_calls.append(r)
            return SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=300,
                supplier_part_number="603-ABC123",
            )

        def digikey_lookup(r):
            digikey_calls.append(r)
            return None

        decision = source_row(
            row, mouser_lookup, digikey_lookup,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser"},
        )

        self.assertEqual(decision["selected_supplier"], "Mouser")
        self.assertEqual(decision["sourcing_status"], "sourced_mouser")
        self.assertEqual(len(mouser_calls), 1)
        self.assertEqual(len(digikey_calls), 0)
        self.assertNotIn("CACHED", decision["supplier_part_number"])

    def test_c_disabled_supplier_cached_match_does_not_prevent_review(self):
        row = self._row()
        cache = self._cache_with(
            "mouser",
            row,
            SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500,
                supplier_part_number="603-CACHED",
            ),
        )

        decision = source_row(
            row,
            lambda r: None,
            lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"digikey"},
        )

        self.assertEqual(decision["selected_supplier"], "")
        self.assertEqual(decision["sourcing_status"], "check_wall_inventory")

    def test_d_both_enabled_still_reuse_cache(self):
        row = self._row()
        cache = self._cache_with(
            "mouser",
            row,
            SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500,
                supplier_part_number="603-CACHED",
            ),
        )

        mouser_calls = []

        def mouser_lookup(r):
            mouser_calls.append(r)
            return None

        decision = source_row(
            row, mouser_lookup, lambda r: None,
            persistent_cache=cache, run_cache={}, enabled_sources={"mouser", "digikey"},
        )

        self.assertEqual(decision["selected_supplier"], "Mouser")
        self.assertEqual(decision["supplier_part_number"], "603-CACHED")
        self.assertEqual(len(mouser_calls), 0)

    def test_default_enabled_sources_is_backward_compatible(self):
        """Omitting enabled_sources entirely must behave exactly as before
        this parameter was added -- both suppliers considered."""
        row = self._row()
        cache = SupplierLookupCache()

        decision = source_row(
            row,
            lambda r: SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500),
            lambda r: None,
            persistent_cache=cache, run_cache={},
        )

        self.assertEqual(decision["selected_supplier"], "Mouser")


if __name__ == "__main__":
    unittest.main()
