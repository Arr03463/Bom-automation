"""Mouser Cart API client (guide §5.7) — cart BUILDING only, never checkout.

Refactored from the POC. Two locked constraints:
- DRY-RUN by default (MOUSER_CART_DRY_RUN=true). Live writes are governed by the
  Phase 4 flush pipeline; Phase 2 builds + tests this via mocked HTTP only.
- CPN PASSTHROUGH: the caller hands in an already-generated CPN string (on the
  row's `cpn` field); this writer only places it into `CustomerPartNumber`. It
  never generates, increments, or formats a CPN — that logic is one service, in
  one place, in Phase 4.

There is NO order-submission code here (no /api/v1/order, no SubmitOrder). Cart
insert only. This is the human-approval gate enforced by construction.
"""

from __future__ import annotations

import os

from services.supplier_base import http_request, raise_for_status


class MouserCartClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_CART_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        # Default dry-run TRUE; live writes only when explicitly enabled (Phase 4).
        self.dry_run = os.getenv("MOUSER_CART_DRY_RUN", "true").lower() == "true"

    def validate_config(self):
        if not self.api_key:
            raise ValueError("Missing MOUSER_CART_API_KEY in .env")

    def add_items_to_cart(self, items, cart_key=""):
        """items: [{MouserPartNumber, Quantity, CustomerPartNumber?}]. Passing an
        empty CartKey creates a new cart; the response returns the real key."""
        payload = {"CartKey": cart_key, "CartItems": items}
        if self.dry_run:
            return {"dry_run": True, "items_count": len(items), "cart_key": cart_key, "payload": payload}
        self.validate_config()
        resp = http_request("POST", f"{self.base_url}/api/v1/cart/items/insert", supplier="mouser-cart",
                            params={"apiKey": self.api_key}, json=payload,
                            headers={"Content-Type": "application/json"}, timeout=30)
        raise_for_status(resp, "Mouser cart insert failed")
        return resp.json()


def build_mouser_cart_items(clean_bom):
    """Aggregate Mouser-sourced lines into cart items, carrying a per-line CPN
    (already generated upstream) into CustomerPartNumber. Pure passthrough."""
    aggregated = {}   # (mouser_pn, cpn) -> qty
    for _, row in clean_bom.iterrows():
        if str(row.get("selected_supplier", "")).strip().lower() != "mouser":
            continue
        if str(row.get("sourcing_status", "")).strip().lower() != "sourced_mouser":
            continue
        mouser_pn = str(row.get("supplier_part_number", "")).strip()
        qty = str(row.get("supplier_order_qty", "")).strip()
        cpn = str(row.get("cpn", "")).strip()   # handed-in CPN; NOT generated here
        if not mouser_pn or not qty:
            continue
        try:
            parsed_qty = int(float(qty))
        except ValueError:
            continue
        aggregated[(mouser_pn, cpn)] = aggregated.get((mouser_pn, cpn), 0) + parsed_qty

    items = []
    for (mouser_pn, cpn), quantity in aggregated.items():
        item = {"MouserPartNumber": mouser_pn, "Quantity": quantity}
        if cpn:
            item["CustomerPartNumber"] = cpn[:21]   # guide §5.7 max length; still a passthrough
        items.append(item)
    return items


def create_mouser_cart_from_bom(clean_bom):
    items = build_mouser_cart_items(clean_bom)
    if not items:
        return {"created": False, "message": "No Mouser-sourced parts found for cart upload.", "items_count": 0}
    return {"created": True, "items_count": len(items), "result": MouserCartClient().add_items_to_cart(items)}
