import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from sourcing_report import export_sourcing_report


class ExportSourcingReportCustomerReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_sourcing_report_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_customer_reference_column_included_when_present(self):
        clean_bom = pd.DataFrame(
            [{"mpn": "ABC123", "manufacturer": "Yageo", "customer_reference": "PRJ-ATH-DAB"}]
        )

        path = export_sourcing_report(clean_bom, str(self.temp_dir))

        content = Path(path).read_text()
        self.assertIn("customer_reference", content)
        self.assertIn("PRJ-ATH-DAB", content)

    def test_missing_customer_reference_column_does_not_crash(self):
        clean_bom = pd.DataFrame([{"mpn": "ABC123", "manufacturer": "Yageo"}])

        path = export_sourcing_report(clean_bom, str(self.temp_dir))

        self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
