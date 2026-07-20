"""Mouser Search API client (guide §5).

Refactored from the POC per the Integration Guide:
- API key in the QUERY STRING (never a header).
- Request body wrapped in the named root object; check `Errors[]` FIRST (a 200
  with a non-empty Errors array is a failure).
- `partSearchOptions` uses the real enum (None|Exact), not the POC's "string".
- Batch up to 10 pipe-separated part numbers per call (guide §5.3/§6.4).
- Shared retry/backoff (429/5xx) + the Mouser-specific 403 rate-limit handling.
- Widened normalized schema (guide §6.7); datasheet field is `DataSheetUrl`.
"""

from __future__ import annotations

import os
import time

from services.manufacturer_aliases import manufacturers_equivalent
from services.supplier_base import (
    SupplierResult, append_note, http_request, parse_int, parse_stock,
    raise_for_status, rank_candidates,
)


def _float_env(name, default):
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


class MouserClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_SEARCH_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.search_delay_seconds = _float_env("MOUSER_SEARCH_DELAY_SECONDS", 2.1)
        self.rate_limit_retry_seconds = _float_env("MOUSER_RATE_LIMIT_RETRY_SECONDS", 65.0)
        self.max_rate_limit_retries = _int_env("MOUSER_RATE_LIMIT_RETRIES", 1)
        self._last_search_at = 0.0
        self._search_cache = {}

    # --- transport ---------------------------------------------------------
    def _wait_for_rate_limit_window(self):
        if self.search_delay_seconds <= 0 or self._last_search_at <= 0:
            return
        remaining = self.search_delay_seconds - (time.monotonic() - self._last_search_at)
        if remaining > 0:
            time.sleep(remaining)

    def _post(self, path, payload):
        if not self.api_key:
            raise ValueError("Missing MOUSER_SEARCH_API_KEY in .env")
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_rate_limit_retries + 1):
            self._wait_for_rate_limit_window()
            resp = http_request("POST", url, supplier="mouser",
                                params={"apiKey": self.api_key}, json=payload, timeout=30)
            self._last_search_at = time.monotonic()
            if resp.status_code == 403 and _is_rate_limited(resp):
                if attempt < self.max_rate_limit_retries:
                    time.sleep(self.rate_limit_retry_seconds)
                    continue
            raise_for_status(resp, "Mouser search failed")
            data = resp.json()
            if data.get("Errors"):   # guide §5.5 — check Errors FIRST
                raise RuntimeError(f"Mouser error: {data['Errors']}")
            return data
        raise RuntimeError("Mouser search failed: rate limit exceeded")

    # --- search ------------------------------------------------------------
    def search_by_mpns(self, mpns, exact=False):
        """Batch up to 10 MPNs (pipe-separated) in one call (guide §5.3)."""
        joined = "|".join([str(m).strip() for m in mpns if str(m).strip()][:10])
        if self.dry_run:
            return {"SearchResults": {"Parts": [p for p in (self._mock_part(m) for m in mpns[:10]) if p]}}
        return self._post("/api/v1/search/partnumber", {
            "SearchByPartRequest": {
                "mouserPartNumber": joined,
                "partSearchOptions": "Exact" if exact else "None",
            }
        })

    def search_by_mpn(self, mpn):
        cache_key = str(mpn or "").strip().lower()
        if not self.dry_run and cache_key in self._search_cache:
            return self._search_cache[cache_key]
        data = self.search_by_mpns([mpn])
        if not self.dry_run:
            self._search_cache[cache_key] = data
        return data

    def search_candidates(self, query):
        data = self.search_by_mpn(query)
        parts = (data.get("SearchResults", {}) or {}).get("Parts", []) or []
        notes = ["Multiple supplier candidates found"] if len(parts) > 1 else []
        return [_mouser_part_to_result(p, notes=notes) for p in parts]

    # --- matching (ported behavior) ----------------------------------------
    def find_best_match(self, mpn, manufacturer="", required_qty=None):
        return self.find_exact_match(mpn, manufacturer, required_qty=required_qty) or \
            self.find_best_match_relaxed(mpn, manufacturer, required_qty)

    def find_exact_match(self, mpn, manufacturer="", required_qty=None):
        return rank_candidates(self.search_candidates(mpn), mpn, manufacturer, required_qty, relaxed=False)

    def find_best_match_relaxed(self, mpn, manufacturer="", required_qty=None):
        result = rank_candidates(self.search_candidates(mpn), mpn, manufacturer, required_qty, relaxed=True)
        if result and manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
            result.notes = append_note(result.notes, "Found by relaxed manufacturer alias")
        return result

    def find_best_match_by_supplier_part_number(self, supplier_part_number, required_qty=None):
        result = rank_candidates(self.search_candidates(supplier_part_number), supplier_part_number,
                                 manufacturer="", required_qty=required_qty, relaxed=True,
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
        if result:
            return result
        if supplier == "mouser" and supplier_part_number:
            result = self.find_best_match_by_supplier_part_number(supplier_part_number, required_qty=required_qty)
            if result:
                return result
        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

    def _mock_part(self, mpn):
        stock = {"ABC123": 100, "XYZ789": 50, "RC0603FR-0710KL": 10000}.get(mpn, 0)
        if stock <= 0:
            return None
        return {"Manufacturer": "MOCK", "ManufacturerPartNumber": mpn, "Availability": str(stock),
                "MouserPartNumber": f"MOUSER-{mpn}", "PriceBreaks": [{"Quantity": 1, "Price": "0.01"}]}


def _is_rate_limited(response):
    try:
        errors = response.json().get("Errors", []) or []
    except ValueError:
        return False
    for error in errors:
        code = str(error.get("Code", "")).lower()
        message = str(error.get("Message", "")).lower()
        if "toomanyrequests" in code or "maximum calls per minute" in message:
            return True
    return False


def _mouser_price_breaks(part):
    return [{"quantity": pb.get("Quantity"), "price": str(pb.get("Price", ""))}
            for pb in (part.get("PriceBreaks", []) or [])]


def _mouser_part_to_result(part, notes=None):
    price_breaks = _mouser_price_breaks(part)
    return SupplierResult(
        supplier="Mouser",
        manufacturer=part.get("Manufacturer", ""),
        mpn=part.get("ManufacturerPartNumber", ""),
        stock=parse_stock(part.get("Availability", "")),
        unit_price=(price_breaks[0]["price"] if price_breaks else ""),
        supplier_part_number=part.get("MouserPartNumber", ""),
        product_url=part.get("ProductDetailUrl", ""),
        notes="; ".join(notes or []),
        description=part.get("Description", ""),
        price_breaks=price_breaks,
        lifecycle_status=part.get("LifecycleStatus", ""),
        datasheet_url=part.get("DataSheetUrl", ""),   # casing trap: Mouser = DataSheetUrl
        moq=parse_int(part.get("Min")),
        rohs=part.get("ROHSStatus", ""),
    )
