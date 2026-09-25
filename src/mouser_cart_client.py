import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from http_error_utils import describe_error_response


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class MouserCartClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_CART_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        self.dry_run = os.getenv("MOUSER_CART_DRY_RUN", "true").lower() == "true"

    def validate_config(self):
        if not self.api_key:
            raise ValueError("Missing MOUSER_CART_API_KEY in .env")

    def add_items_to_cart(self, items, cart_key=""):
        """
        items = [
            {"MouserPartNumber": "...", "Quantity": 10}
        ]
        """
        self.validate_config()

        payload = {
            "CartKey": cart_key,
            "CartItems": items,
        }

        if self.dry_run:
            print("\n[MOUSER CART DRY RUN] Would add items to Mouser cart")
            print("Payload:", payload)
            return {
                "dry_run": True,
                "items_count": len(items),
                "cart_key": cart_key,
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
            # The request URL includes apiKey as a query parameter; never
            # print the raw response body, since some vendor error
            # responses echo request details back.
            print("Mouser Cart response:", describe_error_response(response))

        response.raise_for_status()
        return response.json()


def build_mouser_cart_items(clean_bom):
    # Aggregated by (part number, Customer Reference) rather than part
    # number alone: two BOM rows for the same Mouser part but different
    # Customer References (e.g. one line for a project order, another for
    # inventory restock) must stay separate cart lines, each carrying its
    # own reference -- merging them would silently drop one reference.
    # Confirmed live (2026-09-25, one real disposable cart line) and via
    # Mouser's published Cart API schema: CartItemRequest.CustomerPartNumber
    # is a per-item, optional REQUEST string field -- exactly what Customer
    # Reference maps onto. Sending it round-tripped correctly with zero
    # Errors; Mouser's RESPONSE echoes the same value back under a
    # different field name, CartItemCustPartNumber (not read by this
    # codebase today, since it doesn't parse cart response line items
    # beyond CartKey -- noted here in case that changes).
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

        customer_reference = str(row.get("customer_reference", "") or "").strip()
        key = (mouser_part_number, customer_reference)
        item_quantities[key] = item_quantities.get(key, 0) + parsed_qty

    items = []
    for (mouser_part_number, customer_reference), quantity in item_quantities.items():
        item = {
            "MouserPartNumber": mouser_part_number,
            "Quantity": quantity,
        }
        if customer_reference:
            item["CustomerPartNumber"] = customer_reference
        items.append(item)

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
