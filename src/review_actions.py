"""
Needs Review recovery actions: Retry Exact and Find Replacement selection
write through this module. Both reuse existing sourcing/lookup
capabilities -- neither introduces a second sourcing or search
implementation -- and both mutate the canonical ActiveBomState through
its one shared update_row() seam rather than a detached dataset.

Check PartsBox needs no function here: it is
component_lookup.search_components(component_lookup.build_query_from_bom_row(row,
sources={"partsbox"})) called directly by the caller, reusing the exact
same lookup path Find Replacement uses with Mouser/DigiKey.
"""

from digikey_client import DigiKeyClient
from mouser_client import MouserClient
from sourcing_engine import decide_no_split_supplier

_EMPTY_DECISION = {
    "selected_supplier": "",
    "supplier_part_number": "",
    "unit_price": "",
    "supplier_order_qty": "",
    "mouser_stock": "",
    "digikey_stock": "",
    "sourcing_status": "",
    "sourcing_notes": "",
}


def retry_exact_sourcing(active_bom_state, row_id, mouser_client=None, digikey_client=None):
    """
    Re-runs the same per-row supplier lookups and no-split decision logic
    sourcing_engine.apply_sourcing_decisions() uses for the whole BOM,
    scoped to exactly one row, and writes the outcome back through
    ActiveBomState.update_row(). This is the shared sourcing path, not a
    separate lookup built just for Retry.
    """
    row = active_bom_state.get_row(row_id)
    if row is None:
        raise KeyError(f"Unknown row_id: {row_id}")

    mouser = mouser_client or MouserClient()
    digikey = digikey_client or DigiKeyClient()

    mouser_result = None
    digikey_result = None
    notes = []

    mpn = str(row.get("mpn", "")).strip()
    if mpn:
        try:
            mouser_result = mouser.find_best_match_for_row(row)
        except Exception as exc:
            notes.append(f"Mouser retry failed: {exc}")

        try:
            digikey_result = digikey.find_best_match_for_row(row)
        except Exception as exc:
            notes.append(f"DigiKey retry failed: {exc}")

    decision = decide_no_split_supplier(row, mouser_result, digikey_result)

    if notes:
        existing = decision.get("sourcing_notes", "")
        decision["sourcing_notes"] = "; ".join([existing] + notes) if existing else "; ".join(notes)

    # decide_no_split_supplier() only includes supplier_part_number/
    # unit_price on the branches that actually chose a supplier -- fill
    # the rest from _EMPTY_DECISION so a failed retry clears stale values
    # from an earlier attempt instead of leaving them untouched.
    full_decision = dict(_EMPTY_DECISION)
    full_decision.update(decision)
    updates = {key: str(value) for key, value in full_decision.items()}

    return active_bom_state.update_row(row_id, updates)


def apply_replacement(active_bom_state, row_id, replacement):
    """
    Writes an operator-approved replacement onto the canonical BOM row
    through the one shared mutation seam, instead of a detached
    replacement table or a UI-only dictionary. `replacement` is a
    normalized lookup result dict (component_lookup.LookupResult.to_dict())
    as returned by search_components().

    For a Mouser/DigiKey replacement, selected_supplier/sourcing_status
    are set exactly the way sourcing_engine's own decision would set
    them, so the row is indistinguishable from a normally-sourced row to
    the existing Mouser cart / DigiKey MyList builders on a later
    purchasing pass -- no second sourcing implementation. For a PartsBox
    replacement, the row is marked matched and left for a subsequent
    Retry to confirm external availability, since PartsBox is inventory,
    not an external supplier order.
    """
    row = active_bom_state.get_row(row_id)
    if row is None:
        raise KeyError(f"Unknown row_id: {row_id}")

    original_mpn = row.get("original_mpn") or row.get("mpn", "")
    original_manufacturer = row.get("original_manufacturer") or row.get("manufacturer", "")

    updates = {
        "original_mpn": original_mpn,
        "original_manufacturer": original_manufacturer,
        "mpn": replacement.get("mpn", ""),
        "manufacturer": replacement.get("manufacturer", ""),
        "description": replacement.get("description") or row.get("description", ""),
        "status": "clean",
    }

    source = str(replacement.get("source", "")).strip().lower()
    supplier_part_number = replacement.get("supplier_part_number", "")
    unit_price = replacement.get("unit_price", "")
    stock = replacement.get("stock")
    trace_note = f"Replacement selected via Find Replacement (was {original_mpn})."

    if source == "mouser":
        updates.update(
            {
                "selected_supplier": "Mouser",
                "supplier_part_number": supplier_part_number,
                "unit_price": unit_price,
                "mouser_stock": stock if stock is not None else "",
                "sourcing_status": "sourced_mouser",
                "sourcing_notes": trace_note,
            }
        )
    elif source == "digikey":
        updates.update(
            {
                "selected_supplier": "DigiKey",
                "supplier_part_number": supplier_part_number,
                "unit_price": unit_price,
                "digikey_stock": stock if stock is not None else "",
                "sourcing_status": "sourced_digikey",
                "sourcing_notes": trace_note,
            }
        )
    elif source == "partsbox":
        updates.update(
            {
                "partsbox_match_status": "matched",
                "partsbox_part_id": (replacement.get("raw") or {}).get("part/id", ""),
                "sourcing_notes": (
                    "Replacement matched via Check PartsBox "
                    f"(was {original_mpn}); re-run sourcing to confirm "
                    "external availability."
                ),
            }
        )
    else:
        updates["sourcing_notes"] = (
            f"Replacement selected from {replacement.get('source', 'unknown source')} "
            f"(was {original_mpn})."
        )

    return active_bom_state.update_row(row_id, updates)
