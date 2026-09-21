"""
Tests for workflow_runner.py's purchasing-handoff functions:
derive_purchasing_status, build_purchasing_summary, regenerate_purchasing,
and the per-artifact freshness/state model (artifact_status) that backs
them.

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
    refresh_response_snapshot,
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

    def make_mouser_sourced(self, active_bom_state, row_id, mpn="603-ABC123", qty="15"):
        active_bom_state.update_row(
            row_id,
            {
                "selected_supplier": "Mouser",
                "supplier_part_number": mpn,
                "sourcing_status": "sourced_mouser",
                "supplier_order_qty": qty,
            },
        )

    def make_digikey_sourced(self, active_bom_state, row_id, mpn="296-XYZ", qty="10"):
        active_bom_state.update_row(
            row_id,
            {
                "selected_supplier": "DigiKey",
                "supplier_part_number": mpn,
                "sourcing_status": "sourced_digikey",
                "supplier_order_qty": qty,
            },
        )


class _FakeSupplierClient:
    def __init__(self, result):
        self.result = result

    def find_best_match_for_row(self, row):
        return self.result


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
        result["artifact_status"]["cleaned_csv"] = "current"
        refresh_response_snapshot(result)
        self.assertEqual(derive_purchasing_status(result), "Stale — BOM Changed")

    def test_zero_required_items_after_regeneration_is_ready_for_handoff(self):
        # Nothing ever attempted (fresh run) reports "Not Yet Generated";
        # once an explicit regeneration has actually run and there was
        # nothing required from either supplier, there is nothing left to
        # do -- that must read as ready, not stuck at "not yet".
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        regenerate_purchasing(result)

        self.assertEqual(derive_purchasing_status(result), "Ready for Handoff")

    def test_required_supplier_with_created_false_is_not_ready(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser:
            mock_mouser.return_value = {"created": False, "items_count": 0, "message": "rejected"}
            regenerate_purchasing(result)

        self.assertEqual(result["artifact_status"]["mouser_cart"], "failed")
        self.assertNotEqual(derive_purchasing_status(result), "Ready for Handoff")
        self.assertEqual(derive_purchasing_status(result), "Generation Failed")

    def test_supplier_with_zero_required_items_does_not_require_artifact(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser:
            mock_mouser.return_value = {
                "created": True,
                "items_count": 1,
                "result": {"CartKey": "abc"},
            }
            regenerate_purchasing(result)

        self.assertEqual(result["artifact_status"]["digikey_mylist"], "not_required")
        self.assertEqual(derive_purchasing_status(result), "Ready for Handoff")

    def test_both_required_suppliers_created_successfully_is_ready_for_handoff(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            mock_digikey.return_value = {"created": True, "list_id": "list-1", "parts_count": 1}
            regenerate_purchasing(result)

        self.assertEqual(derive_purchasing_status(result), "Ready for Handoff")


class BuildPurchasingSummaryTests(PurchasingStateTestCase):
    def test_summary_counts_sourced_rows_only(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)

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

    def test_purchasing_item_counts_derive_from_current_canonical_bom(self):
        """
        build_purchasing_summary() must read item counts from the LIVE
        ActiveBomState dataframe on every call, not from a snapshot taken
        at some earlier point -- a second mutation must be reflected
        immediately, with no regeneration required just to see updated
        counts (regeneration is only needed to actually create the
        cart/list artifacts).
        """
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()

        self.assertEqual(build_purchasing_summary(result)["mouser"]["item_count"], 0)

        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.assertEqual(build_purchasing_summary(result)["mouser"]["item_count"], 1)

        self.make_mouser_sourced(active_bom_state, rows[1]["row_id"], mpn="603-DEF456")
        self.assertEqual(build_purchasing_summary(result)["mouser"]["item_count"], 2)


class RegeneratePurchasingTests(PurchasingStateTestCase):
    def test_noop_without_active_state(self):
        response = {"_active_bom_state": None}
        self.assertIs(regenerate_purchasing(response), response)

    def test_disabled_flags_are_skipped_without_any_vendor_call(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            regenerate_purchasing(result)

        mock_mouser.assert_not_called()
        mock_digikey.assert_not_called()
        self.assertFalse(result["purchasing"]["mouser"]["created"])
        self.assertEqual(result["purchasing_regeneration_errors"], [])

    def test_enabled_flags_call_existing_cart_and_mylist_functions_exactly_once(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
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
        self.assertEqual(result["artifact_status"]["mouser_cart"], "current")
        self.assertEqual(result["artifact_status"]["digikey_mylist"], "current")

    def test_regeneration_records_failure_without_raising(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser:
            mock_mouser.side_effect = RuntimeError("Mouser API down")
            regenerate_purchasing(result)

        self.assertIn(
            "Mouser cart regeneration failed", " ".join(result["purchasing_regeneration_errors"])
        )
        self.assertEqual(result["artifact_status"]["mouser_cart"], "failed")
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
        os.environ["MOUSER_CART_ENABLED"] = "true"
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

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            regenerate_purchasing(result)

        summary = build_purchasing_summary(result)
        self.assertEqual(summary["mouser"]["item_count"], 1)
        self.assertEqual(summary["status"], "Ready for Handoff")

    # --- Per-artifact freshness / failure-isolation tests (Phase 4 fix pass) ---

    def test_partial_regeneration_mouser_success_digikey_failure(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            mock_digikey.side_effect = RuntimeError("DigiKey API down")
            regenerate_purchasing(result)

        self.assertEqual(result["artifact_status"]["mouser_cart"], "current")
        self.assertEqual(result["artifact_status"]["digikey_mylist"], "failed")
        self.assertTrue(result["purchasing"]["mouser"]["created"])
        self.assertEqual(result["purchasing"]["mouser"]["cart_key"], "abc")
        self.assertEqual(derive_purchasing_status(result), "Partial — Generation Failed")

    def test_partial_regeneration_digikey_success_mouser_failure(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.side_effect = RuntimeError("Mouser API down")
            mock_digikey.return_value = {"created": True, "list_id": "list-1", "parts_count": 1}
            regenerate_purchasing(result)

        self.assertEqual(result["artifact_status"]["digikey_mylist"], "current")
        self.assertEqual(result["artifact_status"]["mouser_cart"], "failed")
        self.assertTrue(result["purchasing"]["digikey"]["created"])
        self.assertEqual(derive_purchasing_status(result), "Partial — Generation Failed")

    def test_retry_after_partial_failure_does_not_recreate_successful_supplier_artifact(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            mock_digikey.side_effect = RuntimeError("DigiKey API down")
            regenerate_purchasing(result)

            # Retry: DigiKey now succeeds. Mouser must not be re-invoked --
            # it is already STATUS_CURRENT for this unchanged BOM state.
            mock_digikey.side_effect = None
            mock_digikey.return_value = {"created": True, "list_id": "list-1", "parts_count": 1}
            regenerate_purchasing(result)

        mock_mouser.assert_called_once()
        self.assertEqual(mock_digikey.call_count, 2)
        self.assertEqual(result["artifact_status"]["mouser_cart"], "current")
        self.assertEqual(result["artifact_status"]["digikey_mylist"], "current")
        # The CartKey from the original successful attempt survives.
        self.assertEqual(result["purchasing"]["mouser"]["cart_key"], "abc")
        self.assertEqual(derive_purchasing_status(result), "Ready for Handoff")

    def test_one_explicit_regeneration_click_creates_each_required_artifact_at_most_once(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        rows = active_bom_state.rows()
        self.make_mouser_sourced(active_bom_state, rows[0]["row_id"])
        self.make_digikey_sourced(active_bom_state, rows[1]["row_id"])
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            mock_mouser.return_value = {"created": True, "items_count": 1, "result": {"CartKey": "abc"}}
            mock_digikey.return_value = {"created": True, "list_id": "list-1", "parts_count": 1}
            regenerate_purchasing(result)

        self.assertEqual(mock_mouser.call_count, 1)
        self.assertEqual(mock_digikey.call_count, 1)

    def test_plain_rerun_creates_no_vendor_artifact(self):
        """
        Reading purchasing state (as every Streamlit rerun does, simply by
        re-executing the page function) must never call the vendor
        creation functions -- only an explicit regenerate_purchasing()
        call may.
        """
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        self.make_mouser_sourced(active_bom_state, row_id)
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        with patch("workflow_runner.create_mouser_cart_from_bom") as mock_mouser, patch(
            "workflow_runner.create_digikey_mylist_from_bom"
        ) as mock_digikey:
            for _ in range(3):
                build_purchasing_summary(result)
                derive_purchasing_status(result)

        mock_mouser.assert_not_called()
        mock_digikey.assert_not_called()

    def test_cleaned_csv_failure_is_caught_and_reported(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.export_clean_bom") as mock_export:
            mock_export.side_effect = RuntimeError("disk full")
            response = regenerate_purchasing(result)

        self.assertIs(response, result)
        self.assertEqual(result["artifact_status"]["cleaned_csv"], "failed")
        self.assertIn("Cleaned CSV regeneration failed", " ".join(result["purchasing_regeneration_errors"]))
        # Other independent artifacts still regenerated successfully.
        self.assertEqual(result["artifact_status"]["sourcing_report"], "current")

    def test_one_export_failure_keeps_only_that_artifact_stale_or_failed(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"

        with patch("workflow_runner.export_digikey_list") as mock_export:
            mock_export.side_effect = RuntimeError("boom")
            regenerate_purchasing(result)

        self.assertEqual(result["artifact_status"]["digikey_list_csv"], "failed")
        self.assertEqual(result["artifact_status"]["cleaned_csv"], "current")
        self.assertEqual(result["artifact_status"]["sourcing_report"], "current")

    def test_stale_workbook_remains_unavailable_after_other_artifacts_regenerate(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        self.assertEqual(result["artifact_status"]["cleaned_workbook"], "current")

        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"mpn": "CHANGED123"})
        refresh_response_snapshot(result)
        self.assertEqual(result["artifact_status"]["cleaned_workbook"], "stale")

        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        regenerate_purchasing(result)

        # Every regeneratable artifact came back current...
        self.assertEqual(result["artifact_status"]["cleaned_csv"], "current")
        self.assertEqual(result["artifact_status"]["sourcing_report"], "current")
        # ...but the workbook was never touched and stays disabled.
        self.assertEqual(result["artifact_status"]["cleaned_workbook"], "stale")

    def test_partsbox_unmatched_csv_regenerated_or_remains_unavailable(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        result["artifact_status"]["partsbox_unmatched_csv"] = "current"

        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"mpn": "CHANGED123"})
        refresh_response_snapshot(result)
        self.assertEqual(result["artifact_status"]["partsbox_unmatched_csv"], "stale")

        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        regenerate_purchasing(result)

        # regenerate_purchasing() never re-derives PartsBox unmatched rows
        # (that requires a fresh, side-effecting project/get-entries call)
        # -- it must remain disabled, not silently re-enabled.
        self.assertEqual(result["artifact_status"]["partsbox_unmatched_csv"], "stale")

    def test_stale_downloads_never_become_enabled_merely_because_another_artifact_succeeded(self):
        result = self.run_workflow(csv_text=CLEAN_BOM_CSV)
        active_bom_state = result["_active_bom_state"]
        row_id = active_bom_state.rows()[0]["row_id"]
        active_bom_state.update_row(row_id, {"mpn": "CHANGED123"})
        refresh_response_snapshot(result)

        os.environ["MOUSER_CART_ENABLED"] = "false"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        with patch("workflow_runner.export_sourcing_report") as mock_export:
            mock_export.side_effect = RuntimeError("boom")
            regenerate_purchasing(result)

        # cleaned_csv succeeded and is current; sourcing_report failed and
        # must stay disabled regardless of cleaned_csv's success.
        self.assertEqual(result["artifact_status"]["cleaned_csv"], "current")
        self.assertEqual(result["artifact_status"]["sourcing_report"], "failed")


if __name__ == "__main__":
    unittest.main()
