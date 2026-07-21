"""Bridge AutoBOM's persisted line shape -> the columns the cart/list builders read.

Phase 3 persists  status='sourced-mouser'  (hyphen, UI shape)
Builders expect   sourcing_status='sourced_mouser' (underscore)

Only genuinely SOURCED lines are ever mapped. Unsourceable parts are a sourcing
failure that never reaches the bucket (see sourcing_engine.sourceable), so the
flush only ever consolidates already-good parts.
"""

from __future__ import annotations

import pandas as pd

BUILDER_COLUMNS = ["selected_supplier", "sourcing_status", "supplier_part_number",
                   "supplier_order_qty", "mpn", "manufacturer", "cpn"]

_SUPPLIER_BY_STATUS = {
    "sourced-mouser": ("mouser", "sourced_mouser"),
    "sourced_mouser": ("mouser", "sourced_mouser"),
    "sourced-digikey": ("digikey", "sourced_digikey"),
    "sourced_digikey": ("digikey", "sourced_digikey"),
}


def _row(mpn, mfr, supplier_pn, qty, status, supplier, cpn=""):
    key = str(status or "").strip().lower()
    if key not in _SUPPLIER_BY_STATUS:
        # fall back to the explicit supplier field when status is unhelpful
        sup = str(supplier or "").strip().lower()
        key = f"sourced-{sup}" if sup in ("mouser", "digikey") else ""
    mapped = _SUPPLIER_BY_STATUS.get(key)
    if not mapped:
        return None                      # not sourced -> never flushed
    sel, sourcing_status = mapped
    if not supplier_pn or not qty:
        return None                      # nothing buyable without a PN + qty
    return {"selected_supplier": sel, "sourcing_status": sourcing_status,
            "supplier_part_number": str(supplier_pn), "supplier_order_qty": qty,
            "mpn": str(mpn or ""), "manufacturer": str(mfr or ""), "cpn": str(cpn or "")}


def from_snapshot_line(line: dict):
    """Request.items_snapshot line. Tolerates BOTH snapshot shapes in the wild:
    seeded requests carry `supplier_pn` (snake) while runtime request-to-order
    snapshots carry `supplierPn` (camel)."""
    supplier_pn = line.get("supplierPn") or line.get("supplier_pn")
    return _row(line.get("mpn"), line.get("mfr"), supplier_pn, line.get("qty"),
                line.get("status"), line.get("supplier"), line.get("cpn"))


def from_bom_line(li):
    """ORM BomLine."""
    return _row(li.mpn, li.mfr, li.supplier_pn, li.qty, li.status, li.supplier, li.cpn)


def rows_to_dataframe(rows) -> pd.DataFrame:
    rows = [r for r in rows if r]
    return pd.DataFrame(rows, columns=BUILDER_COLUMNS) if rows else pd.DataFrame(columns=BUILDER_COLUMNS)


def requests_to_dataframe(requests) -> pd.DataFrame:
    """Flatten a bucket's Requests into builder rows (sourced lines only)."""
    rows = []
    for r in requests:
        for line in (r.items_snapshot or []):
            rows.append(from_snapshot_line(line))
    return rows_to_dataframe(rows)


def bom_to_dataframe(bom) -> pd.DataFrame:
    return rows_to_dataframe([from_bom_line(li) for li in sorted(bom.lines, key=lambda x: x.line_no)])
