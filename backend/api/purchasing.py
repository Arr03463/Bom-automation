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


@router.post("/purchasing/flush")
def flush_bucket(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Admin manual flush escape hatch (audit-logged). Honors the single
    FLUSH_MODE switch — dry-run by default; never submits an order."""
    if "admin" not in (user.roles or []):
        raise HTTPException(403, "Admin only")
    from services.bucket_flush import flush_stream
    result = flush_stream(db, body.get("stream", "main"), actor_id=user.id)
    from db.models import Audit
    from datetime import datetime, timezone
    import uuid
    db.add(Audit(id=f"au-flush-{uuid.uuid4().hex[:10]}",
                 ts="Today " + datetime.now(timezone.utc).strftime("%H:%M"), actor_id=user.id,
                 role="admin", action=f"Bucket flush ({result.get('stream')}, "
                                      f"{'dry-run' if result.get('dryRun') else 'LIVE'})",
                 entity_id="purchasing-bucket", entity_type="batch",
                 before="QUEUED", after=str(result.get("status")).upper()))
    db.commit()
    return result


@router.get("/purchasing/flush/status")
def flush_status(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Flush-mode visibility: the one switch + queued counts + legacy flags."""
    from db.models import Request
    counts = {s: db.query(Request).filter(Request.bucket_state == st).count()
              for s, st in (("critical", "QUEUED_CRITICAL"), ("main", "QUEUED_MAIN"))}
    return {"flushMode": settings.flush_mode, "live": settings.flush_live,
            "queued": counts, "legacyFlags": settings.legacy_flush_flags,
            "sheet": "live" if settings.graph_enabled else "console-fallback"}


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
            row("digikey_mylists", *_digikey_token_row()),
            row("partsbox", "PartsBox API", s["suppliers"]["partsbox"], "Connected" if s["suppliers"]["partsbox"] else "Key missing"),
            row("graph", "Purchasing sheet (Graph)", s["graph_sheet_writer"] == "live", s["graph_sheet_writer"]),
            row("db", "Database", s["database"] == "postgres", s["database"]),
        ],
        "mode": s["mode"], "auth": s["auth"],
    }


def _digikey_token_row():
    """(label, ok, detail) for the 3-legged MyLists token.

    Surfaced because it is the one credential that can go stale on its own: the
    refresh token expires after ~90 days and only a human can re-authorize it.
    Admin should see that coming, not discover it at flush time.
    """
    from services.digikey_user_auth import get_user_auth
    st = get_user_auth().status()
    label = "DigiKey MyLists token"
    detail = {
        "ok": "Auto-refreshing" + (f" (valid {st['expiresInSeconds'] // 60}m)" if st["cached"] else ""),
        "dry_run": "Dry-run — no live token needed",
        "not_configured": "Not authorized — run backend/scripts/digikey_oauth_setup.py",
        "static_token_no_refresh": "Static token, cannot self-refresh — re-authorize to enable auto-refresh",
        "error": f"Last refresh failed: {st['lastError']}",
    }.get(st["state"], st["state"])
    return label, st["state"] in ("ok", "dry_run"), detail
