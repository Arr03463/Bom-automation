import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from purchasing_lines import (
    PurchasingLine,
    build_purchasing_lines,
    parse_purchasing_quantity,
)


def _row(**overrides):
    row = {
        "mpn": "ABC123",
        "manufacturer": "Yageo",
        "selected_supplier": "DigiKey",
        "sourcing_status": "sourced_digikey",
        "supplier_part_number": "296-ABC123-ND",
        "supplier_order_qty": "10",
        "customer_reference": "",
        "dnp": "",
    }
    row.update(overrides)
    return row


class ParsePurchasingQuantityTests(unittest.TestCase):
    def test_accepts_positive_integer(self):
        result = parse_purchasing_quantity(10)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.value, 10)

    def test_accepts_integer_equivalent_string_and_float(self):
        for raw in ("10", "10.0", 10.0, "1,000"):
            with self.subTest(raw=raw):
                result = parse_purchasing_quantity(raw)
                self.assertTrue(result.is_valid, msg=f"{raw!r} should be valid")

    def test_rejects_fraction(self):
        result = parse_purchasing_quantity("10.5")
        self.assertFalse(result.is_valid)
        self.assertIn("fractional", result.error)

    def test_rejects_zero(self):
        result = parse_purchasing_quantity(0)
        self.assertFalse(result.is_valid)

    def test_rejects_negative(self):
        result = parse_purchasing_quantity(-5)
        self.assertFalse(result.is_valid)

    def test_rejects_blank(self):
        result = parse_purchasing_quantity("")
        self.assertFalse(result.is_valid)

    def test_rejects_none(self):
        result = parse_purchasing_quantity(None)
        self.assertFalse(result.is_valid)

    def test_rejects_malformed(self):
        result = parse_purchasing_quantity("abc")
        self.assertFalse(result.is_valid)

    def test_rejects_nan(self):
        result = parse_purchasing_quantity(float("nan"))
        self.assertFalse(result.is_valid)

    def test_rejects_infinity(self):
        result = parse_purchasing_quantity(float("inf"))
        self.assertFalse(result.is_valid)

    def test_never_truncates(self):
        """A caller must never get a truncated int back for a fraction --
        confirms the result carries no usable value on failure."""
        result = parse_purchasing_quantity("10.9")
        self.assertIsNone(result.value)


class BuildPurchasingLinesTests(unittest.TestCase):
    def test_includes_only_matching_successfully_sourced_rows(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="A", selected_supplier="DigiKey", sourcing_status="sourced_digikey"),
                _row(mpn="B", selected_supplier="Mouser", sourcing_status="sourced_mouser"),
                _row(mpn="C", selected_supplier="DigiKey", sourcing_status="check_wall_inventory"),
                _row(mpn="D", selected_supplier="", sourcing_status=""),
            ]
        )

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].mpn, "A")

    def test_case_insensitive_supplier_and_status_match(self):
        clean_bom = pd.DataFrame(
            [_row(selected_supplier="digikey", sourcing_status="SOURCED_DIGIKEY")]
        )
        result = build_purchasing_lines(clean_bom, "DigiKey")
        self.assertEqual(len(result.lines), 1)

    def test_excludes_dnp_rows_silently(self):
        clean_bom = pd.DataFrame([_row(dnp=True)])

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertTrue(result.is_valid)
        self.assertEqual(result.lines, ())
        self.assertEqual(result.errors, ())

    def test_missing_supplier_part_number_is_a_structured_error_not_an_omission(self):
        clean_bom = pd.DataFrame([_row(supplier_part_number="")])

        result = build_purchasing_lines(clean_bom, "digikey", run_id="run1")

        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].field, "supplier_part_number")
        self.assertEqual(result.errors[0].row_id, "run1:0")
        self.assertEqual(result.lines, ())

    def test_invalid_quantity_is_a_structured_error_with_row_specific_reason(self):
        clean_bom = pd.DataFrame([_row(supplier_order_qty="1.5")])

        result = build_purchasing_lines(clean_bom, "digikey", run_id="run1")

        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors[0].field, "supplier_order_qty")
        self.assertIn("fractional", result.errors[0].reason)

    def test_dnp_row_with_bad_data_is_excluded_not_errored(self):
        """DNP is checked before part-number/quantity validation -- an
        explicitly excluded line must never block handoff over data
        quality that no longer matters."""
        clean_bom = pd.DataFrame([_row(dnp=True, supplier_part_number="", supplier_order_qty="bad")])

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertTrue(result.is_valid)
        self.assertEqual(result.lines, ())

    def test_aggregates_matching_lines_by_part_and_customer_reference(self):
        clean_bom = pd.DataFrame(
            [
                _row(supplier_part_number="296-ABC-ND", supplier_order_qty="5", customer_reference="PRJ-A"),
                _row(supplier_part_number="296-ABC-ND", supplier_order_qty="3", customer_reference="PRJ-A"),
            ]
        )

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].quantity, 8)
        self.assertEqual(len(result.lines[0].source_row_ids), 2)

    def test_preserves_distinct_customer_references_as_separate_lines(self):
        clean_bom = pd.DataFrame(
            [
                _row(supplier_part_number="296-ABC-ND", supplier_order_qty="5", customer_reference="PRJ-A"),
                _row(supplier_part_number="296-ABC-ND", supplier_order_qty="3", customer_reference="PRJ-B"),
            ]
        )

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertEqual(len(result.lines), 2)
        quantities_by_reference = {line.customer_reference: line.quantity for line in result.lines}
        self.assertEqual(quantities_by_reference, {"PRJ-A": 5, "PRJ-B": 3})

    def test_deterministic_ordering_matches_first_seen_row_order(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="Z", supplier_part_number="296-Z-ND"),
                _row(mpn="A", supplier_part_number="296-A-ND"),
                _row(mpn="M", supplier_part_number="296-M-ND"),
            ]
        )

        result = build_purchasing_lines(clean_bom, "digikey")

        self.assertEqual([line.mpn for line in result.lines], ["Z", "A", "M"])

    def test_row_id_uses_run_id_prefix_matching_active_bom_state_format(self):
        clean_bom = pd.DataFrame([_row(supplier_part_number="")])
        result = build_purchasing_lines(clean_bom, "digikey", run_id="abc123")
        self.assertEqual(result.errors[0].row_id, "abc123:0")

    def test_mouser_supplier_selection(self):
        clean_bom = pd.DataFrame(
            [_row(selected_supplier="Mouser", sourcing_status="sourced_mouser", supplier_part_number="603-ABC")]
        )
        result = build_purchasing_lines(clean_bom, "mouser")
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].supplier, "mouser")

    def test_purchasing_line_result_item_count_and_total_quantity(self):
        clean_bom = pd.DataFrame(
            [
                _row(supplier_part_number="296-A-ND", supplier_order_qty="5"),
                _row(supplier_part_number="296-B-ND", supplier_order_qty="7"),
            ]
        )
        result = build_purchasing_lines(clean_bom, "digikey")
        self.assertEqual(result.item_count, 2)
        self.assertEqual(result.total_quantity, 12)

    def test_empty_bom_produces_no_lines_and_no_errors(self):
        clean_bom = pd.DataFrame(columns=["mpn", "selected_supplier", "sourcing_status"])
        result = build_purchasing_lines(clean_bom, "digikey")
        self.assertEqual(result.lines, ())
        self.assertEqual(result.errors, ())

    def test_purchasing_line_is_immutable(self):
        line = PurchasingLine(
            supplier="digikey", supplier_part_number="296-A-ND", quantity=1, customer_reference=""
        )
        with self.assertRaises(Exception):
            line.quantity = 2


if __name__ == "__main__":
    unittest.main()
