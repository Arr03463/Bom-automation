import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from file_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, FileLock, LockAcquisitionError


class FileLockContextManagerTests(unittest.TestCase):
    """
    Codex F1: `with FileLock(...):` must be fail-closed -- entering the
    block must always mean the lock is actually held. Before this fix,
    __enter__() called acquire() and ignored its (possibly False) return
    value, so a caller using `with` could run its protected code without
    ever owning the lock.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_file_lock_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.target_path = self.temp_dir / "resource"

    def test_successful_acquire_enters_normally(self):
        with FileLock(self.target_path, timeout=1) as lock:
            self.assertTrue(lock.acquired)

    def test_timed_out_acquire_raises_instead_of_entering(self):
        holder = FileLock(self.target_path, timeout=1)
        self.assertTrue(holder.acquire())
        try:
            entered = False
            with self.assertRaises(LockAcquisitionError):
                with FileLock(self.target_path, timeout=0.2):
                    entered = True  # pragma: no cover - must never execute
            self.assertFalse(entered)
        finally:
            holder.release()

    def test_lock_is_released_after_a_successful_with_block(self):
        with FileLock(self.target_path, timeout=1):
            pass

        # A second acquire should succeed immediately -- the first lock
        # was actually released, not merely reported as "not acquired".
        second = FileLock(self.target_path, timeout=1)
        self.assertTrue(second.acquire())
        second.release()

    def test_lock_is_released_even_when_the_protected_block_raises(self):
        class Boom(Exception):
            pass

        with self.assertRaises(Boom):
            with FileLock(self.target_path, timeout=1):
                raise Boom("protected operation failed")

        second = FileLock(self.target_path, timeout=1)
        self.assertTrue(second.acquire())
        second.release()

    def test_default_timeout_used_when_not_specified(self):
        lock = FileLock(self.target_path)
        self.assertEqual(lock.timeout, DEFAULT_LOCK_TIMEOUT_SECONDS)


class FileLockStaleThresholdTests(unittest.TestCase):
    """
    Codex F1 (stale-lock timing): the stale-reclaim threshold must be
    configurable per lock instance so a caller with a longer protected
    operation (e.g. an HTTP round trip) can use a threshold comfortably
    longer than that operation, independent of other FileLock users (e.g.
    SupplierLookupCache's near-instant JSON read-modify-write).
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_file_lock_stale_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.target_path = self.temp_dir / "resource"

    def test_custom_stale_after_is_honored_not_reclaimed_early(self):
        # A holder with a long custom stale_after must not be reclaimed by
        # a waiter using the (much shorter) default stale threshold logic
        # -- reclaim is driven by lock.stale_after on the ACQUIRING lock's
        # own instance, so a waiter must be constructed with the same
        # generous threshold the protected operation actually needs.
        holder = FileLock(self.target_path, timeout=1, stale_after=120)
        self.assertTrue(holder.acquire())

        waiter = FileLock(self.target_path, timeout=0.3, stale_after=120)
        self.assertFalse(waiter.acquire())  # times out, does not reclaim
        holder.release()

    def test_default_stale_after_matches_module_constant(self):
        from file_lock import LOCK_STALE_SECONDS

        lock = FileLock(self.target_path)
        self.assertEqual(lock.stale_after, LOCK_STALE_SECONDS)


if __name__ == "__main__":
    unittest.main()
