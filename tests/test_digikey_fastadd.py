import sys
import unittest
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_fastadd import (
    FASTADD_BASE_URL,
    FASTADD_SAFE_LENGTH_CHARS,
    build_digikey_fastadd_url,
)
from purchasing_lines import PurchasingLine


def _line(part="296-ABC123-ND", qty=1, cref="", **overrides):
    return PurchasingLine(
        supplier="digikey",
        supplier_part_number=part,
        quantity=qty,
        customer_reference=cref,
        **overrides,
    )


class BuildDigikeyFastaddUrlTests(unittest.TestCase):
    def test_no_lines_is_not_required(self):
        result = build_digikey_fastadd_url([])
        self.assertEqual(result.status, "not_required")
        self.assertEqual(result.url, "")

    def test_base_url_is_the_confirmed_fastadd_endpoint(self):
        result = build_digikey_fastadd_url([_line()])
        self.assertTrue(result.url.startswith(FASTADD_BASE_URL + "?"))

    def test_sequential_part_qty_cref_fields(self):
        lines = [
            _line(part="296-ABC-ND", qty=5, cref="PRJ-A"),
            _line(part="296-DEF-ND", qty=3, cref="PRJ-B"),
        ]
        result = build_digikey_fastadd_url(lines)
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])

        self.assertEqual(query["part1"], ["296-ABC-ND"])
        self.assertEqual(query["qty1"], ["5"])
        self.assertEqual(query["cref1"], ["PRJ-A"])
        self.assertEqual(query["part2"], ["296-DEF-ND"])
        self.assertEqual(query["qty2"], ["3"])
        self.assertEqual(query["cref2"], ["PRJ-B"])

    def test_cref_omitted_when_customer_reference_is_blank(self):
        result = build_digikey_fastadd_url([_line(cref="")])
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertNotIn("cref1", query)

    def test_never_falls_back_to_mpn(self):
        """PurchasingLine.mpn is descriptive only -- the URL must use
        supplier_part_number exclusively, even when mpn differs."""
        line = _line(part="296-ABC-ND", mpn="DIFFERENT-MPN")
        result = build_digikey_fastadd_url([line])
        self.assertIn("296-ABC-ND", result.url)
        self.assertNotIn("DIFFERENT-MPN", result.url)

    def test_newcart_true_by_default(self):
        result = build_digikey_fastadd_url([_line()])
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertEqual(query["newcart"], ["true"])

    def test_newcart_can_be_set_false(self):
        result = build_digikey_fastadd_url([_line()], new_cart=False)
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertEqual(query["newcart"], ["false"])

    def test_utm_source_always_present(self):
        result = build_digikey_fastadd_url([_line()])
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertIn("utm_source", query)

    def test_utm_content_optional(self):
        without = build_digikey_fastadd_url([_line()])
        query_without = urllib.parse.parse_qs(without.url.split("?", 1)[1])
        self.assertNotIn("utm_content", query_without)

        with_content = build_digikey_fastadd_url([_line()], utm_content="abc123")
        query_with = urllib.parse.parse_qs(with_content.url.split("?", 1)[1])
        self.assertEqual(query_with["utm_content"], ["abc123"])

    def test_encodes_spaces_punctuation_ampersand_plus_slash(self):
        line = _line(part="TEST PART&1+2/3", cref="ref with spaces")
        result = build_digikey_fastadd_url([line])

        # Round-trips correctly through a real query-string parser --
        # the strongest proof the encoding is well-formed, not just that
        # certain substrings are absent.
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertEqual(query["part1"], ["TEST PART&1+2/3"])
        self.assertEqual(query["cref1"], ["ref with spaces"])
        # Space is percent-encoded as %20, not "+" -- so a literal "+" in
        # the input round-trips unambiguously as %2B.
        self.assertIn("%20", result.url)
        self.assertIn("%2B", result.url)

    def test_unicode_is_percent_encoded_as_utf8(self):
        line = _line(cref="café-résumé")
        result = build_digikey_fastadd_url([line])
        query = urllib.parse.parse_qs(result.url.split("?", 1)[1])
        self.assertEqual(query["cref1"], ["café-résumé"])
        self.assertIn("%C3%A9", result.url)  # 'é' as UTF-8

    def test_exact_encoded_length_calculation(self):
        result = build_digikey_fastadd_url([_line(part="296-ABC-ND", qty=1)])
        self.assertEqual(result.encoded_length, len(result.url))

    def test_boundary_just_under_limit_is_current(self):
        # Build lines whose encoded URL lands just under the safe limit.
        lines = []
        # Each line contributes roughly 25-30 encoded characters
        # (part{N}=XXXXXXXXXXXXX-ND&qty{N}=1&). Tuned by binary search
        # below rather than a fixed guess, to stay robust to any future
        # encoding-detail change.
        for count in range(1, 200):
            candidate = [_line(part=f"296-PART{i:04d}-ND", qty=1) for i in range(count)]
            result = build_digikey_fastadd_url(candidate)
            if result.encoded_length > FASTADD_SAFE_LENGTH_CHARS:
                break
            lines = candidate

        result = build_digikey_fastadd_url(lines)
        self.assertLessEqual(result.encoded_length, FASTADD_SAFE_LENGTH_CHARS)
        self.assertEqual(result.status, "current")
        self.assertNotEqual(result.url, "")

    def test_boundary_just_over_limit_is_csv_fallback(self):
        lines = [_line(part=f"296-PART{i:04d}-ND", qty=1) for i in range(1, 200)]
        result = build_digikey_fastadd_url(lines)
        # 199 lines is comfortably over 1700 characters encoded.
        self.assertGreater(result.encoded_length, FASTADD_SAFE_LENGTH_CHARS)
        self.assertEqual(result.status, "csv_fallback")

    def test_oversized_url_is_never_exposed_truncated(self):
        lines = [_line(part=f"296-PART{i:04d}-ND", qty=1) for i in range(1, 200)]
        result = build_digikey_fastadd_url(lines)
        self.assertEqual(result.url, "")
        self.assertIn(str(FASTADD_SAFE_LENGTH_CHARS), result.fallback_reason)

    def test_stable_output_ordering_matches_input_line_order(self):
        lines = [_line(part="296-C-ND"), _line(part="296-A-ND"), _line(part="296-B-ND")]
        result = build_digikey_fastadd_url(lines)
        self.assertLess(result.url.index("296-C-ND"), result.url.index("296-A-ND"))
        self.assertLess(result.url.index("296-A-ND"), result.url.index("296-B-ND"))

    def test_item_count_reflects_line_count_not_aggregate_quantity(self):
        lines = [_line(part="296-A-ND", qty=50), _line(part="296-B-ND", qty=1)]
        result = build_digikey_fastadd_url(lines)
        self.assertEqual(result.item_count, 2)


if __name__ == "__main__":
    unittest.main()
