import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from active_bom_state import ActiveBomState
from bom_cleaner import STANDARD_COLUMNS
from run_workspace import build_run_workspace, save_uploaded_file
from workflow_runner import refresh_response_snapshot, run_bom_workflow, start_manual_bom_workflow


SAMPLE_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
    "C1 C2,2,Murata,GRM188R71C105KA12D,1uF Capacitor 16V 0603\n"
)

SAMPLE_BOM_WITH_REVIEW_ROW_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
    "U1,1,STMicroelectronics,,Missing part number\n"
)


def run_isolated_workflow(runs_root, project_name="Widget", bom_csv=SAMPLE_BOM_CSV):
    workspace = build_run_workspace(runs_root=runs_root)
    source_path = save_uploaded_file(
        workspace["input_dir"], "bom.csv", bom_csv.encode("utf-8")
    )

    result = run_bom_workflow(
        source_file_path=source_path,
        build_quantity=5,
        project_name=project_name,
        run_partsbox=False,
        run_sourcing=False,
        run_digikey_mylist=False,
        run_id=workspace["run_id"],
        output_folder=str(workspace["output_dir"]),
    )
    return workspace, result


def run_isolated_workflow_with_review_row(runs_root, project_name="Widget"):
    return run_isolated_workflow(
        runs_root, project_name=project_name, bom_csv=SAMPLE_BOM_WITH_REVIEW_ROW_CSV
    )


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

    def test_customer_reference_column_is_initialized_empty_on_every_row(self):
        """
        customer_reference is canonical BOM data (see customer_reference.py)
        -- it must exist on every row from run start, not only appear
        once an operator first assigns a value.
        """
        _, result = run_isolated_workflow(self.temp_root)

        self.assertTrue(result["bom_rows"])
        for row in result["bom_rows"]:
            self.assertIn("customer_reference", row)
            self.assertEqual(row["customer_reference"], "")

    def test_purchasing_and_partsbox_default_when_not_attempted(self):
        """
        Mouser has no "attempted" vendor-call tracking anymore -- it's a
        plain file export (see mouser_export.py), so response["purchasing"]["mouser"]
        stays None always (the export's own state lives in
        artifact_status["mouser_export_csv"]/outputs["mouser_export_csv"]
        instead).
        """
        _, result = run_isolated_workflow(self.temp_root)

        self.assertIsNone(result["purchasing"]["mouser"])
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

    def test_review_items_and_bom_rows_share_identity_from_one_canonical_state(self):
        """
        Guards against bom_rows and review_items being two independently
        derived/copied datasets that could drift apart -- the review row's
        row_id must also be present in bom_rows, with matching field
        values, because both are produced from the same ActiveBomState.
        """
        _, result = run_isolated_workflow_with_review_row(self.temp_root)

        self.assertEqual(len(result["review_items"]), 1)
        review_row = result["review_items"][0]

        matching_bom_row = next(
            (row for row in result["bom_rows"] if row["row_id"] == review_row["row_id"]),
            None,
        )

        self.assertIsNotNone(matching_bom_row)
        self.assertEqual(matching_bom_row["status"], "missing_mpn")
        self.assertEqual(matching_bom_row["status"], review_row["status"])
        self.assertEqual(matching_bom_row["manufacturer"], review_row["manufacturer"])

    def test_live_active_bom_state_is_exposed_for_session_state_use(self):
        _, result = run_isolated_workflow(self.temp_root)

        state = result["_active_bom_state"]
        self.assertIsInstance(state, ActiveBomState)
        self.assertEqual(state.rows(), result["bom_rows"])

    def test_results_summary_matches_active_bom_state(self):
        _, result = run_isolated_workflow(self.temp_root)

        self.assertEqual(result["results_summary"], result["_active_bom_state"].summary_counts())
        self.assertEqual(result["results_summary"]["total_parts"], 2)

    def test_run_summary_json_on_disk_excludes_live_state(self):
        _, result = run_isolated_workflow(self.temp_root)

        summary_path = Path(result["outputs"]["run_summary"])
        on_disk = json.loads(summary_path.read_text())

        self.assertNotIn("_active_bom_state", on_disk)
        self.assertIn("results_summary", on_disk)

    def test_refresh_response_snapshot_recomputes_from_live_state_and_marks_stale(self):
        _, result = run_isolated_workflow(self.temp_root)
        active_bom_state = result["_active_bom_state"]

        self.assertFalse(result["stale_after_mutation"])

        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"status": "manual_review", "notes": "mutated out of band"})

        refresh_response_snapshot(result)

        self.assertTrue(result["stale_after_mutation"])
        refreshed_row = next(r for r in result["bom_rows"] if r["row_id"] == row_id)
        self.assertEqual(refreshed_row["notes"], "mutated out of band")
        self.assertEqual(result["results_summary"], active_bom_state.summary_counts())

    def test_refresh_response_snapshot_is_a_noop_without_active_bom_state(self):
        response = {"_active_bom_state": None, "bom_rows": ["untouched"]}

        refresh_response_snapshot(response)

        self.assertEqual(response["bom_rows"], ["untouched"])
        self.assertNotIn("stale_after_mutation", response)


class StartManualBomWorkflowTests(unittest.TestCase):
    """
    workflow_runner.start_manual_bom_workflow() -- lets Search start the
    working BOM itself, with no upload required first (Search is the
    default/primary intake method -- see app.py's
    _add_search_result_to_working_bom()).
    """

    def test_creates_an_empty_but_valid_response_shape(self):
        response = start_manual_bom_workflow()

        self.assertTrue(response["success"])
        self.assertIsInstance(response["_active_bom_state"], ActiveBomState)
        self.assertEqual(response["_active_bom_state"].rows(), [])
        self.assertEqual(response["bom_rows"], [])
        self.assertEqual(response["review_items"], [])
        self.assertEqual(response["results_summary"]["total_parts"], 0)
        self.assertIn("run_id", response["run"])

    def test_schema_matches_an_uploaded_runs_column_set_for_merging(self):
        """
        A manually-started working BOM and an uploaded one must share
        identical DataFrame columns so ActiveBomState.add_rows() can
        freely merge either direction (see
        app.py's render_upload_intake()).
        """
        response = start_manual_bom_workflow()

        active_bom_state = response["_active_bom_state"]
        for column in STANDARD_COLUMNS:
            self.assertIn(column, active_bom_state.dataframe.columns)
        self.assertIn("customer_reference", active_bom_state.dataframe.columns)

    def test_each_call_gets_a_distinct_run_id(self):
        first = start_manual_bom_workflow()
        second = start_manual_bom_workflow()

        self.assertNotEqual(first["run"]["run_id"], second["run"]["run_id"])

    def test_does_not_create_any_output_files(self):
        """
        Nothing to process yet -- no cleaned CSV/workbook/sourcing report
        should be written merely by starting an empty working BOM.
        """
        response = start_manual_bom_workflow()

        self.assertEqual(response["outputs"]["cleaned_csv"], "")
        self.assertEqual(response["outputs"]["cleaned_workbook"], "")


if __name__ == "__main__":
    unittest.main()
