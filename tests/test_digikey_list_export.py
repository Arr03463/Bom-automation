import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_list_export import DIGIKEY_IMPORT_HEADERS, export_digikey_list


def _row(**overrides):
    row = {
        "mpn": "FSV20150V",
        "manufacturer": "Vishay",
        "selected_supplier": "DigiKey",
        "sourcing_status": "sourced_digikey",
        "supplier_part_number": "FSV20150V-ND",
        "supplier_order_qty": "10",
        "customer_reference": "",
        "dnp": "",
    }
    row.update(overrides)
    return row


class ExportDigikeyListTests(unittest.TestCase):
    """
    export_digikey_list() now produces a DigiKey supplier-IMPORT CSV
    built from purchasing_lines.build_purchasing_lines() -- see
    digikey_list_export.py's module docstring for the source of the
    verified column set.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_digikey_export_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_selected_supplier_column_does_not_crash(self):
        clean_bom = pd.DataFrame([{"mpn": "ABC123", "manufacturer": "Yageo"}])

        path, result = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 0)
        self.assertTrue(result.is_valid)
        self.assertTrue(Path(path).exists())

    def test_filters_to_digikey_sourced_rows_only(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="A", supplier_part_number="296-A-ND"),
                _row(mpn="B", selected_supplier="Mouser", sourcing_status="sourced_mouser", supplier_part_number="603-B"),
                _row(mpn="C", selected_supplier="", sourcing_status=""),
            ]
        )

        path, result = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 1)
        content = Path(path).read_text()
        self.assertIn("296-A-ND", content)
        self.assertNotIn("603-B", content)

    def test_excludes_dnp_rows(self):
        clean_bom = pd.DataFrame([_row(dnp=True)])
        path, result = export_digikey_list(clean_bom, str(self.temp_dir))
        self.assertEqual(result.item_count, 0)
        content = Path(path).read_text()
        self.assertNotIn("FSV20150V-ND", content)

    def test_missing_supplier_part_number_is_reported_as_an_error_not_dropped(self):
        """
        H3: the DigiKey CSV must include (and require) the DigiKey
        supplier part number -- a sourced row without one is a data
        problem that blocks handoff, never silently omitted.
        """
        clean_bom = pd.DataFrame([_row(supplier_part_number="")])
        _, result = export_digikey_list(clean_bom, str(self.temp_dir), run_id="run1")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors[0].field, "supplier_part_number")
        self.assertEqual(result.errors[0].row_id, "run1:0")

    def test_case_insensitive_supplier_match(self):
        clean_bom = pd.DataFrame([_row(selected_supplier="digikey", sourcing_status="sourced_digikey")])

        _, result = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 1)

    def test_customer_reference_included_when_present(self):
        clean_bom = pd.DataFrame([_row(customer_reference="INV-A12")])

        path, _ = export_digikey_list(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("Customer Reference", content)
        self.assertIn("INV-A12", content)

    def test_golden_file_headers_and_row_shape(self):
        clean_bom = pd.DataFrame(
            [_row(mpn="FSV20150V", manufacturer="Vishay", supplier_part_number="FSV20150V-ND",
                  supplier_order_qty="42", customer_reference="PRJ-A")]
        )

        path, _ = export_digikey_list(clean_bom, str(self.temp_dir), file_stem="golden")

        lines = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], ",".join(DIGIKEY_IMPORT_HEADERS))
        self.assertEqual(
            lines[1],
            "FSV20150V-ND,Vishay,FSV20150V,PRJ-A,42",
        )

    def test_supplier_part_number_column_is_present(self):
        """Direct regression check for H3: the raw output CSV columns
        must include the DigiKey supplier part number, not just MPN."""
        self.assertIn("Digi-Key Part Number", DIGIKEY_IMPORT_HEADERS)

    def test_no_unresolved_or_invalid_row_reaches_the_file(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="GOOD", supplier_part_number="296-GOOD-ND"),
                _row(mpn="BADQTY", supplier_part_number="296-BADQTY-ND", supplier_order_qty="0"),
                _row(mpn="DNPPED", dnp=True),
            ]
        )

        path, result = export_digikey_list(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("296-GOOD-ND", content)
        self.assertNotIn("296-BADQTY-ND", content)
        self.assertNotIn("DNPPED", content)
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
