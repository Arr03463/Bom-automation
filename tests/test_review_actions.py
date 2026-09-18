import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from active_bom_state import ActiveBomState
from mouser_cart_client import build_mouser_cart_items
from digikey_mylists_client import build_digikey_mylists_parts
from review_actions import apply_replacement, retry_exact_sourcing
from sourcing_engine import SupplierResult


class FakeSupplierClient:
    def __init__(self, result=None, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []

    def find_best_match_for_row(self, row):
        self.calls.append(dict(row))
        if self.raises:
            raise RuntimeError("supplier lookup failed")
        return self.result


def make_state(rows):
    return ActiveBomState(pd.DataFrame(rows), run_id="run-1")


class RetryExactSourcingTests(unittest.TestCase):
    def test_successful_retry_updates_canonical_state_and_result_status(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                }
            ]
        )
        mouser = FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="ABC123",
                stock=500,
                unit_price="0.02",
                supplier_part_number="603-ABC123",
            )
        )
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["sourcing_status"], "sourced_mouser")
        self.assertEqual(updated["result_status"], "Ready")
        self.assertEqual(updated["source"], "Mouser")

        # Both lookups were actually invoked -- the shared per-row
        # sourcing path, not a special retry-only shortcut.
        self.assertEqual(len(mouser.calls), 1)

    def test_failed_retry_clears_stale_supplier_fields(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "selected_supplier": "Mouser",
                    "supplier_part_number": "603-STALE",
                    "sourcing_status": "sourced_mouser",
                    "required_qty": "10",
                }
            ]
        )
        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["supplier_part_number"], "")
        self.assertEqual(updated["sourcing_status"], "check_wall_inventory")

    def test_lookup_exception_is_recorded_not_raised(self):
        state = make_state(
            [{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean", "required_qty": "10"}]
        )
        mouser = FakeSupplierClient(raises=True)
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertIn("Mouser retry failed", updated["sourcing_notes"])

    def test_unknown_row_id_raises(self):
        state = make_state([{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean"}])

        with self.assertRaises(KeyError):
            retry_exact_sourcing(state, "run-1:999", mouser_client=FakeSupplierClient(), digikey_client=FakeSupplierClient())


class ApplyReplacementTests(unittest.TestCase):
    def test_mouser_replacement_updates_state_and_reenters_cart_pipeline(self):
        state = make_state(
            [
                {
                    "mpn": "OLDPART",
                    "manufacturer": "Yageo",
                    "status": "missing_mpn",
                    "supplier_order_qty": "10",
                }
            ]
        )
        replacement = {
            "source": "Mouser",
            "mpn": "NEWPART",
            "manufacturer": "Yageo",
            "supplier_part_number": "603-NEWPART",
            "unit_price": "0.03",
            "stock": 800,
        }

        updated = apply_replacement(state, "run-1:0", replacement)

        self.assertEqual(updated["mpn"], "NEWPART")
        self.assertEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["sourcing_status"], "sourced_mouser")
        self.assertEqual(updated["result_status"], "Ready")
        self.assertEqual(updated["source"], "Mouser")

        # Traceability: original identity preserved.
        self.assertEqual(updated["original_mpn"], "OLDPART")

        # Re-enters the existing purchasing pipeline: the row now looks
        # exactly like a normally mouser-sourced row to the existing,
        # unmodified cart builder.
        cart_items = build_mouser_cart_items(state.dataframe)
        self.assertEqual(len(cart_items), 1)
        self.assertEqual(cart_items[0]["MouserPartNumber"], "603-NEWPART")

    def test_digikey_replacement_reenters_mylists_pipeline(self):
        state = make_state(
            [
                {
                    "mpn": "OLDPART",
                    "manufacturer": "TI",
                    "status": "manual_review",
                    "supplier_order_qty": "5",
                }
            ]
        )
        replacement = {
            "source": "DigiKey",
            "mpn": "NEWPART-DK",
            "manufacturer": "TI",
            "supplier_part_number": "NEWPART-DK-ND",
            "unit_price": "0.10",
            "stock": 200,
        }

        updated = apply_replacement(state, "run-1:0", replacement)

        self.assertEqual(updated["selected_supplier"], "DigiKey")
        self.assertEqual(updated["sourcing_status"], "sourced_digikey")

        parts = build_digikey_mylists_parts(state.dataframe)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["RequestedPartNumber"], "NEWPART-DK-ND")

    def test_partsbox_replacement_marks_matched_without_sourcing_status(self):
        state = make_state(
            [{"mpn": "OLDPART", "manufacturer": "Murata", "status": "manual_review"}]
        )
        replacement = {
            "source": "PartsBox",
            "mpn": "NEWPART-PB",
            "manufacturer": "Murata",
            "raw": {"part/id": "part-999"},
        }

        updated = apply_replacement(state, "run-1:0", replacement)

        self.assertEqual(updated["partsbox_match_status"], "matched")
        self.assertEqual(updated["partsbox_part_id"], "part-999")
        self.assertEqual(updated["source"], "PartsBox")
        self.assertEqual(updated["result_status"], "Ready")

    def test_replacement_regenerates_review_status_from_canonical_state(self):
        state = make_state(
            [{"mpn": "", "manufacturer": "TI", "status": "missing_mpn", "notes": "missing mpn"}]
        )
        self.assertEqual(len(state.review_items()), 1)

        apply_replacement(
            state,
            "run-1:0",
            {"source": "Mouser", "mpn": "FOUND123", "manufacturer": "TI", "supplier_part_number": "603-FOUND"},
        )

        # review_items() is derived fresh from canonical state -- no
        # separate review dataset to update by hand.
        self.assertEqual(state.review_items(), [])

    def test_unknown_row_id_raises(self):
        state = make_state([{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean"}])

        with self.assertRaises(KeyError):
            apply_replacement(state, "run-1:999", {"source": "Mouser", "mpn": "X"})


if __name__ == "__main__":
    unittest.main()
