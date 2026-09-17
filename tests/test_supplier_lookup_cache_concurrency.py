import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from supplier_lookup_cache import SupplierLookupCache, _atomic_write_json, _read_json_file


class SupplierLookupCacheConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_cache_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.cache_path = self.temp_dir / "supplier_lookup_cache.json"

        self._env_overrides = {
            "SUPPLIER_LOOKUP_CACHE_ENABLED": "true",
            "SUPPLIER_LOOKUP_CACHE_PATH": str(self.cache_path),
        }
        self._old_env = {}
        for key, value in self._env_overrides.items():
            self._old_env[key] = __import__("os").environ.get(key)
            __import__("os").environ[key] = value

        self.addCleanup(self._restore_env)

    def _restore_env(self):
        import os

        for key, old_value in self._old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    def test_set_then_save_persists_value(self):
        cache = SupplierLookupCache()
        cache.set("mouser|yageo|abc123|", {"supplier": "Mouser", "mpn": "ABC123"})
        cache.save()

        reloaded = SupplierLookupCache()
        self.assertEqual(reloaded.get("mouser|yageo|abc123|"), {"supplier": "Mouser", "mpn": "ABC123"})

    def test_two_runs_updating_different_keys_both_survive(self):
        run_a = SupplierLookupCache()
        run_b = SupplierLookupCache()

        run_a.set("mouser|yageo|abc123|", {"supplier": "Mouser", "mpn": "ABC123"})
        run_b.set("digikey|ti|xyz789|", {"supplier": "DigiKey", "mpn": "XYZ789"})

        # Simulate run_a finishing first, then run_b -- run_b must not
        # clobber run_a's update even though run_b loaded before run_a saved.
        run_a.save()
        run_b.save()

        final = SupplierLookupCache()
        self.assertEqual(final.get("mouser|yageo|abc123|"), {"supplier": "Mouser", "mpn": "ABC123"})
        self.assertEqual(final.get("digikey|ti|xyz789|"), {"supplier": "DigiKey", "mpn": "XYZ789"})

    def test_concurrent_threaded_writers_do_not_lose_updates(self):
        num_writers = 8
        barrier = threading.Barrier(num_writers)
        errors = []

        def worker(index):
            try:
                barrier.wait(timeout=5)
                cache = SupplierLookupCache()
                cache.set(f"mouser|mfg|part{index}|", {"supplier": "Mouser", "mpn": f"PART{index}"})
                cache.save()
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])

        final = SupplierLookupCache()
        for index in range(num_writers):
            self.assertEqual(
                final.get(f"mouser|mfg|part{index}|"),
                {"supplier": "Mouser", "mpn": f"PART{index}"},
            )

    def test_corrupted_cache_file_is_treated_as_empty_not_fatal(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text("{not valid json", encoding="utf-8")

        cache = SupplierLookupCache()
        self.assertIsNone(cache.get("anything"))

        cache.set("mouser|yageo|abc123|", {"supplier": "Mouser"})
        cache.save()

        # Saving after a corrupt read must produce valid JSON going forward.
        reloaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(reloaded["mouser|yageo|abc123|"], {"supplier": "Mouser"})

    def test_atomic_write_leaves_no_partial_file_on_disk(self):
        _atomic_write_json(self.cache_path, {"a": 1})
        self.assertEqual(_read_json_file(self.cache_path), {"a": 1})

        leftover_temp_files = list(self.cache_path.parent.glob(".*.tmp"))
        self.assertEqual(leftover_temp_files, [])

    def test_disabled_cache_never_touches_disk(self):
        import os

        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"
        cache = SupplierLookupCache()
        cache.set("mouser|yageo|abc123|", {"supplier": "Mouser"})
        cache.save()

        self.assertFalse(self.cache_path.exists())
        self.assertIsNone(cache.get("mouser|yageo|abc123|"))


if __name__ == "__main__":
    unittest.main()
