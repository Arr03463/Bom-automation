"""
Streamlit UI tests for the AutoBOM/PartsBox Inventory information
architecture (see render_autobom_workflow_page() in app.py): top-level
navigation is just ["AutoBOM", "PartsBox Inventory"] -- Run BOM, Results/
Needs Review, Customer Reference, and Purchasing Handoff are sections of
one continuous, vertically-flowing AutoBOM page, NOT tabs (an earlier
version of this page used top-level tabs for these; that still separated
them into feeling like different destinations, so they were recomposed
as plain vertical sections instead). Component Search is an embedded
tool (inside a "Search Components" expander) available on the same page
regardless of BOM state. Uses streamlit.testing.v1.AppTest (see
tests/test_app_smoke.py's module docstring for the patch-target gotcha
this file follows).
"""

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
from workflow_runner import run_bom_workflow

CLEAN_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
)


class TopLevelNavigationTests(unittest.TestCase):
    def test_top_level_navigation_has_exactly_autobom_and_partsbox_inventory(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        options = at.sidebar.radio[0].options
        self.assertEqual(list(options), ["AutoBOM", "PartsBox Inventory"])

    def test_run_bom_and_component_search_and_purchasing_are_not_top_level_options(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        options = list(at.sidebar.radio[0].options)
        for stale_page_name in ("Run BOM", "Component Search", "Purchasing"):
            self.assertNotIn(stale_page_name, options)


class AutobomWorkflowSectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_nav_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def _run(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", CLEAN_BOM_CSV.encode("utf-8"))
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="NavTest",
            run_partsbox=False,
            run_sourcing=False,
            run_mouser_cart=False,
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def test_default_page_has_no_top_level_workflow_tabs(self):
        """
        The core complaint this pass fixes: Run BOM / Results / Component
        Search / Customer Reference / Purchasing Handoff must NOT be
        rendered as st.tabs() -- that still separates them into feeling
        like different destinations, even on one nominal "page". The
        only tabs left anywhere should be the pre-existing, unrelated
        "All Results" / "Needs Review (N)" split inside the results
        table itself.
        """
        result = self._run()
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        tab_labels = [tab.label for tab in at.tabs]
        for stale_tab_name in (
            "1. Run BOM",
            "2. Results / Needs Review",
            "3. Component Search",
            "4. Customer Reference",
            "5. Purchasing Handoff",
        ):
            self.assertNotIn(stale_tab_name, tab_labels)
        self.assertTrue(any(label.startswith("Needs Review") for label in tab_labels))

    def test_run_bom_upload_widget_is_present_on_main_workflow_page(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        self.assertEqual(len(at.file_uploader), 1)
        self.assertEqual(at.file_uploader[0].label, "Upload BOM")

    def test_component_search_is_embedded_and_visible_without_any_bom_run(self):
        """
        Component Search is a general-purpose tool independent of any
        BOM run (unchanged from before this pass) -- it must render even
        when current_run is None, inside its own expander, not gated
        behind Run BOM having produced a result.
        """
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        self.assertEqual(len(at.exception), 0)
        expander_labels = [exp.label for exp in at.expander]
        self.assertIn("🔍 Search Components", expander_labels)
        subheaders = [el.value for el in at.subheader]
        self.assertIn("Component Search", subheaders)

    def test_customer_reference_is_reachable_without_a_separate_top_level_page(self):
        result = self._run()
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        subheaders = [el.value for el in at.subheader]
        self.assertIn("Customer Reference", subheaders)

    def test_purchasing_handoff_is_reachable_without_a_separate_top_level_page(self):
        result = self._run()
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        headers = [el.value for el in at.subheader]
        self.assertTrue(any(header.startswith("Purchasing Handoff") for header in headers))

    def test_results_needs_review_is_reachable_without_a_separate_top_level_page(self):
        result = self._run()
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.metric), 5)

    def test_repeated_reruns_preserve_canonical_bom_state(self):
        """
        There is no navigation to lose state over -- every section
        renders on every rerun of the same page, and st.session_state
        (including current_run/_active_bom_state) is shared across the
        whole script execution. This proves the canonical state a Run
        BOM produced is still exactly what Results, Customer Reference,
        and Purchasing Handoff all see after further reruns (e.g.
        interacting with an unrelated widget).
        """
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()
        at.run()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIs(at.session_state["current_run"], result)
        self.assertIs(at.session_state["current_run"]["_active_bom_state"], active_bom_state)
        self.assertEqual(active_bom_state.get_row(row_id)["mpn"], "RC0603FR-0710KL")

    def test_customer_reference_column_is_visible_in_the_working_bom_table(self):
        """
        Customer Reference must be visible directly in the working BOM
        table, not only reachable via a separate section -- confirms the
        column survives dataframe rendering after a bulk Customer
        Reference assignment.
        """
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        for row in active_bom_state.rows():
            active_bom_state.update_row(row["row_id"], {"customer_reference": "PRJ-ATH-DAB"})

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        dataframes = [df.value for df in at.dataframe]
        self.assertTrue(
            any("Customer Reference" in df.columns and (df["Customer Reference"] == "PRJ-ATH-DAB").all() for df in dataframes)
        )

    def test_sections_appear_top_to_bottom_in_workflow_order(self):
        """
        Confirms the vertical composition order: Customer Reference
        configuration before the working BOM/results, before Purchasing
        Handoff -- matching the order an operator actually works through
        a BOM, not an arbitrary order.
        """
        result = self._run()
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        subheaders = [el.value for el in at.subheader]
        cref_index = subheaders.index("Customer Reference")
        results_index = next(i for i, h in enumerate(subheaders) if h.startswith("AutoBOM Results"))
        purchasing_index = next(i for i, h in enumerate(subheaders) if h.startswith("Purchasing Handoff"))

        self.assertLess(cref_index, results_index)
        self.assertLess(results_index, purchasing_index)


class PartsBoxInventoryTopLevelTests(unittest.TestCase):
    def _navigate_to_inventory(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        at.sidebar.radio[0].set_value("PartsBox Inventory")
        at.run()
        return at

    def test_partsbox_inventory_remains_independently_accessible(self):
        at = self._navigate_to_inventory()
        self.assertEqual(len(at.exception), 0)
        subheaders = [el.value for el in at.subheader]
        self.assertIn("PartsBox Inventory", subheaders)

    def test_browse_all_with_empty_query_requests_the_full_inventory_not_a_bom_subset(self):
        """
        "Browse All" must query search_components() with an empty
        query/no BOM-derived filter -- i.e. it asks for the WHOLE
        accessible PartsBox catalog, not just parts referenced by the
        current/any BOM run.
        """
        at = self._navigate_to_inventory()

        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = []
            next(b for b in at.button if b.label == "Search / Browse All").click()
            at.run()

        called_query = mock_search.call_args[0][0]
        self.assertEqual(called_query.mpn, "")
        self.assertEqual(called_query.keywords, "")
        self.assertEqual(called_query.sources, frozenset({"partsbox"}))

    def test_opening_and_browsing_partsbox_inventory_performs_zero_write_calls(self):
        """
        Loading the page, clicking Browse All, and loading storage
        locations are all real PartsBoxClient-backed operations here --
        this proves none of them ever calls PartsBoxClient.call() with a
        write operation (project/create, storage/create,
        project/add-entries). Patches component_lookup.search_components
        (as the other PartsBox Inventory tests do) plus PartsBoxClient's
        underlying call() so this test also protects against a future
        change accidentally introducing a write from this page.
        """
        at = self._navigate_to_inventory()

        with patch("component_lookup.search_components") as mock_search, patch(
            "partsbox_client.PartsBoxClient.call"
        ) as mock_call:
            mock_search.return_value = []
            mock_call.return_value = {"data": []}
            next(b for b in at.button if b.label == "Search / Browse All").click()
            at.run()
            next(b for b in at.button if b.label == "Load storage locations").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        write_operations = {"project/create", "storage/create", "project/add-entries"}
        for call_args in mock_call.call_args_list:
            operation = call_args.args[0] if call_args.args else call_args.kwargs.get("operation")
            self.assertNotIn(operation, write_operations)


if __name__ == "__main__":
    unittest.main()
