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
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _apptest_helpers import fresh_app_test

from partsbox_inventory import InventoryPart, PartsBoxInventorySnapshot
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
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def test_app_loads_without_exceptions(self):
        at = fresh_app_test()
        at.run()
        self.assertEqual(len(at.exception), 0)

    def test_navigating_to_component_search_has_no_exceptions(self):
        """
        Search is the default/primary way to add parts, always visible
        at the top of the main AutoBOM page (not a separate top-level
        nav destination, tab, or expander) -- simply loading the default
        "AutoBOM" page is enough to exercise it. The MPN search box
        itself is a custom component (search_events.search_event_input(),
        needed to distinguish live typing from Enter -- see
        src/search_events.py), not a plain st.text_input, so it isn't
        visible via at.text_input; the Sources checkboxes beside it are
        still plain st.checkbox widgets and are what this asserts on.
        """
        at = fresh_app_test()
        at.run()

        self.assertEqual(len(at.exception), 0)
        checkbox_labels = [c.label for c in at.checkbox]
        self.assertIn("PartsBox", checkbox_labels)
        self.assertIn("Mouser", checkbox_labels)
        self.assertIn("DigiKey", checkbox_labels)

    def test_injected_run_result_renders_results_workspace(self):
        """
        Working Parts List's summary badges are PartsBox/Mouser/DigiKey/
        Needs Review (4 metrics, no "Total Parts" tile) -- and there are
        no "All Results"/"Needs Review (N)" tabs anymore; Needs Review is
        its own always-visible master-detail section (see
        render_needs_review_section()).
        """
        result = self._run_with_review_row()

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 4)
        self.assertEqual(len(at.tabs), 0)
        markdown_headings = [el.value for el in at.markdown]
        self.assertTrue(any("Working Parts List" in heading for heading in markdown_headings))
        self.assertTrue(any("Needs Review" in heading for heading in markdown_headings))

    def test_needs_review_actions_render_without_being_invoked(self):
        result = self._run_with_review_row()

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        button_labels = [button.label for button in at.button]
        self.assertIn("Retry Exact Part", button_labels)
        self.assertIn("Find Replacement", button_labels)
        self.assertIn("Check PartsBox", button_labels)

    def test_find_replacement_click_renders_prefilled_search_without_calling_it(self):
        result = self._run_with_review_row()

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        find_replacement = next(b for b in at.button if b.label == "Find Replacement")
        find_replacement.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertIn("Search", [button.label for button in at.button])

    def test_check_partsbox_search_uses_the_shared_snapshot_not_a_live_search(self):
        """
        Check PartsBox (sources == {"partsbox"}) must filter the same
        shared snapshot (partsbox_inventory.get_snapshot()) Main Search/
        PartsBox Inventory/the location recommender use, not a second
        live-per-search PartsBox read via component_lookup.search_components()
        -- the audit's "one shared PartsBox snapshot" precondition
        applies to Needs Review too. Patched at partsbox_inventory.get_snapshot
        (the defining module, not app.get_partsbox_snapshot -- see
        PartsBoxInventorySmokeTests' docstring for why).
        """
        result = self._run_with_review_row()
        row_id = result["_active_bom_state"].rows()[0]["row_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(b for b in at.button if b.label == "Check PartsBox").click()
        at.run()

        # manufacturer matches the row's known manufacturer
        # (STMicroelectronics, from REVIEW_BOM_CSV) -- Check PartsBox
        # prefilters candidates by the row's already-known manufacturer,
        # same as Find Replacement's LookupQuery does.
        snapshot = _fake_snapshot(
            [_fake_inventory_part(part_id="p1", mpn="MATCHPART", manufacturer="STMicroelectronics")]
        )
        with patch("partsbox_inventory.get_snapshot", return_value=snapshot) as mock_get_snapshot, patch(
            "component_lookup.search_components"
        ) as mock_search_components:
            next(t for t in at.text_input if t.key == f"replacement_query_{row_id}").set_value("MATCHPART")
            at.run()
            next(b for b in at.button if b.key == f"do_replacement_search_{row_id}").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        mock_get_snapshot.assert_called_once()
        mock_search_components.assert_not_called()
        results = at.session_state[f"replacement_results_{row_id}"]
        self.assertEqual([r["mpn"] for r in results], ["MATCHPART"])
        self.assertEqual(results[0]["source"], "PartsBox")

    def test_selecting_a_replacement_updates_canonical_state_via_ui(self):
        """
        apply_replacement() re-sources the replacement through the real
        MouserClient/DigiKeyClient (no injection point from the Needs
        Review UI), so this test mocks those two classes at their
        review_actions import site -- otherwise clicking "Use Selected
        Replacement" would make live vendor API calls. The mocked Mouser
        lookup returns full stock, so the assertions below prove the row
        was genuinely re-sourced by the real sourcing decision
        (result_status/selected_supplier/supplier_order_qty all correct),
        not manually stamped from the discovery candidate.

        Row selection itself happens through st.dataframe(on_select=...),
        which AppTest cannot simulate (see streamlit's own testing.md:
        "selections on st.dataframe ... can't be triggered through
        AppTest"). This test instead injects replacement_selected_{row_id}
        directly, exactly as it already injects replacement_results_{row_id}
        below -- both stand in for real UI interaction AppTest can't drive.
        """
        result = self._run_with_review_row()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        # Simulate a completed search and an operator's row selection by
        # injecting both directly -- never calls search_components()/
        # live vendor APIs in this test, and never drives the real
        # dataframe row-selection UI (see the docstring above).
        replacement_candidate = {
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
        at.session_state[f"replacement_results_{row_id}"] = [replacement_candidate]
        at.session_state[f"replacement_selected_{row_id}"] = replacement_candidate
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

            next(b for b in at.button if b.label == "Use Selected Replacement").click()
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

        at = fresh_app_test()
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

    def test_first_upload_with_no_existing_run_creates_a_fresh_run(self):
        """
        The common/simple case: uploading a file when NO working BOM
        exists yet (fresh session, or Search never added anything) still
        creates a new run exactly as before -- run_bom_workflow() itself
        is unchanged; only how app.py decides replace-vs-merge is new
        (see render_upload_intake()). Upload is automatic now -- no
        "Process Upload" button -- so selecting the file and rerunning
        is the whole interaction (see render_upload_intake()'s
        file_id-based exactly-once fingerprint).
        """
        at = fresh_app_test()
        at.run()

        for checkbox in at.checkbox:
            if checkbox.label in ("Mouser", "DigiKey"):
                checkbox.set_value(False)
        at.file_uploader[0].upload("bom.csv", REVIEW_BOM_CSV.encode("utf-8"), "text/csv")
        at.run()

        self.assertEqual(len(at.exception), 0)
        current_run = at.session_state["current_run"]
        self.assertIsNotNone(current_run)
        self.assertEqual(len(current_run["_active_bom_state"].rows()), 1)

    def test_uploading_while_a_working_bom_exists_merges_instead_of_replacing(self):
        """
        Per the unified Search+Upload intake correction: uploading a
        second file while a working BOM already exists (started here via
        a previous upload; equally applies if it had been started via
        Search) merges its rows into the SAME canonical ActiveBomState/
        run instead of discarding what's already there -- proven by the
        first BOM's open review panel/filter state surviving, which
        reset_run_scoped_session_state() would have cleared if this had
        replaced current_run instead of merging into it.
        """
        result_a = self._run_with_review_row()
        row_id_a = result_a["_active_bom_state"].rows()[0]["row_id"]
        original_run_id = result_a["run"]["run_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result_a
        at.run()

        # Open a review row's replacement panel and set a results filter,
        # simulating mid-review state from the first BOM. Uses Check
        # PartsBox (sources == {"partsbox"}), not Find Replacement --
        # that panel's stored results are deliberately exempt from the
        # Sources-checkbox reconciliation added for Q5 (see
        # render_replacement_lookup()), so injecting a PartsBox-sourced
        # candidate here survives the Mouser/DigiKey checkboxes being
        # unchecked below, same as it did before that fix.
        next(b for b in at.button if b.label == "Check PartsBox").click()
        at.run()
        at.session_state[f"replacement_results_{row_id_a}"] = [{"source": "PartsBox", "mpn": "X"}]
        at.session_state["results_search"] = "some search text"
        at.run()

        self.assertEqual(at.session_state["selected_review_row_id"], row_id_a)

        for checkbox in at.checkbox:
            if checkbox.label in ("Mouser", "DigiKey"):
                checkbox.set_value(False)
        at.file_uploader[0].upload("bom2.csv", CLEAN_BOM_CSV.encode("utf-8"), "text/csv")
        at.run()

        self.assertEqual(len(at.exception), 0)
        # Same run/canonical state -- merged in place, not replaced.
        self.assertEqual(at.session_state["current_run"]["run"]["run_id"], original_run_id)
        self.assertIs(at.session_state["current_run"]["_active_bom_state"], result_a["_active_bom_state"])
        # Review state from the FIRST BOM survives -- proves this was a
        # merge, not a reset_run_scoped_session_state() replacement.
        self.assertEqual(at.session_state["selected_review_row_id"], row_id_a)
        self.assertEqual(at.session_state["results_search"], "some search text")
        self.assertIn(f"replacement_results_{row_id_a}", at.session_state)
        # Both the original review row and the newly uploaded row(s) are present.
        all_mpns = {row.get("mpn") for row in result_a["_active_bom_state"].rows()}
        self.assertIn("RC0603FR-0710KL", all_mpns)


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
        generation=1,
        loaded_at=time.time(),
        parts=parts,
        storage_by_id={},
        project_names=[],
    )


class FindReplacementSourceGatingTests(unittest.TestCase):
    """
    Regression coverage for the QA/QC deep-dive report's Q5: Find
    Replacement previously always captured
    st.session_state.replacement_lookup_sources = {"mouser", "digikey"}
    on click, ignoring the Sources checkboxes -- so unchecking Mouser
    still searched (and displayed) Mouser candidates. Patches
    component_lookup.search_components (the same site
    test_check_partsbox_search_uses_the_shared_snapshot_not_a_live_search
    above patches) to inspect the actual LookupQuery.sources without
    making a live vendor call.
    """

    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_find_replacement_gating_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def _run_with_review_row(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(
            workspace["input_dir"], "bom.csv", REVIEW_BOM_CSV.encode("utf-8")
        )
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="FindReplacementGatingTest",
            run_partsbox=False,
            run_sourcing=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def test_find_replacement_with_mouser_unchecked_only_searches_digikey(self):
        result = self._run_with_review_row()
        row_id = result["_active_bom_state"].rows()[0]["row_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(cb for cb in at.checkbox if cb.key == "component_search_mouser").set_value(False)
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        self.assertEqual(at.session_state["replacement_lookup_sources"], frozenset({"digikey"}))

        with patch("component_lookup.search_components") as mock_search:
            mock_search.return_value = []
            next(b for b in at.button if b.key == f"do_replacement_search_{row_id}").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        called_query = mock_search.call_args.args[0]
        self.assertEqual(called_query.sources, frozenset({"digikey"}))

    def test_find_replacement_with_no_suppliers_checked_shows_warning_and_does_not_search(self):
        result = self._run_with_review_row()
        row_id = result["_active_bom_state"].rows()[0]["row_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(cb for cb in at.checkbox if cb.key == "component_search_mouser").set_value(False)
        next(cb for cb in at.checkbox if cb.key == "component_search_digikey").set_value(False)
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("No external supplier is selected" in w.value for w in at.warning))
        self.assertNotIn(f"do_replacement_search_{row_id}", [b.key for b in at.button])

    def test_toggling_a_source_off_while_the_panel_is_open_clears_stale_results(self):
        result = self._run_with_review_row()
        row_id = result["_active_bom_state"].rows()[0]["row_id"]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(b for b in at.button if b.label == "Find Replacement").click()
        at.run()

        stale_candidate = {
            "source": "Mouser", "mpn": "STALE", "manufacturer": "STMicroelectronics",
            "supplier_part_number": "603-STALE", "unit_price": "0.1", "stock": 500,
            "description": "", "category": "", "package": "", "lifecycle_status": "",
            "characteristics": {}, "raw": {}, "stock_sufficient": None,
        }
        at.session_state[f"replacement_results_{row_id}"] = [stale_candidate]
        at.session_state[f"replacement_selected_{row_id}"] = stale_candidate
        at.run()

        next(cb for cb in at.checkbox if cb.key == "component_search_mouser").set_value(False)
        at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertNotIn(f"replacement_results_{row_id}", at.session_state)
        self.assertNotIn(f"replacement_selected_{row_id}", at.session_state)
        self.assertEqual(at.session_state["replacement_lookup_sources"], frozenset({"digikey"}))


class MainSearchPartsBoxPanelSmokeTests(unittest.TestCase):
    """
    The old standalone PartsBox Inventory page is retired -- browsing the
    full catalog is now the "Browse Inventory" button inline in Main
    Search's PartsBox panel (see tests/test_app_navigation.py's
    MainSearchBrowseInventoryTests for the page-level coverage of that
    button). These tests cover the panel's filtering/no-write-actions
    guarantees directly against a fake snapshot, patched at
    partsbox_inventory.get_snapshot (the module that DEFINES it), not
    app.get_partsbox_snapshot -- see this file's module docstring for
    why. Patches are entered via self.enterContext so they stay active
    across every .run() in a test, not just the first.
    """

    def _navigate_with_browse(self, snapshot=None):
        self.enterContext(patch("partsbox_inventory.get_snapshot", return_value=snapshot or _fake_snapshot([])))
        at = fresh_app_test()
        at.run()
        next(b for b in at.button if b.label == "Browse Inventory").click()
        at.run()
        return at

    def test_browse_inventory_loads_without_exceptions(self):
        at = self._navigate_with_browse()
        self.assertEqual(len(at.exception), 0)

    def test_browse_inventory_reuses_shared_snapshot(self):
        at = self._navigate_with_browse(_fake_snapshot([_fake_inventory_part()]))

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.dataframe[0].value), 1)

    def test_filters_use_shared_filtering_layer(self):
        at = self._navigate_with_browse(
            _fake_snapshot(
                [
                    _fake_inventory_part(part_id="p1", mpn="A", package="0603"),
                    _fake_inventory_part(part_id="p2", mpn="B", package="0805"),
                ]
            )
        )

        selectbox_labels = [s.label for s in at.selectbox]
        self.assertIn("Package", selectbox_labels)

    def test_no_write_action_buttons_are_present_anywhere(self):
        """
        No PartsBox write operation is confirmed supported through the
        UI (see the Phase 4 report) -- nowhere on the page should offer
        write actions it can't back with a verified API call.
        """
        at = self._navigate_with_browse()
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


class DynamicFacetSmokeTests(unittest.TestCase):
    def test_component_search_shows_facets_present_in_results(self):
        """
        Mouser/DigiKey results only ever populate
        component_search_supplier_results on a real Enter press in the
        search box, which is driven by search_events.py's frontend JS --
        something AppTest cannot simulate (no real browser executes
        custom-component JS in this test harness). This injects the
        post-Enter state directly, the same stand-in pattern used for
        replacement_results_{row_id} in AppSmokeTests, to exercise the
        real facet-rendering code (render_dynamic_facet_filters()) that
        runs once results exist, decoupled from the untestable Enter
        trigger itself.
        """
        fake_results = [
            _lookup_result(source="Mouser", mpn="A", package="0603", manufacturer="Yageo"),
            _lookup_result(source="DigiKey", mpn="B", package="0805", manufacturer="Murata"),
        ]
        fake_results[0]["voltage"] = "25V"
        fake_results[1]["voltage"] = "50V"

        at = fresh_app_test()
        at.session_state["component_search_supplier_results"] = fake_results
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
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def _navigate_to_purchasing(self, result):
        """
        Purchasing Handoff is a section on the single AutoBOM page now,
        not a separate top-level nav destination or a tab -- the default
        "AutoBOM" page already renders it once current_run is set, so
        there is nothing left to navigate to.
        """
        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()
        return at

    def test_purchasing_page_loads_without_exceptions(self):
        at = self._navigate_to_purchasing(self._run(CLEAN_BOM_CSV))
        self.assertEqual(len(at.exception), 0)

    def test_digikey_cart_link_ui_shows_open_and_code_no_mylist_fields(self):
        """
        Regression coverage for the direct-cart-handoff migration: the
        DigiKey panel must show the FastAdd cart link (an st.link_button
        "Open DigiKey Cart" plus the URL in an st.code() box for its
        native copy affordance) and a "Download DigiKey CSV" button, and
        must NOT show any MyList-era field (List ID, Share Identifier,
        "MyList created").
        """
        result = self._run(CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        active_bom_state.update_row(
            rows[0]["row_id"],
            {
                "selected_supplier": "DigiKey",
                "sourcing_status": "sourced_digikey",
                "supplier_part_number": "296-ABC123-ND",
                "supplier_order_qty": "10",
            },
        )
        mouser_row_id = active_bom_state.add_row(
            {
                "mpn": "XYZ456",
                "manufacturer": "Murata",
                "selected_supplier": "Mouser",
                "sourcing_status": "sourced_mouser",
                "supplier_part_number": "603-XYZ456",
                "supplier_order_qty": "5",
            }
        )
        self.assertIsNotNone(mouser_row_id)
        from workflow_runner import regenerate_purchasing

        regenerate_purchasing(result)

        at = self._navigate_to_purchasing(result)

        self.assertEqual(len(at.exception), 0)
        code_values = [c.value for c in at.code]
        self.assertTrue(any("fastadd.aspx" in value for value in code_values))
        self.assertTrue(any("296-ABC123-ND" in value for value in code_values))

        download_labels = [d.label for d in at.download_button]
        self.assertTrue(any(label.startswith("Download DigiKey CSV") for label in download_labels))
        self.assertTrue(any(label.startswith("Download Mouser CSV") for label in download_labels))

        page_text = " ".join(el.value for el in at.markdown)
        for forbidden in ("MyList", "List ID", "Share identifier", "Share Identifier"):
            self.assertNotIn(forbidden, page_text)

    def test_regenerate_button_disabled_while_review_pending(self):
        at = self._navigate_to_purchasing(self._run(REVIEW_BOM_CSV))

        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        self.assertTrue(regenerate_button.disabled)

    def test_marking_the_only_review_row_dnp_unblocks_regenerate(self):
        """
        Direct operator request: Regenerate Purchasing was unconditionally
        blocked by ANY unresolved Needs Review row with no escape hatch.
        Mark DNP is that escape hatch -- an explicit "skip this line"
        decision, not a claim it's actually sourced.
        """
        result = self._run(REVIEW_BOM_CSV)
        at = self._navigate_to_purchasing(result)
        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        self.assertTrue(regenerate_button.disabled)

        next(b for b in at.button if b.label == "Mark DNP").click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        self.assertFalse(regenerate_button.disabled)

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
        Regeneration re-exports every purchasing artifact from the
        current BOM state -- it must only happen on an explicit button
        click, never merely because Streamlit reran the script (e.g. a
        filter widget change), so downloads don't silently change
        underneath an operator mid-review.
        """
        at = self._navigate_to_purchasing(self._run(CLEAN_BOM_CSV))

        with patch("workflow_runner.regenerate_purchasing") as mock_regenerate:
            at.run()
            at.run()

        mock_regenerate.assert_not_called()

    def test_download_buttons_disable_and_reenable_per_artifact_after_regeneration(self):
        """
        Per-artifact download disabling (Phase 4 purchasing-correctness fix
        pass): a mutation disables every regeneratable download, and an
        explicit Regenerate re-enables the ones that actually came back
        current. The multi-sheet workbook now regenerates too (QA/QC
        deep-dive report, Q9) -- it no longer stays permanently disabled
        after the first post-upload edit, unlike before this fix.
        """
        result = self._run(CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"mpn": "CHANGED123"})
        from workflow_runner import refresh_response_snapshot

        refresh_response_snapshot(result)

        at = self._navigate_to_purchasing(result)

        def find(label_prefix):
            return next(b for b in at.download_button if b.label.startswith(label_prefix))

        self.assertTrue(find("Download cleaned CSV").disabled)
        self.assertTrue(find("Download cleaned workbook").disabled)

        regenerate_button = next(b for b in at.button if b.label == "Regenerate Purchasing")
        regenerate_button.click()
        at.run()

        self.assertFalse(find("Download cleaned CSV").disabled)
        self.assertFalse(find("Download cleaned workbook").disabled)


class BuildQuantityResourcingTests(unittest.TestCase):
    """
    Regression coverage for the QA/QC deep-dive report's Q2: changing
    build quantity must not leave a row's old sourcing decision (selected
    supplier, stock, supplier_order_qty) stamped as Ready once the
    recomputed required_qty exceeds what that decision actually covers.
    _apply_build_quantity() now re-sources every affected row through the
    same retry_exact_sourcing() seam Retry Exact uses, so this mocks
    review_actions.MouserClient/DigiKeyClient exactly like the existing
    Retry Exact/replacement smoke tests above -- otherwise clicking
    "Apply Build Quantity to Uploaded Lines" would make live vendor calls.
    """

    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_build_qty_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

        old_cache_enabled = os.environ.get("SUPPLIER_LOOKUP_CACHE_ENABLED")
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"
        self.addCleanup(AppSmokeTests._restore_cache_env, old_cache_enabled)

    def _run(self):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", CLEAN_BOM_CSV.encode("utf-8"))
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=1,
            project_name="BuildQtyTest",
            run_partsbox=False,
            run_sourcing=False,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    def _seed_stale_ready_decision(self, active_bom_state, row_id):
        active_bom_state.update_row(
            row_id,
            {
                "status": "clean",
                "selected_supplier": "Mouser",
                "sourcing_status": "sourced_mouser",
                "supplier_part_number": "603-OLD",
                "mouser_stock": "3",
                "supplier_order_qty": "3",
            },
        )
        self.assertEqual(active_bom_state.get_row(row_id)["result_status"], "Ready")

    def test_increasing_build_quantity_beyond_old_stock_clears_stale_ready_status(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self._seed_stale_ready_decision(active_bom_state, row_id)

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(n for n in at.number_input if n.key == "cfg_build_quantity").set_value(1000)
        at.run()

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            # Same stock (3) the stale decision already recorded -- no
            # longer enough once required_qty grows to match build
            # quantity 1000, so the row must not remain Ready.
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="RC0603FR-0710KL", stock=3,
                supplier_part_number="603-OLD",
            )
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None

            next(b for b in at.button if b.label == "Apply Build Quantity to Uploaded Lines").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        updated_row = active_bom_state.get_row(row_id)
        self.assertGreater(int(updated_row["required_qty"]), 3)
        self.assertNotEqual(updated_row["result_status"], "Ready")
        self.assertNotEqual(updated_row["selected_supplier"], "Mouser")

    def test_supplier_order_qty_matches_recomputed_requirement_after_resourcing(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self._seed_stale_ready_decision(active_bom_state, row_id)

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(n for n in at.number_input if n.key == "cfg_build_quantity").set_value(1000)
        at.run()

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="RC0603FR-0710KL", stock=5000,
                supplier_part_number="603-NEW",
            )
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None

            next(b for b in at.button if b.label == "Apply Build Quantity to Uploaded Lines").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        updated_row = active_bom_state.get_row(row_id)
        self.assertEqual(updated_row["result_status"], "Ready")
        self.assertEqual(updated_row["selected_supplier"], "Mouser")
        self.assertEqual(updated_row["supplier_part_number"], "603-NEW")
        self.assertEqual(int(updated_row["supplier_order_qty"]), int(updated_row["required_qty"]))

    def test_manually_added_row_without_qty_per_board_is_left_unchanged(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        new_row_ids = active_bom_state.add_rows(
            pd.DataFrame(
                [
                    {
                        "mpn": "MANUAL123",
                        "manufacturer": "Yageo",
                        "status": "clean",
                        "selected_supplier": "Mouser",
                        "sourcing_status": "sourced_mouser",
                        "supplier_part_number": "603-MANUAL",
                        "required_qty": "10",
                        "qty_per_board": "",
                    }
                ]
            )
        )
        manual_row_id = new_row_ids[0]

        at = fresh_app_test()
        at.session_state["current_run"] = result
        at.run()

        next(n for n in at.number_input if n.key == "cfg_build_quantity").set_value(1000)
        at.run()

        with patch("review_actions.MouserClient") as mock_mouser_cls, patch(
            "review_actions.DigiKeyClient"
        ) as mock_digikey_cls:
            # The CSV-uploaded row (qty_per_board set) is legitimately
            # re-sourced by this action -- only the manually-added row
            # (no qty_per_board) must be left untouched, so this isn't a
            # blanket "the mock was never called" assertion.
            mock_mouser_cls.return_value.find_best_match_for_row.return_value = None
            mock_digikey_cls.return_value.find_best_match_for_row.return_value = None

            next(b for b in at.button if b.label == "Apply Build Quantity to Uploaded Lines").click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        manual_row = active_bom_state.get_row(manual_row_id)
        self.assertEqual(manual_row["required_qty"], "10")
        self.assertEqual(manual_row["supplier_part_number"], "603-MANUAL")
        self.assertEqual(manual_row["selected_supplier"], "Mouser")
        self.assertEqual(manual_row["sourcing_status"], "sourced_mouser")


if __name__ == "__main__":
    unittest.main()
