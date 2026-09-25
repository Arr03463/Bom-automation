import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from record_filter import apply_filters, generate_facets, search_and_filter, text_search


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

    def test_range_filter_bounds_a_numeric_field(self):
        records = [
            {"mpn": "A", "voltage": "16V"},
            {"mpn": "B", "voltage": "25V"},
            {"mpn": "C", "voltage": "50V"},
        ]
        result = apply_filters(records, {"voltage": {"min": 20, "max": 30}})
        self.assertEqual([r["mpn"] for r in result], ["B"])

    def test_range_filter_unbounded_side(self):
        records = [
            {"mpn": "A", "voltage": "16V"},
            {"mpn": "B", "voltage": "25V"},
            {"mpn": "C", "voltage": "50V"},
        ]
        result = apply_filters(records, {"voltage": {"min": 20}})
        self.assertEqual({r["mpn"] for r in result}, {"B", "C"})

    def test_range_filter_excludes_unparseable_values(self):
        records = [
            {"mpn": "A", "voltage": "25V"},
            {"mpn": "B", "voltage": "unknown"},
            {"mpn": "C", "voltage": ""},
        ]
        result = apply_filters(records, {"voltage": {"min": 0, "max": 100}})
        self.assertEqual([r["mpn"] for r in result], ["A"])

    def test_range_and_categorical_filters_combine(self):
        records = [
            {"mpn": "A", "source": "Mouser", "voltage": "25V"},
            {"mpn": "B", "source": "DigiKey", "voltage": "25V"},
        ]
        result = apply_filters(records, {"source": "Mouser", "voltage": {"min": 20, "max": 30}})
        self.assertEqual([r["mpn"] for r in result], ["A"])


class GenerateFacetsTests(unittest.TestCase):
    def test_only_fields_with_real_data_are_returned(self):
        records = [
            {"mpn": "A", "package": "0603", "dielectric": ""},
            {"mpn": "B", "package": "0805", "dielectric": ""},
        ]
        facets = generate_facets(records, ["package", "dielectric", "mounting"])

        self.assertEqual(facets, {"package": ["0603", "0805"]})
        self.assertNotIn("dielectric", facets)
        self.assertNotIn("mounting", facets)

    def test_values_are_sorted_and_deduplicated(self):
        records = [
            {"mpn": "A", "manufacturer": "Yageo"},
            {"mpn": "B", "manufacturer": "Murata"},
            {"mpn": "C", "manufacturer": "Yageo"},
        ]
        facets = generate_facets(records, ["manufacturer"])

        self.assertEqual(facets["manufacturer"], ["Murata", "Yageo"])

    def test_empty_records_produce_no_facets(self):
        self.assertEqual(generate_facets([], ["package", "manufacturer"]), {})


class MembershipFilterTests(unittest.TestCase):
    """
    Multiselect membership filters (Storage Space / Location / Project)
    -- a list/set/tuple desired value matches either a scalar record
    field that's IN the desired collection, or (for a PartsBox-enriched
    part that can be in several locations/projects at once) a
    list-valued record field that intersects the desired collection.
    """

    def test_list_desired_matches_scalar_field_membership(self):
        records = [{"mpn": "A", "storage_space": "Development"}, {"mpn": "B", "storage_space": "Project"}]
        result = apply_filters(records, {"storage_space": ["Development", "Mechanical"]})
        self.assertEqual([r["mpn"] for r in result], ["A"])

    def test_list_desired_matches_list_valued_field_intersection(self):
        records = [
            {"mpn": "A", "location": ["C1 - Resistors", "DAB Prototype"]},
            {"mpn": "B", "location": ["C2 - Capacitors"]},
        ]
        result = apply_filters(records, {"location": ["DAB Prototype"]})
        self.assertEqual([r["mpn"] for r in result], ["A"])

    def test_empty_desired_list_is_treated_as_no_filter(self):
        records = make_records()
        result = apply_filters(records, {"source": []})
        self.assertEqual(len(result), 3)

    def test_membership_is_case_insensitive(self):
        records = [{"mpn": "A", "project": ["dab prototype"]}]
        result = apply_filters(records, {"project": ["DAB Prototype"]})
        self.assertEqual([r["mpn"] for r in result], ["A"])

    def test_no_intersection_excludes_record(self):
        records = [{"mpn": "A", "location": ["C1 - Resistors"]}]
        result = apply_filters(records, {"location": ["A12"]})
        self.assertEqual(result, [])


class GenerateFacetsListValuedFieldTests(unittest.TestCase):
    def test_list_valued_field_contributes_each_entry(self):
        records = [
            {"mpn": "A", "location": ["C1 - Resistors", "DAB Prototype"]},
            {"mpn": "B", "location": ["C2 - Capacitors"]},
        ]
        facets = generate_facets(records, ["location"])
        self.assertEqual(facets["location"], ["C1 - Resistors", "C2 - Capacitors", "DAB Prototype"])

    def test_empty_lists_contribute_nothing(self):
        records = [{"mpn": "A", "location": []}]
        facets = generate_facets(records, ["location"])
        self.assertEqual(facets, {})

    def test_mixed_scalar_and_list_fields_both_work(self):
        records = [
            {"mpn": "A", "manufacturer": "Yageo", "location": ["C1 - Resistors"]},
            {"mpn": "B", "manufacturer": "Murata", "location": ["C2 - Capacitors", "C1 - Resistors"]},
        ]
        facets = generate_facets(records, ["manufacturer", "location"])
        self.assertEqual(facets["manufacturer"], ["Murata", "Yageo"])
        self.assertEqual(facets["location"], ["C1 - Resistors", "C2 - Capacitors"])


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
