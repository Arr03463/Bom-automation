"""Purchasing + system-status endpoints (Phase 3).

- Cart DRY-RUN preview: build a Mouser cart + DigiKey list from a BOM's sourced
  lines using the Phase 2 clients in dry-run mode. Building/reviewing only —
  never submits an order (that constraint is permanent; live writes are Phase 4).
- System status: a fresh, non-secret health snapshot for the Admin dashboard.
"""

from __future__ import annotations

import os

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException

from auth.deps import require_user
from config import settings
from db.models import Bom, User
from db.session import get_db
from services.digikey_mylists_client import build_digikey_mylists_parts
from services.mouser_cart_client import build_mouser_cart_items
from sqlalchemy.orm import Session

router = APIRouter(tags=["purchasing"])


def _bom_dataframe(bom: Bom) -> pd.DataFrame:
    rows = []
    for li in sorted(bom.lines, key=lambda x: x.line_no):
        rows.append({
            "selected_supplier": li.supplier or "",
            "sourcing_status": "sourced_mouser" if li.supplier == "mouser" else "sourced_digikey" if li.supplier == "digikey" else "",
            "supplier_part_number": li.supplier_pn or "",
            "supplier_order_qty": li.qty or 0,
            "mpn": li.mpn or "", "manufacturer": li.mfr or "", "cpn": li.cpn or "",
        })
    return pd.DataFrame(rows)


@router.post("/purchasing/cart/preview")
def cart_preview(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    """DRY-RUN cart/list preview for a BOM's sourced lines."""
    bom = db.get(Bom, body.get("bomId"))
    if not bom:
        raise HTTPException(404, "BOM not found")
    df = _bom_dataframe(bom)
    mouser_items = build_mouser_cart_items(df) if not df.empty else []
    digikey_parts = build_digikey_mylists_parts(df) if not df.empty else []
    return {
        "bomId": bom.id, "dryRun": True, "submits": False,
        "mouser": {"items": mouser_items, "count": len(mouser_items)},
        "digikey": {"parts": digikey_parts, "count": len(digikey_parts)},
        "note": "Preview only — AutoBOM never submits an order. Cart is built for review.",
    }


@router.get("/system/status")
def system_status(user: User = Depends(require_user)):
    """Fresh non-secret health snapshot for the Admin dashboard."""
    s = settings.status()
    def row(i, label, ok, detail):
        return {"id": i, "label": label, "state": "green" if ok else "amber", "detail": detail}
    return {
        "status": [
            row("app", "Application", True, "All services operational"),
            row("mouser", "Mouser API", s["suppliers"]["mouser_search"], "Connected" if s["suppliers"]["mouser_search"] else "Key missing"),
            row("digikey", "DigiKey API", s["suppliers"]["digikey"], "Connected" if s["suppliers"]["digikey"] else "Credentials missing"),
            row("partsbox", "PartsBox API", s["suppliers"]["partsbox"], "Connected" if s["suppliers"]["partsbox"] else "Key missing"),
            row("graph", "Purchasing sheet (Graph)", s["graph_sheet_writer"] == "live", s["graph_sheet_writer"]),
            row("db", "Database", s["database"] == "postgres", s["database"]),
        ],
        "mode": s["mode"], "auth": s["auth"],
    }
