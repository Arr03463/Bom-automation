import os
import requests
from dotenv import load_dotenv

from sourcing_engine import SupplierResult, manufacturer_matches, mpn_matches

load_dotenv()


class MouserClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_SEARCH_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"

    def search_by_mpn(self, mpn):
        if self.dry_run:
            return self._mock_search(mpn)

        if not self.api_key:
            raise ValueError("Missing MOUSER_SEARCH_API_KEY in .env")

        # NOTE:
        # Mouser Search API endpoint/payload may need adjustment based on
        # your company API account/docs.
        url = f"{self.base_url}/api/v1/search/partnumber"
        params = {"apiKey": self.api_key}
        payload = {
            "SearchByPartRequest": {
                "mouserPartNumber": mpn,
                "partSearchOptions": "string",
            }
        }

        response = requests.post(url, params=params, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def find_best_match(self, mpn, manufacturer=""):
        data = self.search_by_mpn(mpn)

        if self.dry_run:
            return data

        parts = (
            data.get("SearchResults", {})
            .get("Parts", [])
        )

        for part in parts:
            found_mpn = part.get("ManufacturerPartNumber", "")
            found_mfr = part.get("Manufacturer", "")
            stock = _parse_stock(part.get("Availability", ""))

            if mpn_matches(mpn, found_mpn) and manufacturer_matches(manufacturer, found_mfr):
                return SupplierResult(
                    supplier="Mouser",
                    manufacturer=found_mfr,
                    mpn=found_mpn,
                    stock=stock,
                    unit_price=_first_price(part),
                    supplier_part_number=part.get("MouserPartNumber", ""),
                    product_url=part.get("ProductDetailUrl", ""),
                )

        return None

    def _mock_search(self, mpn):
        fake_stock = {
            "ABC123": 100,
            "XYZ789": 50,
            "RC0603FR-0710KL": 10000,
        }

        stock = fake_stock.get(mpn, 0)
        if stock <= 0:
            return None

        return SupplierResult(
            supplier="Mouser",
            manufacturer="MOCK",
            mpn=mpn,
            stock=stock,
            unit_price="0.01",
            supplier_part_number=f"MOUSER-{mpn}",
            product_url="",
            notes="mock data",
        )


def _parse_stock(value):
    text = str(value or "").replace(",", "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def _first_price(part):
    price_breaks = part.get("PriceBreaks", []) or []
    if not price_breaks:
        return ""

    first = price_breaks[0]
    return str(first.get("Price", ""))