import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from run_retention import cleanup_old_runs
from run_workspace import build_run_workspace


def _make_run_dir(root, run_id, age_seconds=0):
    run_dir = root / run_id
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    if age_seconds:
        stale_time = __import__("time").time() - age_seconds
        os.utime(run_dir, (stale_time, stale_time))
    return run_dir


class CleanupOldRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_retention_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def test_missing_runs_root_is_a_noop(self):
        missing = self.temp_root / "does-not-exist"
        result = cleanup_old_runs(runs_root=missing)

        self.assertEqual(result, {"deleted": [], "kept": [], "errors": []})

    def test_active_run_is_never_deleted_regardless_of_age(self):
        _make_run_dir(self.temp_root, "active-run", age_seconds=999 * 86400)

        result = cleanup_old_runs(
            runs_root=self.temp_root,
            active_run_id="active-run",
            retention_days=1,
            max_runs=0,
        )

        self.assertEqual(result["deleted"], [])
        self.assertIn("active-run", result["kept"])
        self.assertTrue((self.temp_root / "active-run").exists())

    def test_runs_older_than_retention_days_are_deleted(self):
        _make_run_dir(self.temp_root, "old-run", age_seconds=30 * 86400)
        _make_run_dir(self.temp_root, "new-run", age_seconds=0)

        result = cleanup_old_runs(runs_root=self.temp_root, retention_days=14, max_runs=0)

        self.assertIn("old-run", result["deleted"])
        self.assertIn("new-run", result["kept"])
        self.assertFalse((self.temp_root / "old-run").exists())
        self.assertTrue((self.temp_root / "new-run").exists())

    def test_retention_days_zero_disables_age_based_cleanup(self):
        _make_run_dir(self.temp_root, "very-old-run", age_seconds=999 * 86400)

        result = cleanup_old_runs(runs_root=self.temp_root, retention_days=0, max_runs=0)

        self.assertEqual(result["deleted"], [])
        self.assertTrue((self.temp_root / "very-old-run").exists())

    def test_max_runs_keeps_only_the_newest_n(self):
        for index in range(5):
            _make_run_dir(self.temp_root, f"run-{index}", age_seconds=index * 3600)

        result = cleanup_old_runs(runs_root=self.temp_root, retention_days=0, max_runs=3)

        self.assertEqual(len(result["kept"]), 3)
        self.assertEqual(len(result["deleted"]), 2)
        # The two oldest (highest age_seconds -> run-3, run-4) are removed.
        self.assertIn("run-3", result["deleted"])
        self.assertIn("run-4", result["deleted"])

    def test_max_runs_zero_disables_count_based_cleanup(self):
        for index in range(5):
            _make_run_dir(self.temp_root, f"run-{index}", age_seconds=index * 3600)

        result = cleanup_old_runs(runs_root=self.temp_root, retention_days=0, max_runs=0)

        self.assertEqual(result["deleted"], [])
        self.assertEqual(len(result["kept"]), 5)

    def test_cleanup_failure_is_captured_not_raised(self):
        # A file where a directory is expected: path.is_dir() is False, so
        # it's skipped entirely rather than tripping shutil.rmtree -- but
        # this also proves the walk itself never raises on unexpected
        # filesystem entries.
        (self.temp_root / "not-a-directory").write_text("x", encoding="utf-8")

        result = cleanup_old_runs(runs_root=self.temp_root, retention_days=0, max_runs=0)

        self.assertEqual(result["errors"], [])

    def test_never_raises_on_unexpected_exception(self):
        class ExplodingPath:
            def iterdir(self):
                raise RuntimeError("disk error")

            def exists(self):
                return True

        result = cleanup_old_runs(runs_root=ExplodingPath())

        self.assertTrue(result["errors"])


class BuildRunWorkspaceCleanupIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_workspace_retention_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def test_new_run_kickoff_reaps_old_runs_by_count(self):
        for index in range(5):
            _make_run_dir(self.temp_root, f"stale-{index}", age_seconds=(index + 1) * 3600)

        os.environ["AUTOBOM_MAX_RUNS"] = "2"
        os.environ["AUTOBOM_RUN_RETENTION_DAYS"] = "0"
        self.addCleanup(os.environ.pop, "AUTOBOM_MAX_RUNS", None)
        self.addCleanup(os.environ.pop, "AUTOBOM_RUN_RETENTION_DAYS", None)

        workspace = build_run_workspace(runs_root=self.temp_root)

        remaining = {p.name for p in self.temp_root.iterdir() if p.is_dir()}
        # max_runs=2 is a total cap including the just-created active run
        # (it is always newest, so it occupies one of the two kept slots);
        # only the single newest stale run survives alongside it.
        self.assertIn(workspace["run_id"], remaining)
        self.assertEqual(len(remaining), 2)

    def test_cleanup_false_leaves_old_runs_untouched(self):
        _make_run_dir(self.temp_root, "ancient-run", age_seconds=999 * 86400)

        build_run_workspace(runs_root=self.temp_root, cleanup=False)

        self.assertTrue((self.temp_root / "ancient-run").exists())


if __name__ == "__main__":
    unittest.main()
