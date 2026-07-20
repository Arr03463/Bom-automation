"""Shared supplier foundation for the Mouser + DigiKey clients.

Owns the ONE normalized part schema (guide §6.7), the shared candidate ranking /
matching helpers (deduped from the POC's per-client copies), and the retry/
backoff + traceability HTTP helper (guide §6.2, §6.6).

No supplier-specific request shaping lives here — each client maps its raw
response into `SupplierResult`, then calls `rank_candidates`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from services.manufacturer_aliases import (
    manufacturers_equivalent,
    normalize_part_number,
    part_numbers_equivalent,
)

log = logging.getLogger("autobom.suppliers")


# --------------------------------------------------------------------------- #
# Normalized part schema (guide §6.7) — widened from the POC's 8-field version.
# All new fields default so cached (older, narrower) entries still deserialize.
# --------------------------------------------------------------------------- #
@dataclass
class SupplierResult:
    supplier: str
    manufacturer: str
    mpn: str
    stock: int
    unit_price: str = ""
    supplier_part_number: str = ""
    product_url: str = ""
    notes: str = ""
    # --- guide §6.7 additions ---
    description: str = ""
    price_breaks: list = field(default_factory=list)   # [{"quantity": int, "price": str}]
    lifecycle_status: str = ""
    datasheet_url: str = ""                              # DatasheetUrl (DK) vs DataSheetUrl (Mouser)
    moq: Optional[int] = None
    rohs: str = ""


# --------------------------------------------------------------------------- #
# Matching / parsing helpers (ported from sourcing_engine + the clients)
# --------------------------------------------------------------------------- #
def parse_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def manufacturer_matches(expected, actual):
    expected = str(expected or "").strip().lower()
    actual = str(actual or "").strip().lower()
    if not expected:
        return True
    return expected == actual or expected in actual or actual in expected


def mpn_matches(expected, actual):
    return part_numbers_equivalent(expected, actual)


def price_as_float(value):
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 999999.0


def parse_stock(value):
    text = str(value or "").replace(",", "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def append_note(existing, note):
    notes = [item.strip() for item in str(existing or "").split(";") if item.strip()]
    if note not in notes:
        notes.append(note)
    return "; ".join(notes)


def _looks_active(candidate: SupplierResult):
    text = " ".join([
        str(candidate.notes or ""),
        str(candidate.product_url or ""),
        str(candidate.lifecycle_status or ""),
    ]).lower()
    return not any(word in text for word in ["obsolete", "discontinued", "nrnd"])


def rank_candidates(candidates, requested_part_number, manufacturer="",
                    required_qty=None, relaxed=False, match_supplier_part_number=False):
    """Shared ranking (identical scoring to the POC's per-client _rank_candidates)."""
    requested_key = normalize_part_number(requested_part_number)
    required_qty = parse_int(required_qty)
    scored = []

    for candidate in candidates:
        if candidate is None:
            continue
        supplier_key = normalize_part_number(candidate.supplier_part_number)
        mpn_matches_candidate = part_numbers_equivalent(requested_part_number, candidate.mpn)
        supplier_matches_candidate = requested_key == supplier_key

        if match_supplier_part_number:
            if not supplier_matches_candidate:
                continue
        elif not mpn_matches_candidate:
            continue

        if manufacturer:
            manufacturer_ok = (manufacturers_equivalent(manufacturer, candidate.manufacturer)
                               if relaxed else manufacturer_matches(manufacturer, candidate.manufacturer))
            if not manufacturer_ok:
                continue

        enough_stock = required_qty is None or candidate.stock >= required_qty
        score = (
            100 if mpn_matches_candidate else 0,
            90 if supplier_matches_candidate else 0,
            60 if manufacturer and manufacturers_equivalent(manufacturer, candidate.manufacturer) else 0,
            40 if enough_stock else 0,
            20 if _looks_active(candidate) else 0,
            -price_as_float(candidate.unit_price),
        )
        scored.append((score, candidate))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


# --------------------------------------------------------------------------- #
# HTTP with retry/backoff (guide §6.2) + traceability logging (guide §6.6)
# --------------------------------------------------------------------------- #
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _mask_url(url: str) -> str:
    """Never log a full apiKey (Mouser passes it in the query string)."""
    if "apiKey=" not in url:
        return url
    import re
    return re.sub(r"(apiKey=)[^&]+", lambda m: m.group(1) + "****", url)


def _retry_wait_seconds(resp: requests.Response, attempt: int) -> float:
    for header in ("Retry-After", "X-RateLimit-Reset"):
        val = resp.headers.get(header)
        if val:
            try:
                return min(float(val), 60.0)
            except ValueError:
                pass
    return min(2 ** attempt, 30.0)


def http_request(method: str, url: str, *, supplier: str = "supplier",
                 max_attempts: int = 4, timeout: int = 30,
                 sleep: Callable[[float], None] = time.sleep, **kwargs) -> requests.Response:
    """Perform an HTTP request, retrying ONLY on 429/5xx/timeout with exponential
    backoff (honoring Retry-After / X-RateLimit-Reset). 400/401/404 are returned
    to the caller unretried (401 lets the DigiKey client refresh its token once).
    Logs supplier, endpoint, status, rate-limit-remaining, and latency."""
    last_resp: Optional[requests.Response] = None
    for attempt in range(max_attempts):
        started = time.monotonic()
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            log.warning("%s %s %s -> network error: %s (attempt %d)",
                        supplier, method, _mask_url(url), exc, attempt + 1)
            if attempt < max_attempts - 1:
                sleep(min(2 ** attempt, 30.0))
                continue
            raise
        latency_ms = int((time.monotonic() - started) * 1000)
        remaining = resp.headers.get("X-RateLimit-Remaining", "?")
        log.info("%s %s %s -> %s (rl-remaining=%s, %dms)",
                 supplier, method, _mask_url(url), resp.status_code, remaining, latency_ms)
        last_resp = resp
        if resp.status_code in RETRYABLE_STATUS and attempt < max_attempts - 1:
            sleep(_retry_wait_seconds(resp, attempt))
            continue
        return resp
    return last_resp


def raise_for_status(response: requests.Response, context: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = (response.text or "").strip() or (response.reason or "No response body")
        raise RuntimeError(f"{context}: {response.status_code} {detail[:300]}") from exc
