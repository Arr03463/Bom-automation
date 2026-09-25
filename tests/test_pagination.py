import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from pagination import clamp_page, paginate, result_signature, total_pages_for


class TotalPagesForTests(unittest.TestCase):
    def test_zero_records_is_one_page(self):
        self.assertEqual(total_pages_for(0), 1)

    def test_exact_multiple_of_page_size(self):
        self.assertEqual(total_pages_for(40, page_size=20), 2)

    def test_one_extra_record_adds_a_page(self):
        self.assertEqual(total_pages_for(41, page_size=20), 3)

    def test_large_catalog(self):
        self.assertEqual(total_pages_for(3450, page_size=20), 173)


class ClampPageTests(unittest.TestCase):
    def test_below_one_clamps_to_one(self):
        self.assertEqual(clamp_page(0, total_pages=5), 1)
        self.assertEqual(clamp_page(-3, total_pages=5), 1)

    def test_above_total_clamps_to_total(self):
        self.assertEqual(clamp_page(99, total_pages=5), 5)

    def test_non_numeric_defaults_to_one(self):
        self.assertEqual(clamp_page("not a number", total_pages=5), 1)
        self.assertEqual(clamp_page(None, total_pages=5), 1)

    def test_in_range_is_unchanged(self):
        self.assertEqual(clamp_page(3, total_pages=5), 3)


class PaginateTests(unittest.TestCase):
    def test_zero_records(self):
        page = paginate([], page=1, page_size=20)
        self.assertEqual(page.items, [])
        self.assertEqual(page.total_items, 0)
        self.assertEqual(page.total_pages, 1)
        self.assertEqual(page.page, 1)

    def test_one_record(self):
        page = paginate([{"mpn": "A"}], page=1, page_size=20)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.total_pages, 1)

    def test_exactly_one_page_size(self):
        records = [{"mpn": str(i)} for i in range(20)]
        page = paginate(records, page=1, page_size=20)
        self.assertEqual(len(page.items), 20)
        self.assertEqual(page.total_pages, 1)

    def test_one_more_than_page_size_creates_second_page(self):
        records = [{"mpn": str(i)} for i in range(21)]
        first = paginate(records, page=1, page_size=20)
        second = paginate(records, page=2, page_size=20)
        self.assertEqual(len(first.items), 20)
        self.assertEqual(len(second.items), 1)
        self.assertEqual(first.total_pages, 2)

    def test_large_catalog_pages_correctly(self):
        records = [{"mpn": str(i)} for i in range(3450)]
        page = paginate(records, page=173, page_size=20)
        self.assertEqual(page.total_pages, 173)
        self.assertEqual(len(page.items), 10)  # 3450 - 172*20 = 10

    def test_out_of_range_page_is_clamped_not_erroring(self):
        records = [{"mpn": str(i)} for i in range(5)]
        page = paginate(records, page=999, page_size=20)
        self.assertEqual(page.page, 1)
        self.assertEqual(len(page.items), 5)

    def test_stable_order_preserved_across_pages(self):
        """
        Records must not shift between pages on repeated calls with the
        same input -- paginate() itself does no sorting/shuffling, so
        identical input always slices identically.
        """
        records = [{"mpn": str(i)} for i in range(50)]
        first_call = paginate(records, page=2, page_size=20).items
        second_call = paginate(records, page=2, page_size=20).items
        self.assertEqual(first_call, second_call)

    def test_all_items_preserved_for_caller_use(self):
        records = [{"mpn": str(i)} for i in range(5)]
        page = paginate(records, page=1, page_size=20)
        self.assertEqual(page.all_items, records)


class ResultSignatureTests(unittest.TestCase):
    def test_same_inputs_produce_same_signature(self):
        sig1 = result_signature("rc0603", frozenset({"partsbox", "mouser"}), {"manufacturer": "Yageo"})
        sig2 = result_signature("rc0603", frozenset({"mouser", "partsbox"}), {"manufacturer": "Yageo"})
        self.assertEqual(sig1, sig2)

    def test_different_query_text_changes_signature(self):
        sig1 = result_signature("rc0603")
        sig2 = result_signature("rc0805")
        self.assertNotEqual(sig1, sig2)

    def test_different_filters_change_signature(self):
        sig1 = result_signature("x", {"manufacturer": "Yageo"})
        sig2 = result_signature("x", {"manufacturer": "Vishay"})
        self.assertNotEqual(sig1, sig2)

    def test_list_and_dict_values_are_hashable(self):
        # Must not raise -- signatures get stored as plain dict/session
        # state values and compared with ==, so every part must reduce
        # to something hashable/comparable.
        sig = result_signature(["a", "b"], {"range": {"min": 1, "max": 2}})
        self.assertIsInstance(hash(sig), int)


if __name__ == "__main__":
    unittest.main()
