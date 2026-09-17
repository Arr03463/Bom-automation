import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from run_workspace import build_run_workspace, save_uploaded_file


class RunWorkspaceIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_runs_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def test_two_runs_generate_distinct_run_ids_and_directories(self):
        workspace_a = build_run_workspace(runs_root=self.temp_root)
        workspace_b = build_run_workspace(runs_root=self.temp_root)

        self.assertNotEqual(workspace_a["run_id"], workspace_b["run_id"])
        self.assertNotEqual(workspace_a["input_dir"], workspace_b["input_dir"])
        self.assertNotEqual(workspace_a["output_dir"], workspace_b["output_dir"])
        self.assertTrue(workspace_a["input_dir"].is_dir())
        self.assertTrue(workspace_a["output_dir"].is_dir())

    def test_same_uploaded_filename_does_not_collide_across_runs(self):
        workspace_a = build_run_workspace(runs_root=self.temp_root)
        workspace_b = build_run_workspace(runs_root=self.temp_root)

        path_a = save_uploaded_file(workspace_a["input_dir"], "bom.csv", b"run-a-content")
        path_b = save_uploaded_file(workspace_b["input_dir"], "bom.csv", b"run-b-content")

        self.assertNotEqual(path_a, path_b)
        self.assertEqual(path_a.read_bytes(), b"run-a-content")
        self.assertEqual(path_b.read_bytes(), b"run-b-content")

        # Overwriting one run's file must never touch the other run's copy.
        save_uploaded_file(workspace_a["input_dir"], "bom.csv", b"run-a-content-v2")
        self.assertEqual(path_a.read_bytes(), b"run-a-content-v2")
        self.assertEqual(path_b.read_bytes(), b"run-b-content")

    def test_upload_name_is_sanitized(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        path = save_uploaded_file(workspace["input_dir"], "my bom (v2)!!.csv", b"data")

        self.assertTrue(path.exists())
        self.assertNotIn(" ", path.name)
        self.assertNotIn("(", path.name)


if __name__ == "__main__":
    unittest.main()
