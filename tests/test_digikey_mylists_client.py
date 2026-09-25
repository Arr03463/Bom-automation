import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_mylists_client import build_digikey_mylists_parts


def _row(mpn, supplier_part_number, qty, manufacturer="Yageo", customer_reference=None):
    row = {
        "mpn": mpn,
        "manufacturer": manufacturer,
        "selected_supplier": "DigiKey",
        "sourcing_status": "sourced_digikey",
        "supplier_part_number": supplier_part_number,
        "supplier_order_qty": str(qty),
    }
    if customer_reference is not None:
        row["customer_reference"] = customer_reference
    return row


class BuildDigikeyMylistsPartsCustomerReferenceTests(unittest.TestCase):
    def test_customer_reference_maps_to_customer_reference_field(self):
        clean_bom = pd.DataFrame([_row("A", "311-A-ND", 10, customer_reference="PRJ-ATH-DAB")])

        parts = build_digikey_mylists_parts(clean_bom)

        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["CustomerReference"], "PRJ-ATH-DAB")

    def test_no_customer_reference_omits_the_field(self):
        clean_bom = pd.DataFrame([_row("A", "311-A-ND", 10)])

        parts = build_digikey_mylists_parts(clean_bom)

        self.assertNotIn("CustomerReference", parts[0])

    def test_each_row_keeps_its_own_reference(self):
        clean_bom = pd.DataFrame(
            [
                _row("A", "311-A-ND", 10, customer_reference="PRJ-ATH-DAB"),
                _row("B", "311-B-ND", 5, customer_reference="INV-B04"),
            ]
        )

        parts = build_digikey_mylists_parts(clean_bom)

        by_part = {part["RequestedPartNumber"]: part.get("CustomerReference") for part in parts}
        self.assertEqual(by_part, {"311-A-ND": "PRJ-ATH-DAB", "311-B-ND": "INV-B04"})

    def test_same_part_same_reference_both_rows_kept_separately(self):
        """
        Unlike Mouser's cart, DigiKey MyList parts are never merged by
        part number -- each BOM row is already its own entry, so two rows
        for the same part (even with the same reference) both appear.
        """
        clean_bom = pd.DataFrame(
            [
                _row("A", "311-A-ND", 5, customer_reference="PRJ-ATH-DAB"),
                _row("A2", "311-A-ND", 5, customer_reference="PRJ-ATH-DAB"),
            ]
        )

        parts = build_digikey_mylists_parts(clean_bom)

        self.assertEqual(len(parts), 2)


if __name__ == "__main__":
    unittest.main()
