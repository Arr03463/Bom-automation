"""
Streamlit UI smoke tests using streamlit.testing.v1.AppTest -- runs
app.py's actual script (not a re-implementation of it) and inspects the
rendered widget tree. Deliberately never clicks "Retry Exact Part" or a
replacement "Search" button, since both call real Mouser/DigiKey/PartsBox
clients whose reads are not gated by any dry-run flag in this codebase --
clicking them in a test would make live vendor API calls. Everything
exercised here (page load, run injection, Find Replacement's prefilled
sub-UI, and applying an already-found replacement) never reaches network
code.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from streamlit.testing.v1 import AppTest

from run_workspace import build_run_workspace, save_uploaded_file
from workflow_runner import run_bom_workflow


REVIEW_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "U1,1,STMicroelectronics,,Missing part number\n"
)


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_app_smoke_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def _run_with_review_row(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(
            workspace["input_dir"], "bom.csv", REVIEW_BOM_CSV.encode("utf-8")
        )
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="SmokeTest",
            run_partsbox=False,
            run_sourcing=False,
            run_mouser_cart=False,
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def test_app_loads_without_exceptions(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.run()
        self.assertEqual(len(at.exception), 0)

    def test_navigating_to_component_search_has_no_exceptions(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.run()

        at.sidebar.radio[0].set_value("Component Search")
        at.run()

        self.assertEqual(len(at.exception), 0)

    def test_injected_run_result_renders_results_workspace(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 5)
        tab_labels = [tab.label for tab in at.tabs]
        self.assertIn("All Results", tab_labels)
        self.assertIn("Needs Review (1)", tab_labels)

    def test_needs_review_actions_render_without_being_invoked(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.session_state["current_run"] = result
        at.run()

        button_labels = [button.label for button in at.button]
        self.assertIn("Retry Exact Part", button_labels)
        self.assertIn("Find Replacement", button_labels)
        self.assertIn("Check PartsBox", button_labels)

    def test_find_replacement_click_renders_prefilled_search_without_calling_it(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.session_state["current_run"] = result
        at.run()

        find_replacement = next(b for b in at.button if b.label == "Find Replacement")
        find_replacement.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIn("Search", [button.label for button in at.button])

    def test_selecting_a_replacement_updates_canonical_state_via_ui(self):
        result = self._run_with_review_row()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        at.session_state["current_run"] = result
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        # Simulate a completed search by injecting its result directly --
        # never calls search_components()/live vendor APIs in this test.
        at.session_state[f"replacement_results_{row_id}"] = [
            {
                "source": "Mouser",
                "mpn": "REPLACEMENT123",
                "manufacturer": "STMicroelectronics",
                "supplier_part_number": "511-REPL123",
                "unit_price": "0.5",
                "stock": 900,
                "description": "",
                "category": "",
                "package": "",
                "lifecycle_status": "",
                "characteristics": {},
                "raw": {},
            }
        ]
        at.run()

        next(b for b in at.button if b.label == "Select").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(active_bom_state.summary_counts()["needs_review"], 0)

        updated_row = active_bom_state.get_row(row_id)
        self.assertEqual(updated_row["mpn"], "REPLACEMENT123")
        self.assertEqual(updated_row["source"], "Mouser")
        self.assertEqual(updated_row["result_status"], "Ready")


if __name__ == "__main__":
    unittest.main()
