import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from manufacturer_aliases import (
    manufacturers_equivalent,
    normalize_part_number,
    part_numbers_equivalent,
)
from sourcing_engine import SupplierResult, manufacturer_matches, mpn_matches, parse_int


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class MouserClient:
    def __init__(self):
        self.api_key = os.getenv("MOUSER_SEARCH_API_KEY", "").strip()
        self.base_url = os.getenv("MOUSER_BASE_URL", "https://api.mouser.com").strip()
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.search_delay_seconds = _parse_float_env("MOUSER_SEARCH_DELAY_SECONDS", 2.1)
        self.rate_limit_retry_seconds = _parse_float_env("MOUSER_RATE_LIMIT_RETRY_SECONDS", 65.0)
        self.max_rate_limit_retries = _parse_int_env("MOUSER_RATE_LIMIT_RETRIES", 1)
        self._last_search_at = 0.0
        self._search_cache = {}

    def search_by_mpn(self, mpn):
        if self.dry_run:
            return self._mock_search(mpn)

        if not self.api_key:
            raise ValueError("Missing MOUSER_SEARCH_API_KEY in .env")

        cache_key = str(mpn or "").strip().lower()
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

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

        for attempt in range(self.max_rate_limit_retries + 1):
            self._wait_for_rate_limit_window()
            response = requests.post(url, params=params, json=payload, timeout=30)
            self._last_search_at = time.monotonic()

            if response.status_code == 403 and _is_mouser_rate_limit_response(response):
                if attempt < self.max_rate_limit_retries:
                    time.sleep(self.rate_limit_retry_seconds)
                    continue

            _raise_for_status(response, "Mouser part-number search failed")
            result = response.json()
            self._search_cache[cache_key] = result
            return result

        raise RuntimeError("Mouser part-number search failed: rate limit exceeded")

    def _wait_for_rate_limit_window(self):
        if self.search_delay_seconds <= 0 or self._last_search_at <= 0:
            return

        elapsed = time.monotonic() - self._last_search_at
        remaining = self.search_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def search_candidates(self, query):
        data = self.search_by_mpn(query)

        if self.dry_run:
            return [data] if data else []

        parts = data.get("SearchResults", {}).get("Parts", []) or []
        notes = []
        if len(parts) > 1:
            notes.append("Multiple supplier candidates found")

        return [_mouser_part_to_result(part, notes=notes) for part in parts]

    def find_best_match(self, mpn, manufacturer="", required_qty=None):
        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        if result:
            return result

        return self.find_best_match_relaxed(mpn, manufacturer, required_qty)

    def find_exact_match(self, mpn, manufacturer="", required_qty=None):
        candidates = self.search_candidates(mpn)
        return _rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=False)

    def find_best_match_relaxed(self, mpn, manufacturer="", required_qty=None):
        candidates = self.search_candidates(mpn)
        result = _rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=True)
        if result and manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
            result.notes = _append_note(result.notes, "Found by relaxed manufacturer alias")
        return result

    def find_best_match_by_supplier_part_number(self, supplier_part_number, required_qty=None):
        candidates = self.search_candidates(supplier_part_number)
        result = _rank_candidates(
            candidates,
            supplier_part_number,
            manufacturer="",
            required_qty=required_qty,
            relaxed=True,
            match_supplier_part_number=True,
        )
        if result:
            result.notes = _append_note(result.notes, "Found by supplier part number")
        return result

    def find_best_match_for_row(self, row):
        mpn = str(row.get("mpn", "")).strip()
        manufacturer = str(row.get("manufacturer", "")).strip()
        required_qty = parse_int(row.get("required_qty"))

        supplier = str(row.get("supplier", "")).strip().lower()
        supplier_part_number = str(row.get("supplier_part_number", "")).strip()

        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        if result:
            return result

        if supplier == "mouser" and supplier_part_number:
            result = self.find_best_match_by_supplier_part_number(
                supplier_part_number,
                required_qty=required_qty,
            )

            if result:
                return result

        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

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


def _mouser_part_to_result(part, notes=None):
    return SupplierResult(
        supplier="Mouser",
        manufacturer=part.get("Manufacturer", ""),
        mpn=part.get("ManufacturerPartNumber", ""),
        stock=_parse_stock(part.get("Availability", "")),
        unit_price=_first_price(part),
        supplier_part_number=part.get("MouserPartNumber", ""),
        product_url=part.get("ProductDetailUrl", ""),
        notes="; ".join(notes or []),
    )


def _rank_candidates(
    candidates,
    requested_part_number,
    manufacturer="",
    required_qty=None,
    relaxed=False,
    match_supplier_part_number=False,
):
    requested_key = normalize_part_number(requested_part_number)
    required_qty = parse_int(required_qty)
    scored = []

    for candidate in candidates:
        mpn_key = normalize_part_number(candidate.mpn)
        supplier_key = normalize_part_number(candidate.supplier_part_number)
        mpn_matches_candidate = part_numbers_equivalent(requested_part_number, candidate.mpn)
        supplier_matches_candidate = requested_key == supplier_key

        if match_supplier_part_number:
            if not supplier_matches_candidate:
                continue
        elif not mpn_matches_candidate:
            continue

        if manufacturer:
            if relaxed:
                manufacturer_ok = manufacturers_equivalent(manufacturer, candidate.manufacturer)
            else:
                manufacturer_ok = manufacturer_matches(manufacturer, candidate.manufacturer)

            if not manufacturer_ok:
                continue

        enough_stock = required_qty is None or candidate.stock >= required_qty
        score = (
            100 if mpn_matches_candidate else 0,
            90 if supplier_matches_candidate else 0,
            60 if manufacturer and manufacturers_equivalent(manufacturer, candidate.manufacturer) else 0,
            40 if enough_stock else 0,
            20 if _looks_active(candidate) else 0,
            -_price_as_float(candidate.unit_price),
        )
        scored.append((score, candidate))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _looks_active(candidate):
    text = " ".join(
        [
            str(candidate.notes or ""),
            str(candidate.product_url or ""),
        ]
    ).lower()
    return not any(word in text for word in ["obsolete", "discontinued", "nrnd"])


def _price_as_float(value):
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 999999.0


def _append_note(existing, note):
    notes = [item.strip() for item in str(existing or "").split(";") if item.strip()]
    if note not in notes:
        notes.append(note)
    return "; ".join(notes)


def _first_price(part):
    price_breaks = part.get("PriceBreaks", []) or []
    if not price_breaks:
        return ""

    first = price_breaks[0]
    return str(first.get("Price", ""))


def _parse_float_env(name, default):
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _parse_int_env(name, default):
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _is_mouser_rate_limit_response(response):
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


def _raise_for_status(response, context):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()
        if not detail:
            detail = response.reason or "No response body"

        raise RuntimeError(f"{context}: {response.status_code} {detail}") from exc
