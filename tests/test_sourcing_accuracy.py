import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_client import DigiKeyClient
from mouser_client import MouserClient


class FakeMouserClient(MouserClient):
    def __init__(self, responses):
        super().__init__()
        self.dry_run = False
        self.search_delay_seconds = 0
        self.responses = responses
        self.calls = []

    def search_by_mpn(self, mpn):
        self.calls.append(mpn)
        return {
            "SearchResults": {
                "Parts": self.responses.get(mpn, []),
            }
        }


class FakeDigiKeyClient(DigiKeyClient):
    def __init__(self, product_details=None, keyword_results=None, product_details_errors=None):
        super().__init__()
        self.dry_run = False
        self.product_details_map = product_details or {}
        self.keyword_results = keyword_results or {}
        self.product_details_errors = product_details_errors or set()
        self.calls = []

    def product_details(self, mpn):
        self.calls.append(("product_details", mpn))
        if mpn in self.product_details_errors:
            raise RuntimeError("duplicate products")
        return {"Product": self.product_details_map[mpn]}

    def keyword_search(self, keywords):
        self.calls.append(("keyword_search", keywords))
        return {"Products": self.keyword_results.get(keywords, [])}


def mouser_part(mpn, manufacturer, stock, supplier_part_number, price="0.10"):
    return {
        "ManufacturerPartNumber": mpn,
        "Manufacturer": manufacturer,
        "Availability": str(stock),
        "MouserPartNumber": supplier_part_number,
        "PriceBreaks": [{"Price": price}],
        "ProductDetailUrl": "https://example.test/mouser",
    }


def digikey_product(mpn, manufacturer, stock, supplier_part_number, price="0.10", status="Active"):
    return {
        "ManufacturerProductNumber": mpn,
        "Manufacturer": {"Name": manufacturer},
        "QuantityAvailable": stock,
        "DigiKeyProductNumber": supplier_part_number,
        "ProductVariations": [
            {
                "DigiKeyProductNumber": supplier_part_number,
                "StandardPricing": [{"UnitPrice": price}],
            }
        ],
        "ProductStatus": {"Status": status},
        "ProductUrl": "https://example.test/digikey",
    }


class SourcingAccuracyTests(unittest.TestCase):
    def test_mouser_exact_match(self):
        client = FakeMouserClient(
            {
                "ABC123": [
                    mouser_part("ABC123", "Yageo", 500, "603-ABC123"),
                ]
            }
        )

        result = client.find_best_match("ABC123", "Yageo", required_qty=20)

        self.assertIsNotNone(result)
        self.assertEqual(result.supplier, "Mouser")
        self.assertEqual(result.supplier_part_number, "603-ABC123")

    def test_mouser_supplier_part_number_fallback(self):
        client = FakeMouserClient(
            {
                "ABC123": [],
                "603-ABC123": [
                    mouser_part("ABC123", "Yageo", 500, "603-ABC123"),
                ],
            }
        )
        row = {
            "mpn": "ABC123",
            "manufacturer": "Yageo",
            "supplier": "Mouser",
            "supplier_part_number": "603-ABC123",
            "required_qty": "20",
        }

        result = client.find_best_match_for_row(row)

        self.assertIsNotNone(result)
        self.assertIn("Found by supplier part number", result.notes)

    def test_mouser_relaxed_manufacturer_alias(self):
        client = FakeMouserClient(
            {
                "ABC123": [
                    mouser_part("ABC123", "Texas Instruments", 500, "595-ABC123"),
                ]
            }
        )
        row = {
            "mpn": "ABC123",
            "manufacturer": "TI",
            "required_qty": "20",
        }

        result = client.find_best_match_for_row(row)

        self.assertIsNotNone(result)
        self.assertIn("Found by relaxed manufacturer alias", result.notes)

    def test_mouser_duplicate_candidate_ranking_prefers_stock_then_price(self):
        client = FakeMouserClient(
            {
                "ABC123": [
                    mouser_part("ABC123", "Yageo", 5, "603-LOW", price="0.01"),
                    mouser_part("ABC123", "Yageo", 500, "603-HIGH", price="0.03"),
                ]
            }
        )

        result = client.find_best_match("ABC123", "Yageo", required_qty=20)

        self.assertIsNotNone(result)
        self.assertEqual(result.supplier_part_number, "603-HIGH")
        self.assertIn("Multiple supplier candidates found", result.notes)

    def test_digikey_productdetails_failure_falls_back_to_keyword_search(self):
        client = FakeDigiKeyClient(
            product_details_errors={"ABC123"},
            keyword_results={
                "ABC123": [
                    digikey_product("ABC123", "Texas Instruments", 500, "296-ABC123-ND"),
                ]
            },
        )

        result = client.find_best_match("ABC123", "Texas Instruments", required_qty=20)

        self.assertIsNotNone(result)
        self.assertEqual(result.supplier_part_number, "296-ABC123-ND")
        self.assertIn("ProductDetails failed; fallback search used", result.notes)
        self.assertIn(("keyword_search", "ABC123"), client.calls)


if __name__ == "__main__":
    unittest.main()
