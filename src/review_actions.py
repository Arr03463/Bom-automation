"""
Needs Review recovery actions: Retry Exact and Find Replacement selection
write through this module. Both call sourcing_engine.source_row() -- the
same Mouser-first/DigiKey-fallback/no-split seam full-BOM sourcing uses --
rather than a second sourcing algorithm, and both mutate the canonical
ActiveBomState through its one shared update_row() seam rather than a
detached dataset.

Check PartsBox needs no function here: it is
component_lookup.search_components(component_lookup.build_query_from_bom_row(row,
sources={"partsbox"})) called directly by the caller, reusing the exact
same lookup path Find Replacement uses with Mouser/DigiKey.
"""

from digikey_client import DigiKeyClient
from mouser_client import MouserClient
from sourcing_engine import EMPTY_SOURCING_DECISION, source_row

# Fields that belong to a specific component identity and must never
# survive a component transition (a new replacement, or PartsBox
# rediscovering a different match) unless the fresh sourcing pass below
# sets them again. Sourcing fields are covered by EMPTY_SOURCING_DECISION;
# these are the PartsBox/legacy fields sourcing_engine doesn't know about.
_STALE_NON_SOURCING_FIELDS = {
    "partsbox_match_status": "",
    "partsbox_part_id": "",
    "supplier_match_status": "",
}


def retry_exact_sourcing(active_bom_state, row_id, mouser_client=None, digikey_client=None):
    """
    Re-runs the exact same per-row sourcing seam
    sourcing_engine.apply_sourcing_decisions() uses for a whole BOM,
    scoped to one row, and writes the outcome back through
    ActiveBomState.update_row(). DigiKey is only queried when Mouser
    doesn't already cover the required quantity -- Retry does not
    duplicate or diverge from that orchestration.
    """
    row = active_bom_state.get_row(row_id)
    if row is None:
        raise KeyError(f"Unknown row_id: {row_id}")

    mouser = mouser_client or MouserClient()
    digikey = digikey_client or DigiKeyClient()

    decision = source_row(row, mouser.find_best_match_for_row, digikey.find_best_match_for_row)
    return active_bom_state.update_row(row_id, decision)


def apply_replacement(active_bom_state, row_id, replacement, mouser_client=None, digikey_client=None):
    """
    Writes an operator-approved replacement onto the canonical BOM row
    through the one shared mutation seam, instead of a detached
    replacement table or a UI-only dictionary. `replacement` is a
    normalized lookup result dict (component_lookup.LookupResult.to_dict())
    as returned by search_components().

    The discovery source (which service surfaced this candidate) never
    becomes the purchasing supplier directly -- that was Phase 3's
    critical defect. Instead:

    1. Clear every stale sourcing/PartsBox field from the OLD component
       identity (EMPTY_SOURCING_DECISION plus the PartsBox/legacy
       fields), then set the new component's mpn/manufacturer/
       description. This prevents a previous Mouser/DigiKey selection or
       PartsBox match from surviving a component transition.
    2. If the candidate was discovered via PartsBox, record that as an
       internal match only (partsbox_match_status/partsbox_part_id) --
       this is inventory information, not confirmed external purchase
       readiness, since PartsBox stock is not a field this client can
       confirm (see component_lookup._partsbox_part_to_result).
    3. Re-run the row through sourcing_engine.source_row() -- the same
       Mouser-first/DigiKey-fallback/no-split decision full-BOM sourcing
       uses -- so the purchasing supplier, supplier part number, stock,
       supplier_order_qty, and sourcing_status are all recomputed for the
       new component identity rather than copied from the discovery
       candidate. A DigiKey-discovered replacement that Mouser can also
       fully cover is purchased from Mouser, exactly as normal sourcing
       would decide.

    The row is only Ready if source_row()'s decision says so -- selecting
    a candidate does not, by itself, mark anything Ready.
    """
    row = active_bom_state.get_row(row_id)
    if row is None:
        raise KeyError(f"Unknown row_id: {row_id}")

    original_mpn = row.get("original_mpn") or row.get("mpn", "")
    original_manufacturer = row.get("original_manufacturer") or row.get("manufacturer", "")
    discovery_source = str(replacement.get("source", "")).strip()

    trace_note = (
        f"Replacement selected via Find Replacement (was {original_mpn}); "
        f"discovered via {discovery_source or 'unknown source'}."
    )
    existing_notes = str(row.get("notes", "")).strip()
    combined_notes = f"{existing_notes}; {trace_note}" if existing_notes else trace_note

    identity_updates = dict(EMPTY_SOURCING_DECISION)
    identity_updates.update(_STALE_NON_SOURCING_FIELDS)
    identity_updates.update(
        {
            "original_mpn": original_mpn,
            "original_manufacturer": original_manufacturer,
            "mpn": replacement.get("mpn", ""),
            "manufacturer": replacement.get("manufacturer", ""),
            "description": replacement.get("description") or row.get("description", ""),
            "status": "clean",
            "replacement_discovery_source": discovery_source,
            "notes": combined_notes,
        }
    )
    active_bom_state.update_row(row_id, identity_updates)

    if discovery_source.strip().lower() == "partsbox":
        # Internal match only. Do not assume this covers external
        # purchasing -- the re-sourcing pass below determines that
        # independently against Mouser/DigiKey.
        active_bom_state.update_row(
            row_id,
            {
                "partsbox_match_status": "matched",
                "partsbox_part_id": (replacement.get("raw") or {}).get("part/id", ""),
            },
        )

    mouser = mouser_client or MouserClient()
    digikey = digikey_client or DigiKeyClient()

    updated_row = active_bom_state.get_row(row_id)
    decision = source_row(updated_row, mouser.find_best_match_for_row, digikey.find_best_match_for_row)

    return active_bom_state.update_row(row_id, decision)
