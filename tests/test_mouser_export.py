import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from mouser_export import export_mouser_list


class ExportMouserListTests(unittest.TestCase):
    """
    Mirrors tests/test_digikey_list_export.py -- export_mouser_list() is
    a second instance of that same established file-export pattern, not
    a new one (see mouser_export.py's docstring).
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_mouser_export_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_selected_supplier_column_does_not_crash(self):
        clean_bom = pd.DataFrame([{"mpn": "ABC123", "manufacturer": "Yageo"}])

        path, count = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 0)
        self.assertTrue(Path(path).exists())

    def test_filters_to_mouser_selected_rows_only(self):
        clean_bom = pd.DataFrame(
            [
                {"mpn": "A", "selected_supplier": "Mouser"},
                {"mpn": "B", "selected_supplier": "DigiKey"},
                {"mpn": "C", "selected_supplier": ""},
            ]
        )

        path, count = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 1)
        content = Path(path).read_text()
        self.assertIn("A", content)
        self.assertNotIn("B\n", content)

    def test_case_insensitive_supplier_match(self):
        clean_bom = pd.DataFrame([{"mpn": "A", "selected_supplier": "mouser"}])

        _, count = export_mouser_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 1)

    def test_customer_reference_column_included_when_present(self):
        clean_bom = pd.DataFrame(
            [{"mpn": "A", "selected_supplier": "Mouser", "customer_reference": "PRJ-ATH-DAB"}]
        )

        path, _ = export_mouser_list(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("customer_reference", content)
        self.assertIn("PRJ-ATH-DAB", content)


if __name__ == "__main__":
    unittest.main()
