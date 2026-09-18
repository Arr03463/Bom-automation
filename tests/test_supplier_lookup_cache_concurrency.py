import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from supplier_lookup_cache import (
    LOCK_STALE_SECONDS,
    SupplierLookupCache,
    _atomic_write_json,
    _FileLock,
    _read_json_file,
)


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
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"
        cache = SupplierLookupCache()
        cache.set("mouser|yageo|abc123|", {"supplier": "Mouser"})
        cache.save()

        self.assertFalse(self.cache_path.exists())
        self.assertIsNone(cache.get("mouser|yageo|abc123|"))

    def test_same_key_updates_resolve_last_write_wins(self):
        run_a = SupplierLookupCache()
        run_b = SupplierLookupCache()

        run_a.set("mouser|yageo|abc123|", {"supplier": "Mouser", "mpn": "ABC123-A"})
        run_b.set("mouser|yageo|abc123|", {"supplier": "Mouser", "mpn": "ABC123-B"})

        run_a.save()
        run_b.save()

        final = SupplierLookupCache()
        self.assertEqual(
            final.get("mouser|yageo|abc123|"), {"supplier": "Mouser", "mpn": "ABC123-B"}
        )

    def test_save_is_skipped_without_error_when_lock_cannot_be_acquired(self):
        os.environ["SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS"] = "0.2"
        self.addCleanup(os.environ.pop, "SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS", None)

        holder_lock_path = Path(str(self.cache_path) + ".lock")
        holder_lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder_lock_path.write_text("other-owner-token", encoding="utf-8")

        cache = SupplierLookupCache()
        cache.set("mouser|yageo|abc123|", {"supplier": "Mouser"})

        saved = cache.save()

        self.assertFalse(saved)
        self.assertFalse(self.cache_path.exists())
        # The other holder's lock must be untouched by our failed attempt.
        self.assertEqual(holder_lock_path.read_text(encoding="utf-8"), "other-owner-token")

    def test_sourcing_decisions_still_succeed_when_cache_save_is_skipped(self):
        import pandas as pd

        from sourcing_engine import SupplierResult, apply_sourcing_decisions

        os.environ["SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS"] = "0.2"
        self.addCleanup(os.environ.pop, "SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS", None)

        holder_lock_path = Path(str(self.cache_path) + ".lock")
        holder_lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder_lock_path.write_text("other-owner-token", encoding="utf-8")

        rows = pd.DataFrame(
            [
                {
                    "manufacturer": "Yageo",
                    "mpn": "ABC123",
                    "supplier_part_number": "",
                    "required_qty": "10",
                }
            ]
        )

        def mouser_lookup(row):
            return SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="ABC123",
                stock=100,
                supplier_part_number="603-ABC123",
            )

        def digikey_lookup(row):
            return SupplierResult(
                supplier="DigiKey",
                manufacturer="Yageo",
                mpn="ABC123",
                stock=0,
                supplier_part_number="ABC123-ND",
            )

        sourced = apply_sourcing_decisions(rows, mouser_lookup, digikey_lookup)

        self.assertEqual(list(sourced["selected_supplier"]), ["Mouser"])
        # The cache save was skipped (lock held by "another owner"); the
        # sourcing result is still correct and nothing raised.
        self.assertFalse(self.cache_path.exists())


class FileLockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_filelock_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.target_path = self.temp_dir / "target.json"
        self.lock_path = Path(str(self.target_path) + ".lock")

    def test_acquire_succeeds_when_free(self):
        lock = _FileLock(self.target_path, timeout=1)

        self.assertTrue(lock.acquire())
        self.assertTrue(lock.acquired)
        self.assertTrue(self.lock_path.exists())

        lock.release()
        self.assertFalse(lock.acquired)
        self.assertFalse(self.lock_path.exists())

    def test_acquire_times_out_when_held_by_another_owner(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text("other-owner-token", encoding="utf-8")

        lock = _FileLock(self.target_path, timeout=0.3)
        acquired = lock.acquire()

        self.assertFalse(acquired)
        self.assertFalse(lock.acquired)
        # A failed acquire must never touch the lock it failed to get.
        self.assertEqual(self.lock_path.read_text(encoding="utf-8"), "other-owner-token")

    def test_stale_lock_is_reclaimed_and_can_be_acquired(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text("dead-owner-token", encoding="utf-8")
        stale_time = time.time() - (LOCK_STALE_SECONDS + 5)
        os.utime(self.lock_path, (stale_time, stale_time))

        lock = _FileLock(self.target_path, timeout=2)
        acquired = lock.acquire()

        self.assertTrue(acquired)
        self.assertNotEqual(self.lock_path.read_text(encoding="utf-8"), "dead-owner-token")

        lock.release()
        self.assertFalse(self.lock_path.exists())

    def test_release_does_not_delete_a_successors_lock(self):
        lock_a = _FileLock(self.target_path, timeout=1)
        self.assertTrue(lock_a.acquire())

        # Simulate lock_a's lock being reclaimed as stale and re-acquired
        # by a successor while lock_a still believes it owns it.
        self.lock_path.write_text("successor-owner-token", encoding="utf-8")

        lock_a.release()

        self.assertTrue(self.lock_path.exists())
        self.assertEqual(self.lock_path.read_text(encoding="utf-8"), "successor-owner-token")


if __name__ == "__main__":
    unittest.main()
