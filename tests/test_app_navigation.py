"""
Streamlit UI tests for the AutoBOM/PartsBox Inventory information
architecture (see render_autobom_workflow_page() in app.py): top-level
navigation is just ["AutoBOM", "PartsBox Inventory"] -- Search+Upload
(the unified "Add Parts" intake), BOM Configuration (Customer Reference
nested inside), Results/Needs Review, and Purchasing Handoff are
sections of one continuous, vertically-flowing AutoBOM page, NOT tabs
and NOT "Upload page, then Search page, then Customer Reference page".
Search and Upload are two intake methods for the SAME canonical working
BOM -- see the UnifiedIntakeTests class below. Uses
streamlit.testing.v1.AppTest (see tests/test_app_smoke.py's module
docstring for the patch-target gotcha this file follows).
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

    def test_upload_widget_is_present_on_main_workflow_page(self):
        """
        Upload is the SECONDARY intake method, beside Search -- still
        present and functional, just no longer the dominant first thing
        on the page (see render_upload_intake()).
        """
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        self.assertEqual(len(at.file_uploader), 1)

    def test_search_is_embedded_and_visible_without_any_bom_run(self):
        """
        Search is the PRIMARY/default way to add parts -- it must render
        even when current_run is None, directly on the page (not gated
        behind Upload having produced a result, and not hidden inside an
        expander the way the old standalone "Component Search" tool
        was).
        """
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        self.assertEqual(len(at.exception), 0)
        subheaders = [el.value for el in at.subheader]
        self.assertIn("Add Parts", subheaders)
        text_input_labels = [t.label for t in at.text_input]
        self.assertIn("MPN, manufacturer, or keywords", text_input_labels)

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


class UnifiedIntakeTests(unittest.TestCase):
    """
    "AutoBOM Intake + BOM Configuration UI Correction": Search is the
    default/primary intake method and starts the working BOM itself if
    none exists yet (workflow_runner.start_manual_bom_workflow()); Upload
    is the secondary side option. Both feed the exact same canonical
    ActiveBomState -- see render_add_parts_section() in app.py. Mocks
    review_actions.MouserClient/DigiKeyClient (as
    tests/test_app_smoke.py's module docstring explains) so Add to BOM
    never makes a live vendor call in these tests.
    """

    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_intake_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    @staticmethod
    def _search_result(mpn="ABC123", source="PartsBox"):
        return {
            "source": source,
            "manufacturer": "Yageo",
            "mpn": mpn,
            "description": "10k Resistor",
            "category": "",
            "package": "",
            "stock": None,
            "supplier_part_number": "",
            "unit_price": "",
            "lifecycle_status": "",
            "characteristics": {},
            "raw": {},
            "stock_sufficient": None,
        }

    def _search_and_add(self, at, candidate, qty=3):
        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = [candidate]
            next(b for b in at.button if b.key == "component_search_button").click()
            at.run()

        next(n for n in at.number_input if n.key == "add_to_bom_qty_0").set_value(qty)
        at.run()

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = None
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None
            next(b for b in at.button if b.key == "add_to_bom_button_0").click()
            at.run()

        return at

    def _upload(self, at, csv_text, filename="bom.csv"):
        for checkbox in at.checkbox:
            if checkbox.label in ("Run PartsBox", "Run supplier sourcing"):
                checkbox.set_value(False)
        at.file_uploader[0].upload(filename, csv_text.encode("utf-8"), "text/csv")
        at.run()
        next(b for b in at.button if b.label == "Process Upload").click()
        at.run()
        return at

    def test_search_add_creates_a_line_in_the_working_bom_with_no_prior_upload(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        self.assertIsNone(at.session_state["current_run"])

        self._search_and_add(at, self._search_result())

        self.assertEqual(len(at.exception), 0)
        current_run = at.session_state["current_run"]
        self.assertIsNotNone(current_run)
        rows = current_run["_active_bom_state"].rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mpn"], "ABC123")
        self.assertEqual(rows[0]["required_qty"], 3)

    def test_search_can_add_a_part_after_an_upload(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", CLEAN_BOM_CSV.encode("utf-8"))
        result = run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="",
            run_partsbox=False,
            run_sourcing=False,
            run_mouser_cart=False,
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )
        active_bom_state = result["_active_bom_state"]
        self.assertEqual(len(active_bom_state.rows()), 1)

        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.session_state["current_run"] = result
        at.run()

        self._search_and_add(at, self._search_result(mpn="EXTRACONN"))

        self.assertEqual(len(at.exception), 0)
        # Same canonical state -- Search appended to it, did not replace it.
        self.assertIs(at.session_state["current_run"]["_active_bom_state"], active_bom_state)
        mpns = {row["mpn"] for row in active_bom_state.rows()}
        self.assertEqual(mpns, {"RC0603FR-0710KL", "EXTRACONN"})

    def test_upload_can_add_parts_after_manual_search_additions(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()

        self._search_and_add(at, self._search_result(mpn="MANUALPART"))
        self.assertEqual(len(at.exception), 0)
        manual_run_id = at.session_state["current_run"]["run"]["run_id"]
        active_bom_state = at.session_state["current_run"]["_active_bom_state"]
        self.assertEqual(len(active_bom_state.rows()), 1)

        self._upload(at, CLEAN_BOM_CSV)

        self.assertEqual(len(at.exception), 0)
        # The manually-started run/state survived -- upload merged into it.
        self.assertEqual(at.session_state["current_run"]["run"]["run_id"], manual_run_id)
        self.assertIs(at.session_state["current_run"]["_active_bom_state"], active_bom_state)
        mpns = {row["mpn"] for row in active_bom_state.rows()}
        self.assertEqual(mpns, {"MANUALPART", "RC0603FR-0710KL"})

    def test_customer_reference_configurable_from_bom_configuration_area(self):
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        self._search_and_add(at, self._search_result())

        subheaders = [el.value for el in at.subheader]
        bomcfg_index = subheaders.index("BOM Configuration")
        cref_index = subheaders.index("Customer Reference")
        self.assertLess(bomcfg_index, cref_index)
        # Appears exactly once, inside BOM Configuration -- not a second,
        # independent section elsewhere on the page.
        self.assertEqual(subheaders.count("Customer Reference"), 1)

    def test_no_vendor_artifact_created_by_search_or_upload(self):
        """
        Section 17's critical side-effect rule -- adding parts via Search
        and uploading a file must never themselves create a Mouser cart
        or DigiKey MyList. Only an explicit Regenerate Purchasing click
        may (see tests/test_app_smoke.py's PurchasingPageSmokeTests for
        that boundary, and test_customer_reference_ui.py's
        test_assigning_reference_creates_no_vendor_calls for the same
        guarantee around editing a Customer Reference).
        """
        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
            at.run()
            self._search_and_add(at, self._search_result())
            self._upload(at, CLEAN_BOM_CSV)

            self.assertEqual(len(at.exception), 0)

        mock_mouser.assert_not_called()
        mock_digikey.assert_not_called()


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
