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

from streamlit.testing.v1 import AppTest

from run_workspace import build_run_workspace, save_uploaded_file
from sourcing_engine import SupplierResult
from workflow_runner import run_bom_workflow


REVIEW_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "U1,1,STMicroelectronics,,Missing part number\n"
)

CLEAN_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
)


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_app_smoke_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

        old_cache_enabled = os.environ.get("SUPPLIER_LOOKUP_CACHE_ENABLED")
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"
        self.addCleanup(self._restore_cache_env, old_cache_enabled)

    @staticmethod
    def _restore_cache_env(old_value):
        if old_value is None:
            os.environ.pop("SUPPLIER_LOOKUP_CACHE_ENABLED", None)
        else:
            os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = old_value

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
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        self.assertEqual(len(at.exception), 0)

    def test_navigating_to_component_search_has_no_exceptions(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        at.sidebar.radio[0].set_value("Component Search")
        at.run()

        self.assertEqual(len(at.exception), 0)

    def test_injected_run_result_renders_results_workspace(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 5)
        tab_labels = [tab.label for tab in at.tabs]
        self.assertIn("All Results", tab_labels)
        self.assertIn("Needs Review (1)", tab_labels)

    def test_needs_review_actions_render_without_being_invoked(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        button_labels = [button.label for button in at.button]
        self.assertIn("Retry Exact Part", button_labels)
        self.assertIn("Find Replacement", button_labels)
        self.assertIn("Check PartsBox", button_labels)

    def test_find_replacement_click_renders_prefilled_search_without_calling_it(self):
        result = self._run_with_review_row()

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        find_replacement = next(b for b in at.button if b.label == "Find Replacement")
        find_replacement.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIn("Search", [button.label for button in at.button])

    def test_selecting_a_replacement_updates_canonical_state_via_ui(self):
        """
        apply_replacement() re-sources the replacement through the real
        MouserClient/DigiKeyClient (no injection point from the Needs
        Review UI), so this test mocks those two classes at their
        review_actions import site -- otherwise clicking "Select" would
        make live vendor API calls. The mocked Mouser lookup returns full
        stock, so the assertions below prove the row was genuinely
        re-sourced by the real sourcing decision (result_status/
        selected_supplier/supplier_order_qty all correct), not manually
        stamped from the discovery candidate.
        """
        result = self._run_with_review_row()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        # Simulate a completed search by injecting its result directly --
        # never calls search_components()/live vendor APIs in this test.
        at.session_state[f"replacement_results_{row_id}"] = [
            {
                "source": "DigiKey",
                "mpn": "REPLACEMENT123",
                "manufacturer": "STMicroelectronics",
                "supplier_part_number": "511-REPL123-DIGIKEY",
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

        mouser_match = SupplierResult(
            supplier="Mouser",
            manufacturer="STMicroelectronics",
            mpn="REPLACEMENT123",
            stock=500,
            supplier_part_number="511-REPLACEMENT123-MOUSER",
        )
        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = mouser_match
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None

            next(b for b in at.button if b.label == "Select").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(active_bom_state.summary_counts()["needs_review"], 0)

        updated_row = active_bom_state.get_row(row_id)
        self.assertEqual(updated_row["mpn"], "REPLACEMENT123")
        # Discovered via DigiKey, but re-sourcing found Mouser covers it
        # -- normal Mouser-first rules picked Mouser, not the discovery
        # source. This is the core Phase 3 fix, verified through the
        # real UI, not just the underlying function.
        self.assertEqual(updated_row["selected_supplier"], "Mouser")
        self.assertEqual(updated_row["source"], "Mouser")
        self.assertEqual(updated_row["supplier_part_number"], "511-REPLACEMENT123-MOUSER")
        self.assertEqual(updated_row["result_status"], "Ready")
        self.assertEqual(updated_row["replacement_discovery_source"], "DigiKey")

    def test_retry_marks_downloads_stale_and_refreshes_snapshot(self):
        result = self._run_with_review_row()
        row_id = result["_active_bom_state"].rows()[0]["row_id"]

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertFalse(result.get("stale_after_mutation"))

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = None
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None

            next(b for b in at.button if b.label == "Retry Exact Part").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(result["stale_after_mutation"])
        # bom_rows snapshot was refreshed from the live state, not left
        # as the pre-mutation snapshot.
        refreshed_row = next(r for r in result["bom_rows"] if r["row_id"] == row_id)
        self.assertEqual(refreshed_row["sourcing_status"], "manual_review")
        warning_texts = [w.value for w in at.warning]
        self.assertTrue(any("regenerated" in text for text in warning_texts))

    def test_new_run_resets_run_scoped_session_state(self):
        """
        Exercises the real "Run BOM Automation" button handler (not a
        hand-simulated version of reset_run_scoped_session_state()) via
        AppTest's file_uploader.upload(), with sourcing/PartsBox turned
        off so the second run makes no live vendor calls.
        """
        result_a = self._run_with_review_row()
        row_id_a = result_a["_active_bom_state"].rows()[0]["row_id"]

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result_a
        at.run()

        # Open a review row's replacement panel and set a results filter,
        # simulating mid-review state from the first run.
        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()
        at.session_state[f"replacement_results_{row_id_a}"] = [{"source": "Mouser", "mpn": "X"}]
        at.session_state["results_search"] = "some search text"
        at.run()

        self.assertEqual(at.session_state["selected_review_row_id"], row_id_a)

        for checkbox in at.checkbox:
            if checkbox.label in ("Run PartsBox", "Run supplier sourcing"):
                checkbox.set_value(False)
        at.file_uploader[0].upload("bom2.csv", REVIEW_BOM_CSV.encode("utf-8"), "text/csv")
        at.run()

        next(b for b in at.button if b.label == "Run BOM Automation").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state["selected_review_row_id"])
        self.assertEqual(at.session_state["results_search"], "")
        self.assertNotIn(f"replacement_results_{row_id_a}", at.session_state)
        # A genuinely new run replaced current_run.
        self.assertNotEqual(
            at.session_state["current_run"]["run"]["run_id"], result_a["run"]["run_id"]
        )


def _lookup_result(**overrides):
    result = {
        "source": "PartsBox",
        "manufacturer": "Yageo",
        "mpn": "ABC123",
        "description": "10k Resistor",
        "category": "Resistor",
        "package": "0603",
        "stock": None,
        "supplier_part_number": "",
        "unit_price": "",
        "lifecycle_status": "",
        "characteristics": {},
        "raw": {"part/id": "p1"},
        "stock_sufficient": None,
    }
    result.update(overrides)
    return result


class PartsBoxInventorySmokeTests(unittest.TestCase):
    def _navigate_to_inventory(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        at.sidebar.radio[0].set_value("PartsBox Inventory")
        at.run()
        return at

    def test_inventory_page_loads_without_exceptions(self):
        at = self._navigate_to_inventory()
        self.assertEqual(len(at.exception), 0)

    def test_search_reuses_shared_lookup_service(self):
        at = self._navigate_to_inventory()

        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = [_lookup_result()]
            next(b for b in at.button if b.label == "Search / Browse All").click()
            at.run()

        mock_search.assert_called_once()
        called_query = mock_search.call_args[0][0]
        # PartsBox Inventory only ever searches PartsBox, through the
        # exact same LookupQuery/search_components() Component Search and
        # Find Replacement use -- not a second PartsBox search path.
        self.assertEqual(called_query.sources, frozenset({"partsbox"}))
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe), 1)

    def test_filters_use_shared_filtering_layer(self):
        at = self._navigate_to_inventory()

        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = [
                _lookup_result(mpn="A", package="0603"),
                _lookup_result(mpn="B", package="0805"),
            ]
            next(b for b in at.button if b.label == "Search / Browse All").click()
            at.run()

        selectbox_labels = [s.label for s in at.selectbox]
        self.assertIn("Package", selectbox_labels)

    def test_no_write_action_buttons_are_present(self):
        """
        No PartsBox write operation is confirmed supported in this pass
        (see the Phase 4 report) -- the Inventory page must not offer
        write actions it can't back with a verified API call.
        """
        at = self._navigate_to_inventory()
        button_labels = {b.label for b in at.button}
        write_action_labels = {
            "Add Stock",
            "Remove Stock",
            "Update Quantity",
            "Move Stock",
            "Create Part",
            "Edit Part",
            "Delete Part",
        }
        self.assertEqual(write_action_labels.intersection(button_labels), set())

    def test_storage_locations_load_via_shared_partsbox_client(self):
        at = self._navigate_to_inventory()

        with patch("partsbox_client.PartsBoxClient") as mock_client_cls:
            mock_client_cls.return_value.list_storage_locations.return_value = {
                "data": [{"storage/name": "Widget", "storage/tags": ["production"]}]
            }
            next(b for b in at.button if b.label == "Load storage locations").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        mock_client_cls.return_value.list_storage_locations.assert_called_once()
        self.assertEqual(len(at.dataframe), 1)


class DynamicFacetSmokeTests(unittest.TestCase):
    def test_component_search_shows_facets_present_in_results(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        at.sidebar.radio[0].set_value("Component Search")
        at.run()

        fake_results = [
            _lookup_result(mpn="A", package="0603", manufacturer="Yageo"),
            _lookup_result(mpn="B", package="0805", manufacturer="Murata"),
        ]
        fake_results[0]["voltage"] = "25V"
        fake_results[1]["voltage"] = "50V"

        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = fake_results
            next(b for b in at.button if b.label == "Search").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        selectbox_labels = [s.label for s in at.selectbox]
        self.assertIn("Package", selectbox_labels)
        text_input_labels = [t.label for t in at.text_input]
        self.assertTrue(any("voltage" in (label or "").lower() for label in text_input_labels))


class PurchasingPageSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_purchasing_smoke_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def _run(self, csv_text):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", csv_text.encode("utf-8"))
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="PurchasingSmoke",
            run_partsbox=False,
            run_sourcing=False,
            run_mouser_cart=False,
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def _navigate_to_purchasing(self, result):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()
        at.sidebar.radio[0].set_value("Purchasing")
        at.run()
        return at

    def test_purchasing_page_loads_without_exceptions(self):
        at = self._navigate_to_purchasing(self._run(CLEAN_BOM_CSV))
        self.assertEqual(len(at.exception), 0)

    def test_regenerate_button_disabled_while_review_pending(self):
        at = self._navigate_to_purchasing(self._run(REVIEW_BOM_CSV))

        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        self.assertTrue(regenerate_button.disabled)

    def test_regenerate_button_enabled_when_clean_and_calls_shared_regeneration_once(self):
        at = self._navigate_to_purchasing(self._run(CLEAN_BOM_CSV))

        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        self.assertFalse(regenerate_button.disabled)

        with patch("workflow_runner.regenerate_purchasing") as mock_regenerate:
            regenerate_button.click()
            at.run()

        mock_regenerate.assert_called_once()
        self.assertEqual(len(at.exception), 0)

    def test_rerun_alone_never_triggers_regeneration(self):
        """
        Regeneration can create a live Mouser cart / DigiKey MyList --
        it must only happen on an explicit button click, never merely
        because Streamlit reran the script (e.g. a filter widget change).
        """
        at = self._navigate_to_purchasing(self._run(CLEAN_BOM_CSV))

        with patch("workflow_runner.regenerate_purchasing") as mock_regenerate:
            at.run()
            at.run()

        mock_regenerate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
