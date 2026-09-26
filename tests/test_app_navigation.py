"""
Streamlit UI tests for the AutoBOM/PartsBox Inventory information
architecture (see render_autobom_workflow_page() in app.py): top-level
navigation is just ["AutoBOM", "PartsBox Inventory"] -- Search+Upload
(the unified "Add Parts" intake), Configuration (Customer Reference
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
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _apptest_helpers import fresh_app_test

from partsbox_inventory import InventoryPart, PartsBoxInventorySnapshot
from run_workspace import build_run_workspace, save_uploaded_file
from workflow_runner import run_bom_workflow, start_manual_bom_workflow

CLEAN_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
)


def _fake_inventory_part(**overrides):
    fields = {
        "part_id": "p1",
        "mpn": "ABC123",
        "manufacturer": "Yageo",
        "description": "10k Resistor",
        "category": "Resistor",
        "package": "0603",
        "characteristics": {},
        "raw": {"part/id": "p1"},
        "locations": [],
        "total_quantity": 0,
    }
    fields.update(overrides)
    return InventoryPart(**fields)


def _fake_snapshot(parts):
    return PartsBoxInventorySnapshot(
        generation=1, loaded_at=time.time(), parts=parts, storage_by_id={}, project_names=[]
    )


class TopLevelNavigationTests(unittest.TestCase):
    """
    No sidebar navigation at all now -- a single continuous page. Browse
    Inventory (the old separate "PartsBox Inventory" page) is folded into
    Main Search's PartsBox panel instead; see
    NoTopLevelNavigationTests/MainSearchBrowseInventoryTests below for
    that behavior's coverage.
    """

    def test_no_sidebar_navigation_widget_exists(self):
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.sidebar.radio), 0)


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
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def test_default_page_has_no_top_level_workflow_tabs(self):
        """
        The core complaint this pass fixes: Run BOM / Results / Component
        Search / Customer Reference / Purchasing Handoff must NOT be
        rendered as st.tabs() -- that still separates them into feeling
        like different destinations, even on one nominal "page". Needs
        Review is its own always-visible master-detail section now (see
        render_needs_review_section()), not a tab alongside "All
        Results" -- there should be no st.tabs() anywhere on this page
        at all.
        """
        result = self._run()
        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.tabs), 0)
        markdown_headings = [el.value for el in at.markdown]
        self.assertTrue(any("Needs Review" in heading for heading in markdown_headings))

    def test_upload_widget_is_present_on_main_workflow_page(self):
        """
        Upload is the SECONDARY intake method, beside Search -- still
        present and functional, just no longer the dominant first thing
        on the page (see render_upload_intake()).
        """
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.file_uploader), 1)

    def test_search_is_embedded_and_visible_without_any_bom_run(self):
        """
        Search is the PRIMARY/default way to add parts -- it must render
        even when current_run is None, directly on the page (not gated
        behind Upload having produced a result, and not hidden inside an
        expander the way the old standalone "Component Search" tool
        was). The MPN search box is a custom component
        (search_events.search_event_input()), not a plain st.text_input
        -- see tests/test_app_smoke.py's matching assertion -- so this
        checks for the Sources checkboxes beside it instead.
        """
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.exception), 0)
        subheaders = [el.value for el in at.subheader]
        self.assertIn("Add Parts", subheaders)
        checkbox_labels = [c.label for c in at.checkbox]
        self.assertIn("PartsBox", checkbox_labels)
        self.assertIn("Mouser", checkbox_labels)
        self.assertIn("DigiKey", checkbox_labels)

    def test_customer_reference_control_is_visible_before_any_bom_exists(self):
        """
        Regression: render_customer_reference_summary() was previously
        gated behind current_run existing, so the ONLY Configuration-card
        control replacing the mockup's plain "Customer part number"
        field silently disappeared on a fresh/blank page -- reported
        directly by the operator ("what happened to the customer part
        number"). It must always render, hinting that it can be
        configured now and applied once parts exist.
        """
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.exception), 0)
        captions = [c.value for c in at.caption]
        self.assertTrue(any("Customer Reference" in c for c in captions))
        self.assertTrue(any("configure now" in c.lower() for c in captions))
        self.assertGreaterEqual(len(at.get("popover")), 1)

    def test_customer_reference_is_configurable_before_any_bom_exists(self):
        """
        Follow-up to the operator's direct request ("it should be able
        to be configure[d] from the start"): the Project/PCB picker,
        live preview, and validity check must all work with no BOM at
        all -- only the actual "Apply to All BOM Lines" write is gated
        (disabled, with an explanatory caption) behind rows existing to
        write into.
        """
        at = fresh_app_test()
        at.run()

        # Re-fetch the popover block after every .run() -- like any
        # other AppTest element, a Block reference from a prior run does
        # not reflect the newly rendered tree.
        popover = at.get("popover")[0]
        self._select(popover, popover.selectbox, "cref_project", "ATH")
        at.run()
        popover = at.get("popover")[0]
        self._select(popover, popover.multiselect, "cref_pcb_codes", "DAB")
        at.run()

        self.assertEqual(len(at.exception), 0)
        popover = at.get("popover")[0]
        success_messages = [s.value for s in popover.success]
        self.assertTrue(any("PRJ-ATH-DAB" in s for s in success_messages))
        apply_button = next(b for b in popover.button if b.label == "Apply to All BOM Lines")
        self.assertTrue(apply_button.disabled)
        captions = [c.value for c in popover.caption]
        self.assertTrue(any("add parts" in c.lower() for c in captions))

    @staticmethod
    def _select(container, widget_list, key, value):
        widget = next(w for w in widget_list if w.key == key)
        widget.select(value)

    def test_customer_reference_is_reachable_without_a_separate_top_level_page(self):
        result = self._run()
        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        subheaders = [el.value for el in at.subheader]
        self.assertIn("Customer Reference", subheaders)

    def test_purchasing_handoff_is_reachable_without_a_separate_top_level_page(self):
        result = self._run()
        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        headers = [el.value for el in at.subheader]
        self.assertTrue(any(header.startswith("Purchasing Handoff") for header in headers))

    def test_results_needs_review_is_reachable_without_a_separate_top_level_page(self):
        """
        Working Parts List's summary badges are PartsBox/Mouser/DigiKey/
        Needs Review (4 metrics) now -- no separate "Total Parts" tile,
        matching the frontend design spec's `counts` list.
        """
        result = self._run()
        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.metric), 4)

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

        at = fresh_app_test()
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

        at = fresh_app_test()
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
        at = fresh_app_test()
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
        """
        Row selection happens through st.dataframe(on_select=...), which
        AppTest cannot simulate (see tests/test_app_smoke.py's docstring
        on the same limitation). This injects the selection directly
        into component_search_selected_part -- the same session-state
        seam the real dataframe selection writes to (see
        render_component_search_intake()) -- then drives the real
        shared Selected Part Details panel (quantity input + Add to BOM
        button) exactly as an operator would after picking a row.
        """
        at.session_state["component_search_selected_part"] = candidate
        at.run()

        next(n for n in at.number_input if n.key == "component_search_add_qty").set_value(qty)
        at.run()

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = None
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None
            next(b for b in at.button if b.key == "component_search_add_button").click()
            at.run()

        return at

    def _upload(self, at, csv_text, filename="bom.csv"):
        """Upload is automatic now -- no "Process Upload" button to click."""
        for checkbox in at.checkbox:
            if checkbox.label in ("Mouser", "DigiKey"):
                checkbox.set_value(False)
        at.file_uploader[0].upload(filename, csv_text.encode("utf-8"), "text/csv")
        at.run()
        return at

    def test_search_add_creates_a_line_in_the_working_bom_with_no_prior_upload(self):
        at = fresh_app_test()
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
            run_digikey_mylist=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )
        active_bom_state = result["_active_bom_state"]
        self.assertEqual(len(active_bom_state.rows()), 1)

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        self._search_and_add(at, self._search_result(mpn="EXTRACONN"))

        self.assertEqual(len(at.exception), 0)
        # Same canonical state -- Search appended to it, did not replace it.
        self.assertIs(at.session_state["current_run"]["_active_bom_state"], active_bom_state)
        mpns = {row["mpn"] for row in active_bom_state.rows()}
        self.assertEqual(mpns, {"RC0603FR-0710KL", "EXTRACONN"})

    def test_upload_can_add_parts_after_manual_search_additions(self):
        at = fresh_app_test()
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
        at = fresh_app_test()
        at.run()
        self._search_and_add(at, self._search_result())

        subheaders = [el.value for el in at.subheader]
        cfg_index = subheaders.index("Configuration")
        cref_index = subheaders.index("Customer Reference")
        self.assertLess(cfg_index, cref_index)
        # Appears exactly once, inside Configuration -- not a second,
        # independent section elsewhere on the page.
        self.assertEqual(subheaders.count("Customer Reference"), 1)

    def test_no_vendor_artifact_created_by_search_or_upload(self):
        """
        Section 17's critical side-effect rule -- adding parts via Search
        and uploading a file must never themselves create a DigiKey
        MyList. Only an explicit Regenerate Purchasing click may (see
        tests/test_app_smoke.py's PurchasingPageSmokeTests for that
        boundary, and test_customer_reference_ui.py's
        test_assigning_reference_creates_no_vendor_calls for the same
        guarantee around editing a Customer Reference). Mouser has no
        vendor call to guard here at all anymore -- it's a plain file
        export (see mouser_export.py), not a vendor side effect.
        """
        with patch("workflow_runner.create_digikey_mylist_from_bom") as mock_digikey:
            at = fresh_app_test()
            at.run()
            self._search_and_add(at, self._search_result())
            self._upload(at, CLEAN_BOM_CSV)

            self.assertEqual(len(at.exception), 0)

        mock_digikey.assert_not_called()

    def test_configuration_section_is_shared_and_has_no_upload_specific_settings(self):
        """
        Sections 2/3/13: Configuration is one shared section below Add
        Parts, not an "Upload settings" expander attached to Upload --
        and the redundant sourcing toggles (section 6/7) are gone
        entirely, replaced by the Sources checkboxes next to Search.
        """
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.exception), 0)
        subheaders = [el.value for el in at.subheader]
        add_parts_index = subheaders.index("Add Parts")
        cfg_index = subheaders.index("Configuration")
        self.assertLess(add_parts_index, cfg_index)

        expander_labels = [exp.label for exp in at.expander]
        self.assertNotIn("Upload settings", expander_labels)

        checkbox_labels = {cb.label for cb in at.checkbox}
        for stale_label in ("Run supplier sourcing", "Use Mouser sourcing", "Use DigiKey sourcing", "Run PartsBox"):
            self.assertNotIn(stale_label, checkbox_labels)
        self.assertIn("Update PartsBox Project", checkbox_labels)

    def test_project_name_field_is_operator_friendly_not_partsbox_labeled(self):
        """Section 4: "PartsBox project name" -> "Project Name"."""
        at = fresh_app_test()
        at.run()

        text_input_labels = [t.label for t in at.text_input]
        self.assertIn("Project Name", text_input_labels)
        self.assertNotIn("PartsBox project name", text_input_labels)

    def test_source_checkboxes_control_upload_sourcing_too(self):
        """
        Sections 6/7/15: the Sources checkboxes beside Search are
        authoritative for the whole sourcing job, including uploaded
        parts -- there is no separate "use Mouser/DigiKey sourcing"
        toggle for Upload. Unchecking Mouser here must turn off Mouser
        sourcing for an upload too.
        """
        at = fresh_app_test()
        at.run()

        next(cb for cb in at.checkbox if cb.key == "component_search_mouser").set_value(False)
        at.run()

        with patch("workflow_runner.run_bom_workflow") as mock_run:
            mock_run.return_value = start_manual_bom_workflow()
            at.file_uploader[0].upload("bom.csv", CLEAN_BOM_CSV.encode("utf-8"), "text/csv")
            at.run()

        self.assertEqual(len(at.exception), 0)
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        self.assertFalse(kwargs["use_mouser_sourcing"])
        self.assertTrue(kwargs["use_digikey_sourcing"])
        # DigiKey alone still selected -- sourcing must still run.
        self.assertTrue(kwargs["run_sourcing"])

    def test_mouser_purchasing_handoff_exposes_downloadable_export(self):
        """
        Section 12: Mouser's current-workflow output is a downloadable
        export, not a cart-creation status -- confirmed by regenerating
        purchasing (DigiKey disabled so this makes no live vendor call)
        and checking the resulting Mouser export file is offered as a
        download.
        """
        result = run_bom_workflow(
            source_file_path=save_uploaded_file(
                build_run_workspace(runs_root=self.temp_root)["input_dir"],
                "bom.csv",
                CLEAN_BOM_CSV.encode("utf-8"),
            ),
            build_quantity=5,
            project_name="",
            run_partsbox=False,
            run_sourcing=False,
            run_digikey_mylist=False,
            run_id="mouser-export-test",
            output_folder=str(self.temp_root / "out"),
        )
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(
            row_id,
            {
                "selected_supplier": "Mouser",
                "supplier_part_number": "603-ABC123",
                "sourcing_status": "sourced_mouser",
                "supplier_order_qty": "15",
            },
        )

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        regenerate_button.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        download_labels = {b.label for b in at.download_button}
        self.assertTrue(any("Download Mouser Export" in label for label in download_labels))


class SearchSelectionAndStaleResultsLifecycleTests(unittest.TestCase):
    """
    Per Documentation/AutoBOM_Interaction_Specification.md §1: a
    selection persists across unrelated reruns but clears on an
    incompatible query/source change, and diverging the draft from the
    last committed Enter query marks (not clears) supplier results as
    stale. Injects session state directly for anything AppTest can't
    drive (the search box's own typing/Enter, and row selection) --
    same established pattern as elsewhere in this suite.
    """

    @staticmethod
    def _candidate(source="PartsBox", mpn="ABC123"):
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

    def test_clear_button_resets_draft_and_supplier_results_and_selection(self):
        at = fresh_app_test()
        at.session_state["component_search_text"] = "old query"
        at.session_state["component_search_supplier_results"] = [self._candidate(source="Mouser")]
        at.session_state["component_search_last_submitted"] = ("old query", ("mouser", "digikey"))
        at.session_state["component_search_selected_part"] = self._candidate(source="Mouser")
        at.run()

        next(b for b in at.button if b.label == "✕ Clear").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["component_search_text"], "")
        self.assertEqual(at.session_state["component_search_supplier_results"], [])
        self.assertIsNone(at.session_state["component_search_last_submitted"])
        self.assertIsNone(at.session_state["component_search_selected_part"])

    def test_unchecking_the_selections_source_clears_it(self):
        at = fresh_app_test()
        at.session_state["component_search_selected_part"] = self._candidate(source="Mouser")
        at.run()
        self.assertIsNotNone(at.session_state["component_search_selected_part"])

        next(cb for cb in at.checkbox if cb.key == "component_search_mouser").set_value(False)
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIsNone(at.session_state["component_search_selected_part"])

    def test_unrelated_filter_change_does_not_clear_a_still_matching_selection(self):
        """
        Contrast case for the above: a selection must NOT be cleared
        just because some other widget on the page reran -- only an
        incompatible source/query change clears it.
        """
        at = fresh_app_test()
        at.session_state["component_search_selected_part"] = self._candidate(source="Mouser")
        at.run()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIsNotNone(at.session_state["component_search_selected_part"])

    def test_stale_supplier_caption_appears_when_draft_diverges_from_last_query(self):
        at = fresh_app_test()
        at.session_state["component_search_supplier_results"] = [self._candidate(source="Mouser")]
        at.session_state["component_search_last_submitted"] = ("OLDQUERY", ("mouser",))
        at.session_state["component_search_text"] = "OLDQUERY"
        at.run()

        captions = [c.value for c in at.caption]
        self.assertFalse(any("press Enter to update" in c for c in captions))

        # Force the widget back to a fresh instance seeded with a
        # DIFFERENT draft than the last committed query -- simulates the
        # operator having typed further without pressing Enter again.
        at.session_state["component_search_event_generation"] = (
            at.session_state.get("component_search_event_generation", 0) + 1
        )
        at.session_state["component_search_text"] = "NEWDRAFT"
        at.run()

        captions = [c.value for c in at.caption]
        self.assertTrue(any("press Enter to update" in c for c in captions))
        self.assertTrue(any("OLDQUERY" in c for c in captions))
        # Still shown, not cleared -- staleness marks, never hides.
        self.assertEqual(len(at.session_state["component_search_supplier_results"]), 1)


class MainSearchBrowseInventoryTests(unittest.TestCase):
    """
    "Browse Inventory" folds the old standalone PartsBox Inventory page
    into Main Search's PartsBox panel: clicking it shows the COMPLETE
    shared snapshot with no query typed, exactly like the old page's
    empty-search-shows-everything behavior -- just without a separate
    nav destination. Patched at partsbox_inventory.get_snapshot (the
    defining module, not app.get_partsbox_snapshot -- AppTest re-execs
    app.py's `from partsbox_inventory import get_snapshot as
    get_partsbox_snapshot` fresh on every .run(), so only a patch on the
    defining module is picked up; see tests/test_app_smoke.py's module
    docstring for the same gotcha elsewhere in this file).
    """

    def _navigate_with_snapshot(self, snapshot=None):
        self.enterContext(
            patch("partsbox_inventory.get_snapshot", return_value=snapshot or _fake_snapshot([]))
        )
        at = fresh_app_test()
        at.run()
        return at

    def test_browse_inventory_shows_the_full_catalog_with_no_query_typed(self):
        snapshot = _fake_snapshot(
            [
                _fake_inventory_part(part_id="p1", mpn="A"),
                _fake_inventory_part(part_id="p2", mpn="B"),
                _fake_inventory_part(part_id="p3", mpn="C"),
            ]
        )
        at = self._navigate_with_snapshot(snapshot)

        next(b for b in at.button if b.label == "Browse Inventory").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe[0].value), 3)

    def test_browsing_inventory_performs_zero_write_calls(self):
        """
        Browsing is a real PartsBoxClient-backed read here (the snapshot
        is NOT mocked away, unlike the other test in this class) -- this
        proves get_snapshot()'s real fetch never calls
        PartsBoxClient.call() with a write operation (project/create,
        storage/create, project/add-entries). Patches PartsBoxClient's
        underlying call() so this test also protects against a future
        change accidentally introducing a write from this panel.
        """
        with patch("partsbox_client.PartsBoxClient.call") as mock_call:
            mock_call.return_value = {"data": []}
            at = fresh_app_test()
            at.run()
            next(b for b in at.button if b.label == "Browse Inventory").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertGreater(mock_call.call_count, 0)
        write_operations = {"project/create", "storage/create", "project/add-entries"}
        for call_args in mock_call.call_args_list:
            operation = call_args.args[0] if call_args.args else call_args.kwargs.get("operation")
            self.assertNotIn(operation, write_operations)


if __name__ == "__main__":
    unittest.main()
