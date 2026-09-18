import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from record_filter import apply_filters, search_and_filter, text_search


def make_records():
    return [
        {
            "mpn": "ABC123",
            "manufacturer": "Yageo",
            "description": "10k Resistor",
            "designators": "R1, R2",
            "source": "Mouser",
            "status": "Ready",
            "stock": 500,
        },
        {
            "mpn": "XYZ789",
            "manufacturer": "TI",
            "description": "Op Amp",
            "designators": "U1",
            "source": "DigiKey",
            "status": "Needs Review",
            "stock": 0,
        },
        {
            "mpn": "GRM188",
            "manufacturer": "Murata",
            "description": "1uF Capacitor",
            "designators": "C1, C2",
            "source": "PartsBox",
            "status": "Ready",
            "stock": 12,
        },
    ]


class TextSearchTests(unittest.TestCase):
    def test_matches_mpn(self):
        records = make_records()
        result = text_search(records, "abc123", ["mpn", "manufacturer", "description", "designators"])
        self.assertEqual([r["mpn"] for r in result], ["ABC123"])

    def test_matches_manufacturer_case_insensitive(self):
        records = make_records()
        result = text_search(records, "yageo", ["mpn", "manufacturer", "description", "designators"])
        self.assertEqual([r["mpn"] for r in result], ["ABC123"])

    def test_matches_description(self):
        records = make_records()
        result = text_search(records, "capacitor", ["mpn", "manufacturer", "description", "designators"])
        self.assertEqual([r["mpn"] for r in result], ["GRM188"])

    def test_matches_designators(self):
        records = make_records()
        result = text_search(records, "u1", ["mpn", "manufacturer", "description", "designators"])
        self.assertEqual([r["mpn"] for r in result], ["XYZ789"])

    def test_empty_query_returns_all(self):
        records = make_records()
        result = text_search(records, "", ["mpn"])
        self.assertEqual(len(result), 3)

    def test_no_match_returns_empty(self):
        records = make_records()
        result = text_search(records, "nonexistent", ["mpn", "manufacturer"])
        self.assertEqual(result, [])


class ApplyFiltersTests(unittest.TestCase):
    def test_source_filter(self):
        records = make_records()
        result = apply_filters(records, {"source": "Mouser"})
        self.assertEqual([r["mpn"] for r in result], ["ABC123"])

    def test_status_filter(self):
        records = make_records()
        result = apply_filters(records, {"status": "Needs Review"})
        self.assertEqual([r["mpn"] for r in result], ["XYZ789"])

    def test_all_sentinel_is_ignored(self):
        records = make_records()
        result = apply_filters(records, {"source": "All"})
        self.assertEqual(len(result), 3)

    def test_empty_filter_dict_returns_all(self):
        records = make_records()
        self.assertEqual(apply_filters(records, {}), records)

    def test_combined_source_and_status_filters(self):
        records = make_records()
        result = apply_filters(records, {"source": "PartsBox", "status": "Ready"})
        self.assertEqual([r["mpn"] for r in result], ["GRM188"])

    def test_combined_filters_no_match(self):
        records = make_records()
        result = apply_filters(records, {"source": "PartsBox", "status": "Needs Review"})
        self.assertEqual(result, [])

    def test_in_stock_filter(self):
        records = make_records()
        result = apply_filters(records, {"stock": "In Stock"})
        self.assertEqual({r["mpn"] for r in result}, {"ABC123", "GRM188"})

    def test_out_of_stock_filter(self):
        records = make_records()
        result = apply_filters(records, {"stock": "Out of Stock"})
        self.assertEqual([r["mpn"] for r in result], ["XYZ789"])

    def test_unknown_stock_filter_is_distinct_from_out_of_stock(self):
        records = make_records()
        records.append({"mpn": "UNKNOWNPART", "source": "PartsBox", "status": "Ready", "stock": None})

        unknown = apply_filters(records, {"stock": "Unknown"})
        out_of_stock = apply_filters(records, {"stock": "Out of Stock"})

        self.assertEqual([r["mpn"] for r in unknown], ["UNKNOWNPART"])
        self.assertEqual([r["mpn"] for r in out_of_stock], ["XYZ789"])
        self.assertNotIn("UNKNOWNPART", [r["mpn"] for r in out_of_stock])


class SearchAndFilterTests(unittest.TestCase):
    def test_search_then_filter_combined(self):
        records = make_records()
        result = search_and_filter(
            records,
            query_text="1",
            search_fields=["mpn", "designators"],
            filters={"source": "PartsBox"},
        )
        self.assertEqual([r["mpn"] for r in result], ["GRM188"])

    def test_no_filters_or_query_returns_all(self):
        records = make_records()
        result = search_and_filter(records)
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
