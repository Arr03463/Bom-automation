import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_list_export import export_digikey_list


class ExportDigikeyListTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_digikey_export_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_missing_selected_supplier_column_does_not_crash(self):
        """
        A BOM that hasn't been through sourcing yet has no
        selected_supplier column at all. clean_bom.get("selected_supplier",
        "") previously returned the plain string "" (not a Series) in
        that case, and .astype(str) on a string crashed.
        """
        clean_bom = pd.DataFrame([{"mpn": "ABC123", "manufacturer": "Yageo"}])

        path, count = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 0)
        self.assertTrue(Path(path).exists())

    def test_filters_to_digikey_selected_rows_only(self):
        clean_bom = pd.DataFrame(
            [
                {"mpn": "A", "selected_supplier": "Mouser"},
                {"mpn": "B", "selected_supplier": "DigiKey"},
                {"mpn": "C", "selected_supplier": ""},
            ]
        )

        path, count = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 1)
        content = Path(path).read_text()
        self.assertIn("B", content)
        self.assertNotIn("A\n", content)

    def test_case_insensitive_supplier_match(self):
        clean_bom = pd.DataFrame([{"mpn": "A", "selected_supplier": "digikey"}])

        _, count = export_digikey_list(clean_bom, str(self.temp_dir))

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
