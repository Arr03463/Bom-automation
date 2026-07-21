"""DigiKey MyLists client (guide §4.1 MyLists) — saved parts list, NOT an order.

Refactored from the POC. Two locked constraints:
- DRY-RUN by default (SUPPLIER_DRY_RUN=true); live writes are Phase 4's flush.
- CPN PASSTHROUGH: a handed-in CPN string is placed into the per-line
  `CustomerReference` field. This writer never generates/increments/formats a
  CPN. No order/checkout call exists (MyLists is not purchasing).
"""

from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import quote

import requests

from services.digikey_client import DigiKeyClient
from services.supplier_base import http_request


class DigiKeyMyListsClient:
    def __init__(self):
        self.base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").strip()
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.account_id = os.getenv("DIGIKEY_ACCOUNT_ID", "").strip()
        self.enabled = os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true"
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.auth_client = DigiKeyClient()

    def validate_config(self):
        if not self.enabled:
            raise ValueError("DIGIKEY_MYLISTS_ENABLED is not true in .env")
        if not self.client_id:
            raise ValueError("Missing DIGIKEY_CLIENT_ID in .env")

    def headers(self, force_refresh=False):
        headers = {
            "Authorization": f"Bearer {self.auth_client.get_user_access_token(force_refresh=force_refresh)}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "Content-Type": "application/json",
        }
        if self.account_id:
            headers["X-DIGIKEY-Account-Id"] = self.account_id
        return headers

    def _request(self, method, url, **kwargs):
        """Send with the cached user token; on a 401 force ONE refresh and retry.

        Guide §3.3's 401 rule applied to the 3-legged path — without this, a
        token that ages out mid-flush fails the whole batch even though the
        refresh token is perfectly good.
        """
        resp = http_request(method, url, supplier="digikey-mylists",
                            headers=self.headers(), timeout=30, **kwargs)
        if resp.status_code == 401:
            from services.digikey_user_auth import get_user_auth
            get_user_auth().invalidate()
            resp = http_request(method, url, supplier="digikey-mylists",
                                headers=self.headers(force_refresh=True), timeout=30, **kwargs)
        return resp

    def is_list_name_available(self, list_name):
        self.validate_config()
        if self.dry_run:
            return True
        resp = self._request("GET", f"{self.base_url}/mylists/v1/lists/validate/{quote(list_name, safe='')}")
        _raise_for_status(resp, "DigiKey MyLists name validation failed")
        result = resp.json()
        return result if isinstance(result, bool) else str(result).strip().lower() == "true"

    def get_valid_list_name(self, list_name):
        self.validate_config()
        if self.dry_run:
            return list_name
        resp = self._request("GET", f"{self.base_url}/mylists/v1/lists/validate/name/{quote(list_name, safe='')}")
        _raise_for_status(resp, "DigiKey MyLists valid-name request failed")
        result = resp.json()
        return result.strip() if isinstance(result, str) and result.strip() else list_name

    def resolve_create_list_name(self, list_name):
        self.validate_config()
        if self.dry_run or self.is_list_name_available(list_name):
            return list_name, False
        return self.get_valid_list_name(build_timestamped_list_name(list_name)), True

    def create_list(self, list_name, description="Created by AutoBOM"):
        self.validate_config()
        payload = {"ListName": list_name, "CreatedBy": description, "Source": "external"}
        if self.dry_run:
            return {"dry_run": True, "ListId": "dry-run-list-id", "ListName": list_name, "payload": payload}
        resp = self._request("POST", f"{self.base_url}/mylists/v1/lists", json=payload)
        _raise_for_status(resp, "DigiKey MyLists create-list request failed")
        return resp.json()

    def add_parts_to_list(self, list_id, parts):
        self.validate_config()
        if self.dry_run:
            return {"dry_run": True, "ListId": list_id, "parts_added": len(parts), "parts": parts}
        resp = self._request("POST", f"{self.base_url}/mylists/v1/lists/{list_id}/parts", json=parts)
        _raise_for_status(resp, "DigiKey MyLists add-parts request failed")
        return resp.json()


def build_timestamped_list_name(list_name):
    return f"{list_name} {datetime.now().strftime('%Y%m%d_%H%M%S')}"


def build_digikey_mylists_parts(clean_bom):
    """DigiKey-sourced lines -> MyLists parts, carrying a per-line CPN (already
    generated upstream) into CustomerReference. Pure passthrough."""
    parts = []
    for _, row in clean_bom.iterrows():
        if str(row.get("selected_supplier", "")).strip().lower() != "digikey":
            continue
        if str(row.get("sourcing_status", "")).strip().lower() != "sourced_digikey":
            continue
        supplier_pn = str(row.get("supplier_part_number", "")).strip()
        mpn = str(row.get("mpn", "")).strip()
        qty = str(row.get("supplier_order_qty", "")).strip()
        part_number = supplier_pn or mpn
        if not part_number or not qty:
            continue
        part = {
            "RequestedPartNumber": part_number,
            "OriginalPartNumber": mpn,
            "ManufacturerName": str(row.get("manufacturer", "")).strip(),
            "SelectedQuantityIndex": 0,
            "Quantities": [{"Quantity": int(float(qty))}],
        }
        cpn = str(row.get("cpn", "")).strip()   # handed-in CPN; NOT generated here
        if cpn:
            part["CustomerReference"] = cpn
        parts.append(part)
    return parts


def create_digikey_mylist_from_bom(clean_bom, list_name):
    client = DigiKeyMyListsClient()
    parts = build_digikey_mylists_parts(clean_bom)
    if not parts:
        return {"created": False, "message": "No DigiKey-sourced parts found.", "parts_count": 0}

    resolved_name, name_changed = client.resolve_create_list_name(list_name)
    create_result = client.create_list(resolved_name)
    list_id = (create_result if isinstance(create_result, str) else
               create_result.get("ListId") or create_result.get("listId")
               or create_result.get("Id") or create_result.get("id"))
    if not list_id:
        return {"created": False, "message": "DigiKey list created but no list ID in response.",
                "requested_list_name": list_name, "list_name": resolved_name,
                "name_changed": name_changed, "parts_count": len(parts), "create_result": create_result}

    add_result = client.add_parts_to_list(list_id, parts)
    return {"created": True, "list_id": list_id, "requested_list_name": list_name, "list_name": resolved_name,
            "name_changed": name_changed, "parts_count": len(parts),
            "create_result": create_result, "add_result": add_result}


def _raise_for_status(response, context):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = (response.text or "").strip()
        try:
            payload = response.json()
            message = payload.get("ErrorMessage") or payload.get("message")
            error_detail = payload.get("ErrorDetails") or payload.get("detail")
            request_id = payload.get("RequestId")
            parts = [p for p in [message, error_detail, f"RequestId: {request_id}" if request_id else ""] if p]
            if parts:
                detail = " | ".join(parts)
        except ValueError:
            pass
        raise RuntimeError(f"{context}: {response.status_code} {detail}") from exc
