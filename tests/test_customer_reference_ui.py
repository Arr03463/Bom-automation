"""
Streamlit UI smoke tests for the Customer Reference section on the
Purchasing page, using streamlit.testing.v1.AppTest (see
tests/test_app_smoke.py's module docstring for the patch-target gotcha
this file follows: patch at the module that DEFINES a name, e.g.
inventory_location_recommender.recommend_location, never app.recommend_location).
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
from workflow_runner import run_bom_workflow

CLEAN_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
    "C1 C2,2,Murata,GRM188R71C105KA12D,1uF Capacitor 16V 0603\n"
)


class CustomerReferenceUITests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_cref_ui_test_"))
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

    def _run(self, csv_text=CLEAN_BOM_CSV):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", csv_text.encode("utf-8"))
        return run_bom_workflow(
            source_file_path=source_path,
            build_quantity=5,
            project_name="CrefSmoke",
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

    def _select(self, at, widget_list, key, value):
        widget = next(w for w in widget_list if w.key == key)
        widget.select(value)

    def test_purchasing_page_with_customer_reference_section_loads_cleanly(self):
        at = self._navigate_to_purchasing(self._run())
        self.assertEqual(len(at.exception), 0)
        headers = [el.value for el in at.subheader]
        self.assertIn("Customer Reference", headers)

    def test_project_pcb_apply_to_all_sets_reference_on_every_line(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        at = self._navigate_to_purchasing(result)

        self._select(at, at.selectbox, "cref_project", "ATH")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "DAB")
        at.run()

        self.assertEqual(len(at.exception), 0)
        apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
        self.assertFalse(apply_button.disabled)
        apply_button.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        for row in active_bom_state.rows():
            self.assertEqual(row["customer_reference"], "PRJ-ATH-DAB")

    def test_project_pcb_multi_pcb_selection_joins_with_underscore(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        at = self._navigate_to_purchasing(result)

        self._select(at, at.selectbox, "cref_project", "ATH")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "DAB")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "BUZZ")
        at.run()

        apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
        apply_button.click()
        at.run()

        self.assertEqual(active_bom_state.rows()[0]["customer_reference"], "PRJ-ATH-DAB_BUZZ")

    def test_rnd_reference_uses_free_text_owner(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        at = self._navigate_to_purchasing(result)

        at.radio(key="cref_reference_type").set_value("R&D")
        at.run()
        self._select(at, at.selectbox, "cref_rnd_project", "ARM")
        at.run()
        owner_input = next(t for t in at.text_input if t.key == "cref_owner")
        owner_input.set_value("Aaron")
        at.run()

        apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
        apply_button.click()
        at.run()

        self.assertEqual(active_bom_state.rows()[0]["customer_reference"], "RND-ARM-AARON")

    def test_override_individual_line(self):
        result = self._run()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        at = self._navigate_to_purchasing(result)

        # Expander content already renders in AppTest regardless of open
        # state -- no need to interact with the expander widget itself.
        override_input = next(t for t in at.text_input if t.key == f"cref_override_{row_id}")
        override_input.set_value("INV-A12")
        at.run()
        save_button = next(b for b in at.button if b.key == f"cref_override_save_{row_id}")
        save_button.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        updated_row = active_bom_state.get_row(row_id)
        self.assertEqual(updated_row["customer_reference"], "INV-A12")

    def test_editing_reference_marks_purchasing_stale(self):
        result = self._run()
        at = self._navigate_to_purchasing(result)

        self._select(at, at.selectbox, "cref_project", "ATH")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "DAB")
        at.run()
        apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
        apply_button.click()
        at.run()

        self.assertTrue(result.get("stale_after_mutation"))

    def test_assigning_reference_creates_no_vendor_calls(self):
        result = self._run()
        at = self._navigate_to_purchasing(result)

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            self._select(at, at.selectbox, "cref_project", "ATH")
            at.run()
            self._select(at, at.multiselect, "cref_pcb_codes", "DAB")
            at.run()
            apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
            apply_button.click()
            at.run()

        mock_mouser.assert_not_called()
        mock_digikey.assert_not_called()

    def test_invalid_reference_disables_apply_button(self):
        result = self._run()
        at = self._navigate_to_purchasing(result)

        # A very long project/PCB combination exceeds the 30-character
        # limit -- the Apply button must be disabled, not silently
        # truncate the value.
        self._select(at, at.selectbox, "cref_project", "TBCA")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "RXCTR")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "TXCTR")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "RXTER")
        at.run()
        self._select(at, at.multiselect, "cref_pcb_codes", "TXTER")
        at.run()

        apply_button = next(b for b in at.button if b.label == "Apply to All BOM Lines")
        self.assertTrue(apply_button.disabled)

    def test_inventory_recommendation_flow(self):
        from inventory_location_recommender import CONFIDENCE_EXACT_PART, LocationRecommendation

        result = self._run()
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        at = self._navigate_to_purchasing(result)

        at.radio(key="cref_reference_type").set_value("Inventory")
        at.run()

        with patch("inventory_location_recommender.recommend_location") as mock_recommend, patch(
            "partsbox_client.PartsBoxClient"
        ) as mock_client_cls:
            mock_recommend.return_value = LocationRecommendation(
                location="A12", confidence=CONFIDENCE_EXACT_PART, reason="Exact manufacturer part already stored here."
            )
            mock_client_cls.return_value.list_storage_locations.return_value = {
                "data": [{"storage/name": "A12"}, {"storage/name": "A14"}]
            }

            recommend_button = next(b for b in at.button if b.label == "Get Recommendation")
            recommend_button.click()
            at.run()

            self.assertEqual(len(at.exception), 0)
            mock_recommend.assert_called_once()

            save_button = next(b for b in at.button if b.label == "Save Reference for This Line")
            save_button.click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        updated_row = active_bom_state.get_row(row_id)
        self.assertEqual(updated_row["customer_reference"], "INV-A12")

    def test_add_approved_project_code(self):
        temp_registry = self.temp_root / "registry.json"
        temp_registry.write_text('{"projects": {"ARM": "desc"}, "pcb_codes": {"DAB": "desc"}}', encoding="utf-8")
        old_value = os.environ.get("CUSTOMER_REFERENCE_REGISTRY_PATH")
        os.environ["CUSTOMER_REFERENCE_REGISTRY_PATH"] = str(temp_registry)
        self.addCleanup(
            lambda: os.environ.pop("CUSTOMER_REFERENCE_REGISTRY_PATH", None)
            if old_value is None
            else os.environ.__setitem__("CUSTOMER_REFERENCE_REGISTRY_PATH", old_value)
        )

        at = self._navigate_to_purchasing(self._run())

        code_input = next(t for t in at.text_input if t.key == "cref_add_code")
        code_input.set_value("NEWPROJ")
        at.run()
        description_input = next(t for t in at.text_input if t.key == "cref_add_description")
        description_input.set_value("A brand new project")
        at.run()
        save_button = next(b for b in at.button if b.key == "cref_add_save")
        save_button.click()
        at.run()

        self.assertEqual(len(at.exception), 0)
        from customer_reference_registry import is_approved_project

        self.assertTrue(is_approved_project("NEWPROJ", temp_registry))


if __name__ == "__main__":
    unittest.main()
