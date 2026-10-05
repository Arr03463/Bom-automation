import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from mouser_export import MOUSER_IMPORT_HEADERS, export_mouser_list


def _row(**overrides):
    row = {
        "mpn": "GRM188R71C105KA12D",
        "manufacturer": "Murata",
        "selected_supplier": "Mouser",
        "sourcing_status": "sourced_mouser",
        "supplier_part_number": "81-GRM188R71C105KA12D",
        "supplier_order_qty": "10",
        "customer_reference": "",
        "dnp": "",
    }
    row.update(overrides)
    return row


class ExportMouserListTests(unittest.TestCase):
    """
    export_mouser_list() now produces a Mouser supplier-IMPORT CSV built
    from purchasing_lines.build_purchasing_lines() -- see
    mouser_export.py's module docstring for the header-verification
    limitation disclosure. Mirrors
    tests/test_digikey_list_export.py -- a second instance of the same
    established pattern.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_mouser_export_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_selected_supplier_column_does_not_crash(self):
        clean_bom = pd.DataFrame([{"mpn": "ABC123", "manufacturer": "Yageo"}])

        path, result = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 0)
        self.assertTrue(result.is_valid)
        self.assertTrue(Path(path).exists())

    def test_filters_to_mouser_sourced_rows_only(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="A", supplier_part_number="603-A"),
                _row(mpn="B", selected_supplier="DigiKey", sourcing_status="sourced_digikey", supplier_part_number="296-B-ND"),
                _row(mpn="C", selected_supplier="", sourcing_status=""),
            ]
        )

        path, result = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 1)
        content = Path(path).read_text()
        self.assertIn("603-A", content)
        self.assertNotIn("296-B-ND", content)

    def test_excludes_dnp_rows(self):
        clean_bom = pd.DataFrame([_row(dnp=True)])
        path, result = export_mouser_list(clean_bom, str(self.temp_dir))
        self.assertEqual(result.item_count, 0)
        content = Path(path).read_text()
        self.assertNotIn("81-GRM188R71C105KA12D", content)

    def test_missing_supplier_part_number_is_reported_as_an_error_not_dropped(self):
        clean_bom = pd.DataFrame([_row(supplier_part_number="")])
        _, result = export_mouser_list(clean_bom, str(self.temp_dir), run_id="run1")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors[0].field, "supplier_part_number")

    def test_case_insensitive_supplier_match(self):
        clean_bom = pd.DataFrame([_row(selected_supplier="mouser", sourcing_status="sourced_mouser")])

        _, result = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(result.item_count, 1)

    def test_customer_reference_included_when_present(self):
        clean_bom = pd.DataFrame([_row(customer_reference="PRJ-ATH-DAB")])

        path, _ = export_mouser_list(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("Customer Reference", content)
        self.assertIn("PRJ-ATH-DAB", content)

    def test_golden_file_headers_and_row_shape(self):
        clean_bom = pd.DataFrame(
            [_row(mpn="GRM188R71C105KA12D", supplier_part_number="81-GRM188R71C105KA12D",
                  supplier_order_qty="25", customer_reference="PRJ-A")]
        )

        path, _ = export_mouser_list(clean_bom, str(self.temp_dir), file_stem="golden")

        lines = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], ",".join(MOUSER_IMPORT_HEADERS))
        self.assertEqual(
            lines[1],
            "81-GRM188R71C105KA12D,GRM188R71C105KA12D,25,PRJ-A",
        )

    def test_no_unresolved_or_invalid_row_reaches_the_file(self):
        clean_bom = pd.DataFrame(
            [
                _row(mpn="GOOD", supplier_part_number="603-GOOD"),
                _row(mpn="BADQTY", supplier_part_number="603-BADQTY", supplier_order_qty="1.5"),
                _row(mpn="DNPPED", dnp=True),
            ]
        )

        path, result = export_mouser_list(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("603-GOOD", content)
        self.assertNotIn("603-BADQTY", content)
        self.assertNotIn("DNPPED", content)
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
