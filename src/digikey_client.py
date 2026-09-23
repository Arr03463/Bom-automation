import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from http_error_utils import raise_for_status as _raise_for_status
from manufacturer_aliases import (
    manufacturers_equivalent,
    normalize_part_number,
    part_numbers_equivalent,
)
from sourcing_engine import SupplierResult, manufacturer_matches, mpn_matches
from token_store import TokenStoreError, build_token_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

REFRESH_TOKEN_STORE_KEY = "DIGIKEY_REFRESH_TOKEN"


class DigiKeyClient:
    def __init__(self, token_store=None):
        load_dotenv(PROJECT_ROOT / ".env", override=True)

        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
        self.base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").strip()
        self.token_url = os.getenv("DIGIKEY_TOKEN_URL", "https://api.digikey.com/v1/oauth2/token").strip()
        self.dry_run = os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true"
        self.access_token = None
        self.user_access_token = os.getenv("DIGIKEY_ACCESS_TOKEN", "").strip()
        self.account_id = os.getenv("DIGIKEY_ACCOUNT_ID", "").strip()

        self.token_store = token_store or build_token_store()
        # Surfaced (not swallowed) when a durable backend can't be reached --
        # see _current_refresh_token() and Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md.
        # Configuration validation (config_validation.py) also reads this
        # indirectly via digikey_status() to warn operators before a
        # request fails.
        self.token_store_error = None
        self.refresh_token = self._load_refresh_token()

    def _load_refresh_token(self):
        # A previously rotated token in the store takes precedence over the
        # static .env/secrets value, so continuity survives across
        # DigiKeyClient() instances within the same process even when the
        # backend can't rewrite .env (see token_store.py for the
        # per-backend persistence guarantees, or lack thereof).
        env_value = os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip()
        try:
            stored_value = self.token_store.get(REFRESH_TOKEN_STORE_KEY)
        except TokenStoreError as exc:
            # Fall back to the static value rather than raising out of
            # __init__ -- many callers construct a DigiKeyClient() only to
            # do a dry-run product lookup that never touches the refresh
            # token at all. Record the failure so anything that DOES need
            # a live user token surfaces it clearly instead of a bare
            # "missing refresh token" error that looks like a config typo.
            self.token_store_error = str(exc)
            stored_value = None

        return (stored_value or env_value or "").strip()

    def _current_refresh_token(self):
        """
        Re-reads the store immediately before a refresh attempt (see
        get_user_access_token()), rather than trusting the value loaded at
        construction time -- a concurrent process holding the same
        durable backend may have already rotated the token since this
        client was built.
        """
        try:
            stored_value = self.token_store.get(REFRESH_TOKEN_STORE_KEY)
        except TokenStoreError as exc:
            self.token_store_error = str(exc)
            stored_value = None

        return (stored_value or self.refresh_token or "").strip()

    def get_access_token(self):
        if self.dry_run:
            return "dry-run-token"

        if not self.client_id or not self.client_secret:
            raise ValueError("Missing DigiKey credentials in .env")

        response = requests.post(
            self.token_url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        _raise_for_status(response, "DigiKey access token request failed")
        self.access_token = response.json().get("access_token")

        if not self.access_token:
            raise ValueError("DigiKey did not return an access token.")

        return self.access_token

    def get_user_access_token(self):
        if self.dry_run:
            return "dry-run-token"

        if self.user_access_token:
            return self.user_access_token

        if not self.client_id or not self.client_secret:
            raise ValueError("Missing DigiKey credentials in .env")

        # Locked for the full read-refresh-write cycle: for the file/
        # env-file backends (the only ones where two AutoBOM processes
        # can share the same persistent store), this serializes concurrent
        # refreshes so the second caller re-reads the FIRST caller's
        # already-rotated token instead of retrying the one DigiKey just
        # invalidated. See token_store.TokenStore.lock() and
        # Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md for what
        # backs this on backends with no real lock (memory, http).
        with self.token_store.lock():
            current_refresh_token = self._current_refresh_token()
            if not current_refresh_token:
                raise ValueError(
                    "DigiKey MyLists requires 3-legged OAuth. Set DIGIKEY_REFRESH_TOKEN "
                    "or DIGIKEY_ACCESS_TOKEN in .env after authorizing this app with your "
                    "My DigiKey account."
                )

            response = requests.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": current_refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            _raise_for_status(response, "DigiKey user token request failed")

            token_data = response.json()
            self.access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", current_refresh_token)
            # Update in-memory state before attempting to persist: DigiKey
            # has already invalidated current_refresh_token by returning a
            # new one, so this process must use the new value for any
            # further refresh even if durable persistence below fails.
            self.refresh_token = new_refresh_token
            if new_refresh_token != current_refresh_token:
                try:
                    self.token_store.set(REFRESH_TOKEN_STORE_KEY, new_refresh_token)
                except TokenStoreError as exc:
                    self.token_store_error = str(exc)

        if not self.access_token:
            raise ValueError("DigiKey did not return a user access token.")

        return self.access_token

    def product_details(self, mpn):
        if self.dry_run:
            return self._mock_search(mpn)

        token = self.access_token or self.get_access_token()

        # NOTE:
        # DigiKey Product Information endpoint/payload may need adjustment based on
        # your developer app/product version.
        url = f"{self.base_url}/products/v4/search/{mpn}/productdetails"

        headers = self.product_headers(token)

        response = requests.get(url, headers=headers, timeout=30)
        _raise_for_status(response, "DigiKey product details request failed")
        return response.json()

    def keyword_search(self, keywords):
        if self.dry_run:
            result = self._mock_search(keywords)
            return {"Products": [result] if result else []}

        token = self.access_token or self.get_access_token()
        url = f"{self.base_url}/products/v4/search/keyword"
        payload = {
            "Keywords": keywords,
            "RecordCount": 50,
            "RecordStartPosition": 0,
        }

        response = requests.post(
            url,
            headers=self.product_headers(token),
            json=payload,
            timeout=30,
        )
        _raise_for_status(response, "DigiKey keyword search request failed")
        return response.json()

    def product_headers(self, token):
        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "X-DIGIKEY-Locale-Language": os.getenv("DIGIKEY_LOCALE_LANGUAGE", "en").strip(),
            "X-DIGIKEY-Locale-Currency": os.getenv("DIGIKEY_LOCALE_CURRENCY", "USD").strip(),
            "X-DIGIKEY-Locale-Site": os.getenv("DIGIKEY_LOCALE_SITE", "US").strip(),
            "Content-Type": "application/json",
        }

        if self.account_id:
            headers["X-DIGIKEY-Account-Id"] = self.account_id

        return headers

    def search_candidates(self, query, product_details_error=None):
        notes = []
        if product_details_error:
            notes.append("ProductDetails failed; fallback search used")

        if self.dry_run:
            result = self._mock_search(query)
            return [result] if result else []

        data = self.keyword_search(query)
        products = _extract_products(data)
        if len(products) > 1:
            notes.append("Multiple supplier candidates found")

        return [_digikey_product_to_result(product, notes=notes) for product in products]

    def find_best_match(self, mpn, manufacturer="", required_qty=None):
        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        parsed_required_qty = _parse_int(required_qty)
        if result and (parsed_required_qty is None or result.stock >= parsed_required_qty):
            return result

        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

    def find_exact_match(self, mpn, manufacturer="", required_qty=None):
        product_details_error = None
        try:
            data = self.product_details(mpn)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = _rank_candidates([candidate], mpn, manufacturer, required_qty, relaxed=False)
            if result:
                return result
        except Exception as exc:
            product_details_error = exc

        candidates = self.search_candidates(mpn, product_details_error=product_details_error)
        return _rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=False)

    def find_best_match_relaxed(self, mpn, manufacturer="", required_qty=None):
        parsed_required_qty = _parse_int(required_qty)
        try:
            data = self.product_details(mpn)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = _rank_candidates([candidate], mpn, manufacturer, required_qty, relaxed=True)
            if result and (parsed_required_qty is None or result.stock >= parsed_required_qty):
                if manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
                    result.notes = _append_note(result.notes, "Found by relaxed manufacturer alias")
                return result
        except Exception:
            pass

        candidates = self.search_candidates(mpn)
        result = _rank_candidates(candidates, mpn, manufacturer, required_qty, relaxed=True)
        if result and manufacturer and manufacturers_equivalent(manufacturer, result.manufacturer):
            result.notes = _append_note(result.notes, "Found by relaxed manufacturer alias")
        return result

    def find_best_match_by_supplier_part_number(self, supplier_part_number, required_qty=None):
        product_details_error = None
        try:
            data = self.product_details(supplier_part_number)
            candidate = _digikey_product_to_result(data.get("Product", data))
            result = _rank_candidates(
                [candidate],
                supplier_part_number,
                manufacturer="",
                required_qty=required_qty,
                relaxed=True,
                match_supplier_part_number=True,
            )
            if result:
                result.notes = _append_note(result.notes, "Found by supplier part number")
                return result
        except Exception as exc:
            product_details_error = exc

        candidates = self.search_candidates(
            supplier_part_number,
            product_details_error=product_details_error,
        )
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
        supplier = str(row.get("supplier", "")).strip().lower()
        supplier_part_number = str(row.get("supplier_part_number", "")).strip()
        required_qty = _parse_int(row.get("required_qty"))

        result = self.find_exact_match(mpn, manufacturer, required_qty=required_qty)
        if result and (required_qty is None or result.stock >= required_qty):
            return result

        if supplier == "digikey" and supplier_part_number:
            result = self.find_best_match_by_supplier_part_number(
                supplier_part_number,
                required_qty=required_qty,
            )
            if result:
                return result

        return self.find_best_match_relaxed(mpn, manufacturer, required_qty=required_qty)

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


def _extract_products(data):
    if not isinstance(data, dict):
        return []

    for key in ("Products", "products"):
        products = data.get(key)
        if isinstance(products, list):
            return products

    search_results = data.get("SearchResults")
    if isinstance(search_results, dict):
        products = search_results.get("Products") or search_results.get("Parts")
        if isinstance(products, list):
            return products

    product = data.get("Product")
    if isinstance(product, dict):
        return [product]

    return []


def _digikey_product_to_result(product, notes=None):
    manufacturer = product.get("Manufacturer", "")
    if isinstance(manufacturer, dict):
        manufacturer = manufacturer.get("Name", "")

    supplier_part_number = product.get("DigiKeyProductNumber", "")
    variations = product.get("ProductVariations", []) or []
    if not supplier_part_number and variations:
        supplier_part_number = variations[0].get("DigiKeyProductNumber", "")

    stock = product.get("QuantityAvailable", 0) or 0
    try:
        stock = int(stock)
    except (TypeError, ValueError):
        stock = 0

    status = product.get("ProductStatus", "")
    if isinstance(status, dict):
        status = status.get("Status", "") or status.get("Name", "")

    result_notes = list(notes or [])
    if status:
        result_notes.append(str(status))

    # Best-effort only: DigiKey's live "Category" field shape is not
    # confirmed against this codebase's own tests/mocks -- extracted
    # defensively the same way Manufacturer/ProductStatus are (nested
    # {"Name": ...} or a plain string), left "" otherwise.
    category = product.get("Category", "")
    if isinstance(category, dict):
        category = category.get("Name", "") or category.get("Value", "")
    if not isinstance(category, str):
        category = ""

    return SupplierResult(
        supplier="DigiKey",
        manufacturer=manufacturer,
        mpn=product.get("ManufacturerProductNumber", ""),
        stock=stock,
        unit_price=_first_unit_price(product),
        supplier_part_number=supplier_part_number,
        product_url=product.get("ProductUrl", ""),
        notes="; ".join(result_notes),
        category=category,
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
    required_qty = _parse_int(required_qty)
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
    text = str(candidate.notes or "").lower()
    return not any(word in text for word in ["obsolete", "discontinued", "nrnd"])


def _price_as_float(value):
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 999999.0


def _parse_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def _append_note(existing, note):
    notes = [item.strip() for item in str(existing or "").split(";") if item.strip()]
    if note not in notes:
        notes.append(note)
    return "; ".join(notes)


