"""Sourcing engine — Mouser-then-DigiKey whole-part decision (ported from POC).

DigiKey is only queried when Mouser is missing or short (cost-saving fallback).
Two-tier cache: per-run dict + persistent TTL cache. The normalized SupplierResult
now lives in services.supplier_base (shared with the clients).

Adds `validate_mpn` for B2-guarded part creation (does this MPN exist at any
supplier?). The full two-mode parametric search (search_available_stock /
search_suppliers with PartsBox overlay + ParametricFilters) ships with the
search UI in a later phase — this module is the supplier-primary core.
"""

from __future__ import annotations

import inspect
from dataclasses import asdict

from services.supplier_base import SupplierResult, parse_int
from services.supplier_lookup_cache import SupplierLookupCache, build_lookup_key

SOURCING_COLUMNS = [
    "selected_supplier", "supplier_part_number", "unit_price", "supplier_order_qty",
    "mouser_stock", "digikey_stock", "sourcing_status", "sourcing_notes",
]


def decide_no_split_supplier(row, mouser_result=None, digikey_result=None):
    required_qty = parse_int(row.get("required_qty"))
    mpn = str(row.get("mpn", "")).strip()
    qty_per_board = parse_int(row.get("qty_per_board"))
    build_quantity = parse_int(row.get("build_quantity"))
    order_qty = qty_per_board * build_quantity if (qty_per_board is not None and build_quantity is not None) else required_qty

    if not mpn:
        return {"selected_supplier": "", "supplier_order_qty": "", "mouser_stock": "", "digikey_stock": "",
                "sourcing_status": "manual_review", "sourcing_notes": "Missing MPN; cannot source."}
    if required_qty is None:
        return {"selected_supplier": "", "supplier_order_qty": "", "mouser_stock": "", "digikey_stock": "",
                "sourcing_status": "manual_review", "sourcing_notes": "Missing or invalid required_qty."}

    mouser_stock = mouser_result.stock if mouser_result else 0
    digikey_stock = digikey_result.stock if digikey_result else 0

    if mouser_result and mouser_stock >= required_qty:
        notes = ["Mouser can cover full required quantity."]
        if mouser_result.notes:
            notes.append(mouser_result.notes)
        return {"selected_supplier": "Mouser", "supplier_part_number": mouser_result.supplier_part_number,
                "unit_price": mouser_result.unit_price, "supplier_order_qty": order_qty,
                "mouser_stock": mouser_stock, "digikey_stock": digikey_stock,
                "sourcing_status": "sourced_mouser", "sourcing_notes": "; ".join(notes)}

    if digikey_result and digikey_stock >= required_qty:
        notes = ["Mouser could not cover full quantity; DigiKey can."]
        if digikey_result.notes:
            notes.append(digikey_result.notes)
        return {"selected_supplier": "DigiKey", "supplier_part_number": digikey_result.supplier_part_number,
                "unit_price": digikey_result.unit_price, "supplier_order_qty": order_qty,
                "mouser_stock": mouser_stock, "digikey_stock": digikey_stock,
                "sourcing_status": "sourced_digikey", "sourcing_notes": "; ".join(notes)}

    return {"selected_supplier": "", "supplier_order_qty": "", "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock, "sourcing_status": "check_wall_inventory",
            "sourcing_notes": "Neither Mouser nor DigiKey can cover full required quantity."}


def apply_sourcing_decisions(clean_bom, mouser_lookup, digikey_lookup):
    updated = clean_bom.copy().astype(object)
    persistent_cache = SupplierLookupCache()
    run_cache = {}

    for col in SOURCING_COLUMNS:
        if col not in updated.columns:
            updated[col] = ""

    for index, row in updated.iterrows():
        mpn = str(row.get("mpn", "")).strip()
        manufacturer = str(row.get("manufacturer", "")).strip()
        mouser_result = digikey_result = None
        lookup_notes = []

        if mpn:
            required_qty = parse_int(row.get("required_qty"))
            try:
                mouser_result = _cached_supplier_lookup("mouser", row, persistent_cache, run_cache,
                                                        lambda: mouser_lookup(row))
            except Exception as exc:
                mouser_result = None
                lookup_notes.append(f"Mouser lookup failed: {exc}")
            try:
                if not mouser_result or required_qty is None or mouser_result.stock < required_qty:
                    digikey_result = _cached_supplier_lookup("digikey", row, persistent_cache, run_cache,
                        lambda: _call_digikey_lookup(digikey_lookup, row, mpn, manufacturer))
            except Exception as exc:
                digikey_result = None
                lookup_notes.append(f"DigiKey lookup failed: {exc}")

        decision = decide_no_split_supplier(row, mouser_result, digikey_result)
        if lookup_notes:
            existing = decision.get("sourcing_notes", "")
            decision["sourcing_notes"] = "; ".join(([existing] + lookup_notes) if existing else lookup_notes)
        for key, value in decision.items():
            updated.at[index, key] = str(value)

    persistent_cache.save()
    return updated


def validate_mpn(mpn, manufacturer="", mouser_client=None, digikey_client=None):
    """B2-guarded validation: does this MPN exist at any supplier?
    Returns {valid, sources, mouser, digikey}. Never places an order."""
    if mouser_client is None:
        from services.mouser_client import MouserClient
        mouser_client = MouserClient()
    if digikey_client is None:
        from services.digikey_client import DigiKeyClient
        digikey_client = DigiKeyClient()

    sources, m_res, d_res = [], None, None
    try:
        m_res = mouser_client.find_best_match(mpn, manufacturer)
        if m_res:
            sources.append("mouser")
    except Exception:
        pass
    try:
        d_res = digikey_client.find_best_match(mpn, manufacturer)
        if d_res:
            sources.append("digikey")
    except Exception:
        pass
    return {"valid": bool(sources), "sources": sources,
            "mouser": asdict(m_res) if m_res else None,
            "digikey": asdict(d_res) if d_res else None}


# --- cache plumbing (ported) ----------------------------------------------
def _cached_supplier_lookup(supplier_name, row, persistent_cache, run_cache, lookup_fn):
    key = build_lookup_key(supplier_name, row)
    if key in run_cache:
        return run_cache[key]
    cached_value = persistent_cache.get(key)
    if cached_value:
        result = _from_cache(cached_value)
        run_cache[key] = result
        return result
    result = lookup_fn()
    run_cache[key] = result
    if result:
        persistent_cache.set(key, asdict(result))
    return result


def _from_cache(value):
    try:
        return SupplierResult(**value)
    except TypeError:
        return None


def _call_digikey_lookup(digikey_lookup, row, mpn, manufacturer):
    positional = [p for p in inspect.signature(digikey_lookup).parameters.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    return digikey_lookup(row) if len(positional) == 1 else digikey_lookup(mpn, manufacturer)
