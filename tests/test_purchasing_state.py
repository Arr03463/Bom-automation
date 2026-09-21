"""
Tests for workflow_runner.py's purchasing-handoff functions:
derive_purchasing_status, build_purchasing_summary, regenerate_purchasing.

Every test explicitly controls MOUSER_CART_ENABLED/DIGIKEY_MYLISTS_ENABLED
rather than relying on the real .env (which has both set to "true" in
this environment) -- and mocks create_mouser_cart_from_bom()/
create_digikey_mylist_from_bom() at the workflow_runner import site
whenever a test needs those flags "true", so no test in this file ever
makes a live vendor API call.
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

from review_actions import apply_replacement
from run_workspace import build_run_workspace, save_uploaded_file
from sourcing_engine import SupplierResult
from workflow_runner import (
    build_purchasing_summary,
    derive_purchasing_status,
    regenerate_purchasing,
    run_bom_workflow,
)


CLEAN_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "R1 R2 R3,3,Yageo,RC0603FR-0710KL,10k Resistor 1% 0603\n"
    "C1 C2,2,Murata,GRM188R71C105KA12D,1uF Capacitor 16V 0603\n"
)

REVIEW_BOM_CSV = (
    "Designator,Quantity,Manufacturer,Part Number,Description\n"
    "U1,1,STMicroelectronics,,Missing part number\n"
)


class PurchasingStateTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="autobom_purchasing_test_"))
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

        self._saved_env = {}
        for key in ("MOUSER_CART_ENABLED", "DIGIKEY_MYLISTS_ENABLED", "SUPPLIER_LOOKUP_CACHE_ENABLED"):
            self._saved_env[key] = os.environ.get(key)
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def run_workflow(self, csv_text=CLEAN_BOM_CSV, project_name="PurchasingTest"):
        workspace = build_run_workspace(runs_root=self.temp_root)
        source_path = save_uploaded_file(workspace["input_dir"], "bom.csv", csv_text.encode("utf-8"))
        return run_bom_workflow(
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


class DerivePurchasingStatusTests(PurchasingStateTestCase):
    def test_not_available_without_active_state(self):
        self.assertEqual(derive_purchasing_status({"_active_bom_state": None}), "Not Available")

    def test_needs_review_when_rows_pending(self):
        result = self.run_workflow(csv_text=REVIEW_BOM_CSV)
        self.assertEqual(derive_purchasing_status(result), "Needs Review")

    def test_not_yet_generated_when_clean_and_untouched(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        self.assertEqual(derive_purchasing_status(result), "Not Yet Generated")

    def test_stale_after_mutation_takes_priority(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        result["stale_after_mutation"] = True
        self.assertEqual(derive_purchasing_status(result), "Stale — BOM Changed")

    def test_generation_failed_when_errors_present(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        result["purchasing_regeneration_errors"] = ["Mouser cart regeneration failed: boom"]
        self.assertEqual(derive_purchasing_status(result), "Generation Failed")

    def test_ready_for_handoff_after_successful_attempt(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        result["purchasing"]["mouser"] = {"attempted": True, "created": True}
        self.assertEqual(derive_purchasing_status(result), "Ready for Handoff")


class BuildPurchasingSummaryTests(PurchasingStateTestCase):
    def test_summary_counts_sourced_rows_only(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
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

        summary = build_purchasing_summary(result)

        self.assertEqual(summary["mouser"]["item_count"], 1)
        self.assertEqual(summary["mouser"]["total_quantity"], 15)
        self.assertEqual(summary["digikey"]["item_count"], 0)

    def test_unresolved_rows_excluded_from_counts(self):
        result = self.run_workflow(csv_text=REVIEW_BOM_CSV)
        summary = build_purchasing_summary(result)

        self.assertEqual(summary["mouser"]["item_count"], 0)
        self.assertEqual(summary["digikey"]["item_count"], 0)
        self.assertEqual(summary["needs_review_count"], 1)

    def test_summary_reflects_replacement_resolution(self):
        result = self.run_workflow(csv_text=REVIEW_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        mouser = _FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="STMicroelectronics",
                mpn="FOUND123",
                stock=500,
                supplier_part_number="511-FOUND123",
            )
        )
        digikey = _FakeSupplierClient(None)
        apply_replacement(
            active_bom_state,
            row_id,
            {"source": "Mouser", "mpn": "FOUND123", "manufacturer": "STMicroelectronics"},
            mouser_client=mouser,
            digikey_client=digikey,
        )

        summary = build_purchasing_summary(result)
        self.assertEqual(summary["mouser"]["item_count"], 1)
        self.assertEqual(summary["needs_review_count"], 0)


class _FakeSupplierClient:
    def __init__(self, result):
        self.result = result

    def find_best_match_for_row(self, row):
        return self.result


class RegeneratePurchasingTests(PurchasingStateTestCase):
    def test_noop_without_active_state(self):
        response = {"_active_bom_state": None}
        self.assertIs(regenerate_purchasing(response), response)

    def test_disabled_flags_are_skipped_without_any_vendor_call(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            regenerate_purchasing(result)

        mock_mouser.assert_not_called()
        mock_digikey.assert_not_called()
        self.assertFalse(result["purchasing"]["mouser"]["created"])
        self.assertFalse(result["purchasing"]["digikey"]["created"])
        self.assertEqual(result["purchasing_regeneration_errors"], [])

    def test_enabled_flags_call_existing_cart_and_mylist_functions_exactly_once(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            mock_digikey.return_value = {"created": True, "list_id": "list-1", "parts_count": 1}

            regenerate_purchasing(result)

        mock_mouser.assert_called_once()
        mock_digikey.assert_called_once()
        self.assertTrue(result["purchasing"]["mouser"]["created"])
        self.assertEqual(result["purchasing"]["mouser"]["cart_key"], "abc")
        self.assertTrue(result["purchasing"]["digikey"]["created"])
        self.assertEqual(result["purchasing"]["digikey"]["list_id"], "list-1")

    def test_regeneration_clears_stale_flag(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        result["stale_after_mutation"] = True

        regenerate_purchasing(result)

        self.assertFalse(result["stale_after_mutation"])

    def test_regeneration_records_failure_without_raising(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser:
            mock_mouser.side_effect = RuntimeError("Mouser API down")
            regenerate_purchasing(result)

        self.assertIn(
            "Mouser cart regeneration failed", " ".join(result["purchasing_regeneration_errors"])
        )
        self.assertEqual(derive_purchasing_status(result), "Generation Failed")

    def test_regeneration_reexports_current_csv_outputs(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"mpn": "CHANGED123"})

        regenerate_purchasing(result)

        csv_path = Path(result["outputs"]["cleaned_csv"])
        self.assertTrue(csv_path.exists())
        self.assertIn("CHANGED123", csv_path.read_text())

    def test_replacement_then_regeneration_produces_updated_purchasing_items(self):
        result = self.run_workflow(csv_text=REVIEW_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]

        mouser = _FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="STMicroelectronics",
                mpn="FOUND123",
                stock=500,
                supplier_part_number="511-FOUND123",
            )
        )
        apply_replacement(
            active_bom_state,
            row_id,
            {"source": "Mouser", "mpn": "FOUND123", "manufacturer": "STMicroelectronics"},
            mouser_client=mouser,
            digikey_client=_FakeSupplierClient(None),
        )

        regenerate_purchasing(result)

        summary = build_purchasing_summary(result)
        self.assertEqual(summary["mouser"]["item_count"], 1)
        self.assertEqual(summary["status"], "Ready for Handoff")


if __name__ == "__main__":
    unittest.main()
