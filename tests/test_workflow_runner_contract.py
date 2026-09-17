import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from run_workspace import build_run_workspace, save_uploaded_file
from workflow_runner import run_bom_workflow


SAMPLE_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
    "C1 C2,2,Murata,GRM188R71C105KA12D,1uF Capacitor 16V 0603\n"
)


def run_isolated_workflow(runs_root, project_name="Widget"):
    workspace = build_run_workspace(runs_root=runs_root)
    source_path = save_uploaded_file(
        workspace["input_dir"], "bom.csv", SAMPLE_BOM_CSV.encode("utf-8")
    )

    result = run_bom_workflow(
        source_file_path=source_path,
        build_quantity=5,
        project_name=project_name,
        run_partsbox=False,
        run_sourcing=False,
        run_mouser_cart=False,
        run_digikey_mylist=False,
        run_id=workspace["run_id"],
        output_folder=str(workspace["output_dir"]),
    )
    return workspace, result


class WorkflowRunnerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_workflow_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def test_backward_compatible_keys_are_preserved(self):
        _, result = run_isolated_workflow(self.temp_root)

        for key in ("success", "errors", "warnings", "summary", "outputs", "messages"):
            self.assertIn(key, result)

    def test_run_metadata_is_returned(self):
        workspace, result = run_isolated_workflow(self.temp_root)

        self.assertEqual(result["run"]["run_id"], workspace["run_id"])
        self.assertEqual(result["run"]["project_name"], "Widget")
        self.assertEqual(result["run"]["build_quantity"], 5)
        self.assertEqual(result["run"]["source_file_name"], "bom.csv")

    def test_bom_rows_are_structured_with_stable_row_ids(self):
        workspace, result = run_isolated_workflow(self.temp_root)

        self.assertEqual(len(result["bom_rows"]), 2)
        for row in result["bom_rows"]:
            self.assertTrue(row["row_id"].startswith(f"{workspace['run_id']}:"))
        self.assertEqual(result["review_items"], [])

    def test_purchasing_and_partsbox_default_when_not_attempted(self):
        _, result = run_isolated_workflow(self.temp_root)

        self.assertFalse(result["purchasing"]["mouser"]["attempted"])
        self.assertFalse(result["purchasing"]["digikey"]["attempted"])
        self.assertIsNone(result["partsbox"])

    def test_two_runs_with_same_uploaded_filename_stay_isolated(self):
        workspace_a, result_a = run_isolated_workflow(self.temp_root, project_name="Alpha")
        workspace_b, result_b = run_isolated_workflow(self.temp_root, project_name="Bravo")

        self.assertNotEqual(result_a["run"]["run_id"], result_b["run"]["run_id"])
        self.assertNotEqual(
            result_a["outputs"]["cleaned_csv"], result_b["outputs"]["cleaned_csv"]
        )
        self.assertTrue(Path(result_a["outputs"]["cleaned_csv"]).exists())
        self.assertTrue(Path(result_b["outputs"]["cleaned_csv"]).exists())

        content_a = Path(result_a["outputs"]["cleaned_csv"]).read_text()
        content_b = Path(result_b["outputs"]["cleaned_csv"]).read_text()
        # Each run's cleaned CSV must live under its own run directory only.
        self.assertIn(workspace_a["run_id"], result_a["outputs"]["cleaned_csv"])
        self.assertIn(workspace_b["run_id"], result_b["outputs"]["cleaned_csv"])
        self.assertNotIn(workspace_b["run_id"], result_a["outputs"]["cleaned_csv"])
        self.assertEqual(content_a, content_b)


if __name__ == "__main__":
    unittest.main()
