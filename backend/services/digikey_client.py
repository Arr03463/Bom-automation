"""DigiKey Product Information V4 client (guide §3, §4).

Refactored from the POC: uses the shared token cache (services.digikey_auth),
the shared retry/backoff HTTP helper, and the widened normalized schema. Keeps
the POC's proven matching/ranking behavior. Sends all required locale headers.
Refreshes the token once on a 401 (guide §3.3).
"""

from __future__ import annotations

import os
from pathlib import Path

from services.digikey_auth import get_auth
from services.manufacturer_aliases import manufacturers_equivalent
from services.supplier_base import (
    SupplierResult, append_note, http_request, parse_int, raise_for_status,
    rank_candidates,
)

# Repo root, for the refresh-token rotation write-back.
REPO_ROOT = Path(__file__).resolve().parents[2]


class DigiKeyClient:
    def __init__(self):
        self.auth = get_auth()
        self.base_url = self.auth.base_url
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.account_id = os.getenv("DIGIKEY_ACCOUNT_ID", "").strip()
        self.refresh_token = os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip()
        self.user_access_token = os.getenv("DIGIKEY_ACCESS_TOKEN", "").strip()

    # --- headers -----------------------------------------------------------
    def product_headers(self, token):
        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "X-DIGIKEY-Locale-Site": os.getenv("DIGIKEY_LOCALE_SITE", "US").strip(),
            "X-DIGIKEY-Locale-Language": os.getenv("DIGIKEY_LOCALE_LANGUAGE", "en").strip(),
            "X-DIGIKEY-Locale-Currency": os.getenv("DIGIKEY_LOCALE_CURRENCY", "USD").strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.account_id:
            headers["X-DIGIKEY-Account-Id"] = self.account_id
        return headers

    def _authed(self, method, url, **kwargs):
        """Product-Info request with a single 401->refresh->retry (guide §3.3)."""
        token = self.auth.token()
        resp = http_request(method, url, supplier="digikey",
                            headers=self.product_headers(token), **kwargs)
        if resp.status_code == 401:
            token = self.auth.token(force_refresh=True)
            resp = http_request(method, url, supplier="digikey",
                                headers=self.product_headers(token), **kwargs)
        return resp

    # --- catalog calls -----------------------------------------------------
    def product_details(self, mpn):
        if self.dry_run:
            return self._mock_details(mpn)
        import urllib.parse
        pn = urllib.parse.quote(str(mpn), safe="")
        resp = self._authed("GET", f"{self.base_url}/products/v4/search/{pn}/productdetails")
        raise_for_status(resp, "DigiKey product details request failed")
        return resp.json()

    def keyword_search(self, keywords):
        if self.dry_run:
            result = self._mock_result(keywords)
            return {"Products": [result] if result else []}
        resp = self._authed("POST", f"{self.base_url}/products/v4/search/keyword",
                            json={"Keywords": keywords, "Limit": 50, "Offset": 0})
        raise_for_status(resp, "DigiKey keyword search request failed")
        return resp.json()

    def search_candidates(self, query, product_details_error=None):
        notes = []
        if product_details_error:
            notes.append("ProductDetails failed; fallback search used")
        if self.dry_run:
            result = self._mock_result(query)
            return [result] if result else []
        products = _extract_products(self.keyword_search(query))
        if len(products) > 1:
            notes.append("Multiple supplier candidates found")
        return [_digikey_product_to_result(p, notes=notes) for p in products]

    # --- matching (ported behavior) ----------------------------------------
    def find_best_match(self, mpn, manufacturer="", required_qty=None):
        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        req = parse_int(required_qty)
        if result and (req is None or result.stock >= req):
            return result
        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

    def find_exact_match(self, mpn, manufacturer="", required_qty=None):
        err = None
        try:
            data = self.product_details(mpn)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = rank_candidates([candidate], mpn, manufacturer, required_qty, relaxed=False)
            if result:
                return result
        except Exception as exc:
            err = exc
        candidates = self.search_candidates(mpn, product_details_error=err)
        return rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=False)

    def find_best_match_relaxed(self, mpn, manufacturer="", required_qty=None):
        req = parse_int(required_qty)
        try:
            data = self.product_details(mpn)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = rank_candidates([candidate], mpn, manufacturer, required_qty, relaxed=True)
            if result and (req is None or result.stock >= req):
                if manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
                    result.notes = append_note(result.notes, "Found by relaxed manufacturer alias")
                return result
        except Exception:
            pass
        candidates = self.search_candidates(mpn)
        result = rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=True)
        if result and manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
            result.notes = append_note(result.notes, "Found by relaxed manufacturer alias")
        return result

    def find_best_match_by_supplier_part_number(self, supplier_part_number, required_qty=None):
        err = None
        try:
            data = self.product_details(supplier_part_number)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = rank_candidates([candidate], supplier_part_number, manufacturer="",
                                     required_qty=required_qty, relaxed=True,
                                     match_supplier_part_number=True)
            if result:
                result.notes = append_note(result.notes, "Found by supplier part number")
                return result
        except Exception as exc:
            err = exc
        candidates = self.search_candidates(supplier_part_number, product_details_error=err)
        result = rank_candidates(candidates, supplier_part_number, manufacturer="",
                                 required_qty=required_qty, relaxed=True,
                                 match_supplier_part_number=True)
        if result:
            result.notes = append_note(result.notes, "Found by supplier part number")
        return result

    def find_best_match_for_row(self, row):
        mpn = str(row.get("mpn", "")).strip()
        manufacturer = str(row.get("manufacturer", "")).strip()
        supplier = str(row.get("supplier", "")).strip().lower()
        supplier_part_number = str(row.get("supplier_part_number", "")).strip()
        required_qty = parse_int(row.get("required_qty"))

        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        if result and (required_qty is None or result.stock >= required_qty):
            return result
        if supplier == "digikey" and supplier_part_number:
            result = self.find_best_match_by_supplier_part_number(supplier_part_number, required_qty=required_qty)
            if result:
                return result
        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

    # --- 3-legged user token (for MyLists) ---------------------------------
    def get_user_access_token(self):
        if self.dry_run:
            return "dry-run-token"
        if self.user_access_token:
            return self.user_access_token
        if not self.refresh_token:
            raise ValueError(
                "DigiKey MyLists requires 3-legged OAuth. Set DIGIKEY_REFRESH_TOKEN "
                "(run backend/scripts/digikey_oauth_setup.py) after authorizing this app."
            )
        from services.digikey_auth import _token_url
        resp = http_request("POST", _token_url(), supplier="digikey-user-auth",
                            data={
                                "client_id": self.client_id,
                                "client_secret": os.getenv("DIGIKEY_CLIENT_SECRET", "").strip(),
                                "refresh_token": self.refresh_token,
                                "grant_type": "refresh_token",
                            },
                            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        raise_for_status(resp, "DigiKey user token request failed")
        data = resp.json()
        token = data.get("access_token")
        new_refresh = data.get("refresh_token", self.refresh_token)
        if new_refresh and new_refresh != self.refresh_token:
            _update_env_value("DIGIKEY_REFRESH_TOKEN", new_refresh)
            self.refresh_token = new_refresh
        if not token:
            raise ValueError("DigiKey did not return a user access token.")
        return token

    # --- dry-run mocks (offline dev) ---------------------------------------
    def _mock_result(self, mpn):
        stock = {"ABC123": 20, "XYZ789": 200, "RC0603FR-0710KL": 5000}.get(mpn, 0)
        if stock <= 0:
            return None
        return SupplierResult(supplier="DigiKey", manufacturer="MOCK", mpn=mpn, stock=stock,
                              unit_price="0.02", supplier_part_number=f"DIGIKEY-{mpn}", notes="mock data")

    def _mock_details(self, mpn):
        r = self._mock_result(mpn)
        return {"Product": {"ManufacturerProductNumber": mpn, "QuantityAvailable": r.stock,
                            "DigiKeyProductNumber": r.supplier_part_number,
                            "Manufacturer": {"Name": "MOCK"}}} if r else {"Product": {}}


# --------------------------------------------------------------------------- #
# Response mapping (widened to guide §6.7)
# --------------------------------------------------------------------------- #
def _extract_products(data):
    if not isinstance(data, dict):
        return []
    for key in ("Products", "products"):
        if isinstance(data.get(key), list):
            return data[key]
    sr = data.get("SearchResults")
    if isinstance(sr, dict):
        products = sr.get("Products") or sr.get("Parts")
        if isinstance(products, list):
            return products
    if isinstance(data.get("Product"), dict):
        return [data["Product"]]
    return []


def _digikey_price_breaks(product):
    breaks = []
    for variation in (product.get("ProductVariations", []) or []):
        for pb in (variation.get("StandardPricing", []) or []):
            breaks.append({"quantity": pb.get("BreakQuantity"), "price": str(pb.get("UnitPrice", ""))})
        if breaks:
            break
    return breaks


def _digikey_product_to_result(product, notes=None):
    manufacturer = product.get("Manufacturer", "")
    if isinstance(manufacturer, dict):
        manufacturer = manufacturer.get("Name", "")

    variations = product.get("ProductVariations", []) or []
    supplier_pn = product.get("DigiKeyProductNumber", "")
    if not supplier_pn and variations:
        supplier_pn = variations[0].get("DigiKeyProductNumber", "")

    try:
        stock = int(product.get("QuantityAvailable", 0) or 0)
    except (TypeError, ValueError):
        stock = 0

    status = product.get("ProductStatus", "")
    if isinstance(status, dict):
        status = status.get("Status", "") or status.get("Name", "")

    description = product.get("Description", "")
    if isinstance(description, dict):
        description = description.get("ProductDescription", "") or description.get("DetailedDescription", "")

    price_breaks = _digikey_price_breaks(product)
    moq = variations[0].get("MinimumOrderQuantity") if variations else None

    result_notes = list(notes or [])
    if status:
        result_notes.append(str(status))

    return SupplierResult(
        supplier="DigiKey",
        manufacturer=manufacturer,
        mpn=product.get("ManufacturerProductNumber", ""),
        stock=stock,
        unit_price=(price_breaks[0]["price"] if price_breaks else ""),
        supplier_part_number=supplier_pn,
        product_url=product.get("ProductUrl", ""),
        notes="; ".join(result_notes),
        description=str(description or ""),
        price_breaks=price_breaks,
        lifecycle_status=str(status or ""),
        datasheet_url=product.get("DatasheetUrl", ""),   # casing trap: DK = DatasheetUrl
        moq=moq,
    )


def _update_env_value(name, value):
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue
        key, _ = line.split("=", 1)
        if key.strip() == name:
            lines[i] = f"{name}={value}"
            env_path.write_text("\n".join(lines) + "\n")
            return
