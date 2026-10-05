from dataclasses import asdict, dataclass, field

import inspect
import os
import time

from supplier_lookup_cache import SupplierLookupCache, build_lookup_key

# See Documentation/AutoBOM_QAQC_State_Cache_Deep_Dive_Report.md, Q3
# defect A: stock/price/candidate-selection data has no freshness rule
# without this. Conservative default (a normal engineering-procurement
# workday) -- overridable per deployment, same override pattern as
# SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS in supplier_lookup_cache.py.
DEFAULT_SUPPLIER_CACHE_TTL_SECONDS = 4 * 60 * 60
# Bumped whenever the cached value's shape changes (e.g. this TTL/cached_at
# wrapper was added here) -- an entry written under a different version is
# always treated as a cache miss (see _supplier_result_from_cache), so a
# schema change fails open to a live lookup rather than crashing or
# silently misinterpreting old data.
SUPPLIER_CACHE_SCHEMA_VERSION = 2


def _supplier_lookup_cache_ttl_seconds():
    try:
        return float(os.getenv("SUPPLIER_LOOKUP_CACHE_TTL_SECONDS", DEFAULT_SUPPLIER_CACHE_TTL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_SUPPLIER_CACHE_TTL_SECONDS


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
    # Best-effort, defensively populated from whatever category-style
    # field the vendor's raw response happens to expose (see
    # mouser_client._mouser_part_to_result / digikey_client
    # ._digikey_product_to_result). Empty when the response doesn't have
    # one -- never fabricated. Existing cached SupplierResult JSON
    # without this key still loads fine via the field's default.
    category: str = ""
    # Same best-effort/defensive posture as category, added directly in
    # response to an operator report that Find Replacement's results
    # table had no way to judge a candidate (blank Description/Package,
    # no voltage/tolerance/current/temp) -- "can't make an effective
    # replacement without that." description/package are each a plain
    # string when the vendor's response has an obvious single field for
    # them; characteristics holds every other parametric attribute the
    # vendor returned (Mouser's ProductAttributes / DigiKey's Parameters)
    # as {attribute name: value}, generic rather than guessing which
    # specs matter for a given part category. Existing cached
    # SupplierResult JSON without these keys still loads fine via each
    # field's default.
    description: str = ""
    package: str = ""
    characteristics: dict = field(default_factory=dict)


def parse_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def manufacturer_matches(expected, actual):
    expected = str(expected or "").strip().lower()
    actual = str(actual or "").strip().lower()

    if not expected:
        return True

    return expected == actual or expected in actual or actual in expected



def mpn_matches(expected, actual):
    from manufacturer_aliases import part_numbers_equivalent

    return part_numbers_equivalent(expected, actual)


def decide_no_split_supplier(row, mouser_result=None, digikey_result=None):
    required_qty = parse_int(row.get("required_qty"))
    manufacturer = str(row.get("manufacturer", "")).strip()
    mpn = str(row.get("mpn", "")).strip()
    qty_per_board = parse_int(row.get("qty_per_board"))
    build_quantity = parse_int(row.get("build_quantity"))

    if qty_per_board is not None and build_quantity is not None:
        order_qty = qty_per_board * build_quantity
    else:
        order_qty = required_qty
    if not mpn:
        return {
            "selected_supplier": "",
            "supplier_order_qty": "",
            "mouser_stock": "",
            "digikey_stock": "",
            "sourcing_status": "manual_review",
            "sourcing_notes": "Missing MPN; cannot source.",
        }

    if required_qty is None:
        return {
            "selected_supplier": "",
            "supplier_order_qty": "",
            "mouser_stock": "",
            "digikey_stock": "",
            "sourcing_status": "manual_review",
            "sourcing_notes": "Missing or invalid required_qty.",
        }

    mouser_stock = mouser_result.stock if mouser_result else 0
    digikey_stock = digikey_result.stock if digikey_result else 0

    if mouser_result and mouser_stock >= required_qty:
        notes = ["Mouser can cover full required quantity."]
        if mouser_result.notes:
            notes.append(mouser_result.notes)
        return {
            "selected_supplier": "Mouser",
            "supplier_part_number": mouser_result.supplier_part_number,
            "unit_price": mouser_result.unit_price,
            "supplier_order_qty": order_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_mouser",
            "sourcing_notes": "; ".join(notes),
        }

    if digikey_result and digikey_stock >= required_qty:
        notes = ["Mouser could not cover full quantity; DigiKey can."]
        if digikey_result.notes:
            notes.append(digikey_result.notes)
        return {
            "selected_supplier": "DigiKey",
            "supplier_part_number": digikey_result.supplier_part_number,
            "unit_price": digikey_result.unit_price,
            "supplier_order_qty": order_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_digikey",
            "sourcing_notes": "; ".join(notes),
    }

    return {
        "selected_supplier": "",
        "supplier_order_qty": "",
        "mouser_stock": mouser_stock,
        "digikey_stock": digikey_stock,
        "sourcing_status": "check_wall_inventory",
        "sourcing_notes": "Neither Mouser nor DigiKey can cover full required quantity.",
    }


SOURCING_DECISION_COLUMNS = [
    "selected_supplier",
    "supplier_part_number",
    "unit_price",
    "supplier_order_qty",
    "mouser_stock",
    "digikey_stock",
    "sourcing_status",
    "sourcing_notes",
]

EMPTY_SOURCING_DECISION = {column: "" for column in SOURCING_DECISION_COLUMNS}


def source_row(row, mouser_lookup, digikey_lookup, persistent_cache=None, run_cache=None, enabled_sources=None):
    """
    Sources exactly one row using the same Mouser-first/DigiKey-fallback/
    no-split decision logic apply_sourcing_decisions() uses for a whole
    BOM: DigiKey is only queried when Mouser did not already cover the
    required quantity. This is the single shared seam Retry Exact and
    replacement re-sourcing call for one row, instead of each
    reimplementing (or partially duplicating) this orchestration.

    Returns a dict with every key in SOURCING_DECISION_COLUMNS always
    present as a string, so a caller overwriting a row's existing
    sourcing fields with this result can never leave a stale value from
    a previous decision behind.

    persistent_cache/run_cache may be shared across many calls (a full
    BOM pass) or omitted for one ad hoc row (Retry/replacement), in which
    case a persistent cache is loaded and saved just for this call.

    `enabled_sources` is the authoritative source-selection boundary
    (defaults to both suppliers when omitted, for backward
    compatibility). A supplier absent from it is never read from the run
    cache, never read from the persistent cache, and never invoked --
    a no-op `lambda row: None` passed as `mouser_lookup`/`digikey_lookup`
    is NOT sufficient on its own, because `_cached_supplier_lookup()`
    would still happily return a stale cached result for that supplier
    from a previous (enabled) run without ever reaching the lookup
    callable at all. See
    Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md.
    """
    owns_cache = persistent_cache is None
    persistent_cache = persistent_cache if persistent_cache is not None else SupplierLookupCache()
    run_cache = run_cache if run_cache is not None else {}
    enabled = frozenset({"mouser", "digikey"}) if enabled_sources is None else frozenset(enabled_sources)

    mpn = str(row.get("mpn", "")).strip()
    manufacturer = str(row.get("manufacturer", "")).strip()

    mouser_result = None
    digikey_result = None
    lookup_notes = []

    if mpn:
        required_qty = parse_int(row.get("required_qty"))

        if "mouser" in enabled:
            try:
                mouser_result = _cached_supplier_lookup(
                    "mouser",
                    row,
                    persistent_cache,
                    run_cache,
                    lambda: mouser_lookup(row),
                )
            except Exception as exc:
                mouser_result = None
                lookup_notes.append(f"Mouser lookup failed: {exc}")

        if "digikey" in enabled and (
            not mouser_result or required_qty is None or mouser_result.stock < required_qty
        ):
            try:
                digikey_result = _cached_supplier_lookup(
                    "digikey",
                    row,
                    persistent_cache,
                    run_cache,
                    lambda: _call_digikey_lookup(
                        digikey_lookup,
                        row,
                        mpn,
                        manufacturer,
                    ),
                )
            except Exception as exc:
                digikey_result = None
                lookup_notes.append(f"DigiKey lookup failed: {exc}")

    decision = decide_no_split_supplier(row, mouser_result, digikey_result)

    if lookup_notes:
        existing = decision.get("sourcing_notes", "")
        decision["sourcing_notes"] = "; ".join([existing] + lookup_notes) if existing else "; ".join(lookup_notes)

    full_decision = dict(EMPTY_SOURCING_DECISION)
    full_decision.update(decision)
    full_decision = {key: str(value) for key, value in full_decision.items()}

    if owns_cache:
        persistent_cache.save()

    return full_decision


def apply_sourcing_decisions(clean_bom, mouser_lookup, digikey_lookup, enabled_sources=None):
    updated = clean_bom.copy().astype(object)
    persistent_cache = SupplierLookupCache()
    run_cache = {}

    for column in SOURCING_DECISION_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    for index, row in updated.iterrows():
        decision = source_row(
            row,
            mouser_lookup,
            digikey_lookup,
            persistent_cache=persistent_cache,
            run_cache=run_cache,
            enabled_sources=enabled_sources,
        )

        for key, value in decision.items():
            updated.at[index, key] = value

    persistent_cache.save()
    return updated


def _cached_supplier_lookup(supplier_name, row, persistent_cache, run_cache, lookup_fn):
    key = build_lookup_key(supplier_name, row)

    if key in run_cache:
        return run_cache[key]

    cached_value = persistent_cache.get(key)
    if cached_value:
        result = _supplier_result_from_cache(cached_value)
        # A malformed/obsolete cached entry (see _supplier_result_from_cache)
        # is a cache MISS, not a confirmed "supplier has no match" -- it
        # must fall through to a live lookup below rather than being
        # stored/returned as a false negative (Codex QA/QC deep-dive
        # report, Q4). A genuine cached "no match" is never stored in the
        # first place (see the `if result:` guard below), so a truthy
        # cached_value here is always either a valid result or garbage.
        if result is not None:
            run_cache[key] = result
            return result

    result = lookup_fn()
    run_cache[key] = result

    if result:
        # Overwrites any malformed entry that fell through above with a
        # valid one, satisfying "replace the bad entry ... if the lookup
        # succeeds" without needing a separate cache-delete operation.
        persistent_cache.set(key, _supplier_result_to_cache(result))

    return result


def _supplier_result_to_cache(result):
    return {
        "schema_version": SUPPLIER_CACHE_SCHEMA_VERSION,
        "cached_at": time.time(),
        "value": asdict(result),
    }


def _supplier_result_from_cache(value):
    """
    Fails open to a live lookup for anything that isn't a fresh,
    current-schema entry -- returns None (a cache MISS, per Q4, not a
    confirmed "no match") for: a pre-existing entry written before this
    schema-version/TTL wrapper existed, an entry whose TTL has expired,
    or a malformed/incompatible value. Never raises.
    """
    if not isinstance(value, dict) or value.get("schema_version") != SUPPLIER_CACHE_SCHEMA_VERSION:
        return None

    cached_at = value.get("cached_at")
    if not isinstance(cached_at, (int, float)):
        return None

    if time.time() - cached_at > _supplier_lookup_cache_ttl_seconds():
        return None

    try:
        return SupplierResult(**(value.get("value") or {}))
    except TypeError:
        return None


def _call_digikey_lookup(digikey_lookup, row, mpn, manufacturer):
    signature = inspect.signature(digikey_lookup)
    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if len(positional_parameters) == 1:
        return digikey_lookup(row)

    return digikey_lookup(mpn, manufacturer)
