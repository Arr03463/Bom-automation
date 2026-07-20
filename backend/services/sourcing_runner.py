"""Live sourcing over a persisted BOM, streamed per line.

Runs the Phase 2 engine (real Mouser/DigiKey via the cached lookup) line by line
so the UI can surface per-line outcomes as they resolve. Persists the results to
bom_lines and advances the BOM state. Per-line lookup failures degrade to a calm
`needs-review` with a note — never an exception that breaks the stream.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Bom, BomLine, User
from services.digikey_client import DigiKeyClient
from services.mouser_client import MouserClient
from services.sourcing_engine import (
    _cached_supplier_lookup, _call_digikey_lookup, decide_no_split_supplier,
)
from services.supplier_base import parse_int
from services.supplier_lookup_cache import SupplierLookupCache

# sourcing_status -> (line.status, line.supplier)
_STATUS_MAP = {
    "sourced_mouser": ("sourced-mouser", "mouser"),
    "sourced_digikey": ("sourced-digikey", "digikey"),
    "check_wall_inventory": ("check-wall", None),
    "manual_review": ("needs-review", None),
}


def _row(line: BomLine) -> dict:
    return {
        "mpn": line.mpn or "", "manufacturer": line.mfr or "",
        "required_qty": line.qty, "qty_per_board": None, "build_quantity": None,
        "supplier": line.supplier or "", "supplier_part_number": line.supplier_pn or "",
    }


def iterate_sourcing(db: Session, bom_id: str):
    """Generator yielding per-line result dicts, then a final done dict."""
    bom = db.get(Bom, bom_id)
    if bom is None:
        yield {"type": "error", "message": f"BOM {bom_id} not found"}
        return

    lines = sorted(bom.lines, key=lambda x: x.line_no)
    mouser = MouserClient()
    digikey = DigiKeyClient()
    persistent_cache = SupplierLookupCache()
    run_cache: dict = {}

    yield {"type": "start", "bom_id": bom_id, "total": len(lines)}

    for line in lines:
        row = _row(line)
        mouser_result = digikey_result = None
        notes = []
        if row["mpn"]:
            required_qty = parse_int(row["required_qty"])
            try:
                mouser_result = _cached_supplier_lookup(
                    "mouser", row, persistent_cache, run_cache,
                    lambda: mouser.find_best_match_for_row(row))
            except Exception as exc:
                notes.append(f"Mouser lookup failed: {exc}")
            try:
                if not mouser_result or required_qty is None or mouser_result.stock < required_qty:
                    digikey_result = _cached_supplier_lookup(
                        "digikey", row, persistent_cache, run_cache,
                        lambda: _call_digikey_lookup(digikey.find_best_match_for_row, row, row["mpn"], row["manufacturer"]))
            except Exception as exc:
                notes.append(f"DigiKey lookup failed: {exc}")

        decision = decide_no_split_supplier(row, mouser_result, digikey_result)
        status, supplier = _STATUS_MAP.get(decision["sourcing_status"], ("needs-review", None))

        # Persist the line result.
        line.status = status
        line.supplier = supplier
        if decision.get("supplier_part_number"):
            line.supplier_pn = decision["supplier_part_number"]
        unit = decision.get("unit_price")
        if unit not in (None, "", 0):
            try:
                line.unit_price = float(str(unit).replace("$", "").replace(",", ""))
                if line.qty is not None:
                    line.ext_price = round(line.unit_price * line.qty, 4)
            except ValueError:
                pass
        note = "; ".join([decision.get("sourcing_notes", "")] + notes).strip("; ")
        line.ex_reason = note if status in ("needs-review", "check-wall") else line.ex_reason
        db.flush()

        yield {
            "type": "line", "line_no": line.line_no, "mpn": line.mpn, "status": status,
            "supplier": supplier, "unit": float(line.unit_price) if line.unit_price is not None else None,
            "ext": float(line.ext_price) if line.ext_price is not None else None,
            "mouser_stock": decision.get("mouser_stock", 0), "digikey_stock": decision.get("digikey_stock", 0),
            "note": note,
        }

    persistent_cache.save()
    # Advance BOM state: results (exceptions if a pushback is already open is handled elsewhere).
    if bom.state in ("draft", "validated", "sourcing", "normalised", "results"):
        bom.state = "results"
    db.commit()

    from api import serializers as SR
    users_by_id = {u.id: u for u in db.query(User).all()}
    db.refresh(bom)
    yield {"type": "done", "bom": SR.bom(bom, sorted(bom.lines, key=lambda x: x.line_no), None, users_by_id)}
