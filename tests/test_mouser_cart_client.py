import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from mouser_cart_client import build_mouser_cart_items


def _row(mpn, mouser_part_number, qty, customer_reference=None):
    row = {
        "mpn": mpn,
        "selected_supplier": "Mouser",
        "sourcing_status": "sourced_mouser",
        "supplier_part_number": mouser_part_number,
        "supplier_order_qty": str(qty),
    }
    if customer_reference is not None:
        row["customer_reference"] = customer_reference
    return row


class BuildMouserCartItemsCustomerReferenceTests(unittest.TestCase):
    def test_customer_reference_maps_to_customer_part_number(self):
        clean_bom = pd.DataFrame([_row("A", "603-A", 10, "PRJ-ATH-DAB")])

        items = build_mouser_cart_items(clean_bom)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["CustomerPartNumber"], "PRJ-ATH-DAB")

    def test_no_customer_reference_omits_the_field(self):
        clean_bom = pd.DataFrame([_row("A", "603-A", 10)])

        items = build_mouser_cart_items(clean_bom)

        self.assertNotIn("CustomerPartNumber", items[0])

    def test_same_part_same_reference_still_merges_quantities(self):
        clean_bom = pd.DataFrame(
            [
                _row("A", "603-A", 5, "PRJ-ATH-DAB"),
                _row("A2", "603-A", 5, "PRJ-ATH-DAB"),
            ]
        )

        items = build_mouser_cart_items(clean_bom)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["Quantity"], 10)
        self.assertEqual(items[0]["CustomerPartNumber"], "PRJ-ATH-DAB")

    def test_same_part_different_reference_stays_separate_lines(self):
        """
        Two BOM rows for the same Mouser part but different Customer
        References (e.g. one project order, one inventory restock) must
        not be merged into one line -- that would silently drop one of
        the two references.
        """
        clean_bom = pd.DataFrame(
            [
                _row("A", "603-A", 5, "PRJ-ATH-DAB"),
                _row("A2", "603-A", 3, "INV-A12"),
            ]
        )

        items = build_mouser_cart_items(clean_bom)

        self.assertEqual(len(items), 2)
        by_reference = {item["CustomerPartNumber"]: item["Quantity"] for item in items}
        self.assertEqual(by_reference, {"PRJ-ATH-DAB": 5, "INV-A12": 3})

    def test_per_line_references_preserved_across_multiple_parts(self):
        clean_bom = pd.DataFrame(
            [
                _row("A", "603-A", 10, "PRJ-ATH-DAB"),
                _row("B", "603-B", 25, "INV-B04"),
            ]
        )

        items = build_mouser_cart_items(clean_bom)

        by_part = {item["MouserPartNumber"]: item["CustomerPartNumber"] for item in items}
        self.assertEqual(by_part, {"603-A": "PRJ-ATH-DAB", "603-B": "INV-B04"})


if __name__ == "__main__":
    unittest.main()
