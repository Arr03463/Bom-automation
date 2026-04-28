import os
import requests
from dotenv import load_dotenv

from sourcing_engine import SupplierResult, manufacturer_matches, mpn_matches

load_dotenv()


class DigiKeyClient:
    def __init__(self):
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
        self.base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").strip()
        self.token_url = os.getenv("DIGIKEY_TOKEN_URL", "https://api.digikey.com/v1/oauth2/token").strip()
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.access_token = None

    def get_access_token(self):
        if self.dry_run:
            return "dry-run-token"

        if not self.client_id or not self.client_secret:
            raise ValueError("Missing DigiKey credentials in .env")

        response = requests.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        response.raise_for_status()
        self.access_token = response.json().get("access_token")

        if not self.access_token:
            raise ValueError("DigiKey did not return an access token.")

        return self.access_token

    def product_details(self, mpn):
        if self.dry_run:
            return self._mock_search(mpn)

        token = self.access_token or self.get_access_token()

        # NOTE:
        # DigiKey Product Information endpoint/payload may need adjustment based on
        # your developer app/product version.
        url = f"{self.base_url}/products/v4/search/{mpn}/productdetails"

        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def find_best_match(self, mpn, manufacturer=""):
        data = self.product_details(mpn)

        if self.dry_run:
            return data

        product = data.get("Product", data)
        found_mpn = product.get("ManufacturerProductNumber", "")
        found_mfr = (
            product.get("Manufacturer", {}).get("Name", "")
            if isinstance(product.get("Manufacturer"), dict)
            else product.get("Manufacturer", "")
        )
        stock = product.get("QuantityAvailable", 0) or 0

        if mpn_matches(mpn, found_mpn) and manufacturer_matches(manufacturer, found_mfr):
            return SupplierResult(
                supplier="DigiKey",
                manufacturer=found_mfr,
                mpn=found_mpn,
                stock=int(stock),
                unit_price=_first_unit_price(product),
                supplier_part_number=product.get("DigiKeyProductNumber", ""),
                product_url=product.get("ProductUrl", ""),
            )

        return None

    def _mock_search(self, mpn):
        fake_stock = {
            "ABC123": 20,
            "XYZ789": 200,
            "RC0603FR-0710KL": 5000,
        }

        stock = fake_stock.get(mpn, 0)
        if stock <= 0:
            return None

        return SupplierResult(
            supplier="DigiKey",
            manufacturer="MOCK",
            mpn=mpn,
            stock=stock,
            unit_price="0.02",
            supplier_part_number=f"DIGIKEY-{mpn}",
            product_url="",
            notes="mock data",
        )


def _first_unit_price(product):
    variations = product.get("ProductVariations", []) or []
    for variation in variations:
        pricing = variation.get("StandardPricing", []) or []
        if pricing:
            return str(pricing[0].get("UnitPrice", ""))

    return ""