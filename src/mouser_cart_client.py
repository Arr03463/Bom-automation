import os
import requests
from dotenv import load_dotenv

load_dotenv()


class MouserCartClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_CART_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        self.dry_run = os.getenv("MOUSER_CART_DRY_RUN", "true").lower() == "true"

    def validate_config(self):
        if not self.api_key:
            raise ValueError("Missing MOUSER_CART_API_KEY in .env")

    def add_items_to_cart(self, items):
        """
        items = [
            {"MouserPartNumber": "...", "Quantity": 10}
        ]
        """
        self.validate_config()

        payload = {
            "CartItems": items,
        }

        if self.dry_run:
            print("\n[MOUSER CART DRY RUN] Would add items to Mouser cart")
            print("Payload:", payload)
            return {
                "dry_run": True,
                "items_count": len(items),
                "payload": payload,
            }

        url = f"{self.base_url}/api/v1/cart/items/insert"
        params = {"apiKey": self.api_key}

        response = requests.post(
            url,
            params=params,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code >= 400:
            print("Mouser Cart response:", response.text)

        response.raise_for_status()
        return response.json()


def build_mouser_cart_items(clean_bom):
    item_quantities = {}

    for _, row in clean_bom.iterrows():
        selected_supplier = str(row.get("selected_supplier", "")).strip().lower()
        sourcing_status = str(row.get("sourcing_status", "")).strip().lower()

        if selected_supplier != "mouser" or sourcing_status != "sourced_mouser":
            continue

        mouser_part_number = str(row.get("supplier_part_number", "")).strip()
        qty = str(row.get("supplier_order_qty", "")).strip()

        if not mouser_part_number or not qty:
            continue

        try:
            parsed_qty = int(float(qty))
        except ValueError:
            continue

        item_quantities[mouser_part_number] = (
            item_quantities.get(mouser_part_number, 0) + parsed_qty
        )

    items = []
    for mouser_part_number, quantity in item_quantities.items():
        items.append(
            {
                "MouserPartNumber": mouser_part_number,
                "Quantity": quantity,
            }
        )

    return items


def create_mouser_cart_from_bom(clean_bom):
    client = MouserCartClient()
    items = build_mouser_cart_items(clean_bom)

    if not items:
        return {
            "created": False,
            "message": "No Mouser-sourced parts found for cart upload.",
            "items_count": 0,
        }

    result = client.add_items_to_cart(items)

    return {
        "created": True,
        "items_count": len(items),
        "result": result,
    }
