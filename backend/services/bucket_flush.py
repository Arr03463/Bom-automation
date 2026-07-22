"""Bucket-flush orchestration (Phase 4).

Sequence: timer/manual trigger -> collect the stream's QUEUED requests -> map to
builder rows -> group by supplier -> call the EXISTING cart/list builders ->
capture the supplier identifier (Mouser CartKey / DigiKey listId) + total ->
append one row per supplier per batch to Josh's sheet -> mark WRITTEN.

Locked design decisions:
- ONE cart/list per batch. Mouser cart_key="" yields a FRESH CartKey per call
  (verified live), so Main and Critical never co-mingle.
- The sheet's URL column gets the ACCOUNT DEEP LINK carrying the batch's own
  CartKey / listId (both verified live to open that specific cart/list); the raw
  identifier is also stored on the Batch for traceability. The API-URL form
  (…?apiKey=…) is NEVER written anywhere — it would leak the API key.
- ONE switch: settings.flush_live. The orchestrator decides dry_run and passes
  it DOWN into the clients (they no longer decide for themselves).
- Atomic (Pattern A): sheet write must succeed for every row or the batch stays
  pending and its requests stay QUEUED — nothing half-written.
- Only sourceable parts ever reach here (sourcing_engine.sourceable gates it);
  a $0/empty cart is treated as a partial failure and writes NO row.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import settings
from db.models import Batch, Request
from services import flush_mapping
from services.bucket_timers import mark_flushed
from services.digikey_mylists_client import DigiKeyMyListsClient, build_digikey_mylists_parts
from services.mouser_cart_client import MouserCartClient, build_mouser_cart_items
from services.purchasing_sheet_writer import write_batch
from services.supplier_base import scrub_secrets

log = logging.getLogger("autobom.flush")

# Account deep links (buyer signs into the account and completes the purchase there).
# VERIFIED live 2026-07-20: ?cartKey=<key> opens THAT specific cart, and the
# MyLists URL opens that specific list — so each sheet row links to its own
# batch's cart/list, not a generic landing page. The API-URL form (…?apiKey=…)
# is never used here: it would leak the API key onto Josh's sheet.
MOUSER_CART_URL = "https://www.mouser.com/cart?cartKey={cart_key}"
MOUSER_ACCOUNT_CART_URL = "https://www.mouser.com/cart"   # dry-run fallback (no key yet)
DIGIKEY_LIST_URL = "https://www.digikey.com/en/mylists/list/{list_id}"

STREAM_STATE = {"critical": "QUEUED_CRITICAL", "main": "QUEUED_MAIN"}


def _next_batch_id(db: Session) -> str:
    nums = [int(m.group(1)) for (i,) in db.query(Batch.id).all()
            if (m := re.match(r"BATCH-0*(\d+)$", str(i)))]
    return f"BATCH-{(max(nums) + 1) if nums else 1:04d}"


def _estimated_total(requests, supplier: str) -> float:
    """Dry-run cost estimate from the already-sourced line extensions."""
    total = 0.0
    for r in requests:
        for line in (r.items_snapshot or []):
            if str(line.get("supplier") or "").lower() == supplier:
                try:
                    total += float(line.get("ext") or 0)
                except (TypeError, ValueError):
                    pass
    return round(total, 2)


def _mouser_batch(df, requests, dry_run: bool) -> dict | None:
    items = build_mouser_cart_items(df)
    if not items:
        return None
    client = MouserCartClient()
    client.dry_run = dry_run            # orchestrator is authoritative
    resp = client.add_items_to_cart(items, cart_key="")   # "" => FRESH cart per batch
    if dry_run:
        return {"supplier": "Mouser", "ref": "DRY-RUN", "total": _estimated_total(requests, "mouser"),
                "items_count": len(items), "link": MOUSER_ACCOUNT_CART_URL, "raw": resp}
    errors = resp.get("Errors") or []
    if errors:
        raise RuntimeError(f"Mouser cart errors: {errors}")
    cart_key = resp.get("CartKey")
    return {"supplier": "Mouser", "ref": cart_key,
            "total": resp.get("MerchandiseTotal"), "items_count": resp.get("TotalItemCount") or len(items),
            "link": MOUSER_CART_URL.format(cart_key=cart_key) if cart_key else MOUSER_ACCOUNT_CART_URL,
            "raw": resp}


def _digikey_batch(df, requests, dry_run: bool, list_name: str) -> dict | None:
    parts = build_digikey_mylists_parts(df)
    if not parts:
        return None
    client = DigiKeyMyListsClient()
    client.dry_run = dry_run
    client.enabled = True               # gating is the orchestrator's job now
    created = client.create_list(list_name)
    list_id = created if isinstance(created, str) else (
        created.get("ListId") or created.get("listId") or created.get("Id") or created.get("id"))
    if not dry_run and list_id:
        client.add_parts_to_list(list_id, parts)
    return {"supplier": "DigiKey", "ref": list_id or "DRY-RUN",
            "total": _estimated_total(requests, "digikey"), "items_count": len(parts),
            "link": DIGIKEY_LIST_URL.format(list_id=list_id) if (list_id and not dry_run) else DIGIKEY_LIST_URL.format(list_id="{listId}"),
            "raw": created}


def flush_stream(db: Session, stream: str, dry_run: bool | None = None, actor_id: str | None = None) -> dict:
    stream = (stream or "main").lower()
    if stream not in STREAM_STATE:
        raise ValueError(f"unknown stream {stream!r}")
    if dry_run is None:
        dry_run = not settings.flush_live

    requests = db.query(Request).filter(Request.bucket_state == STREAM_STATE[stream]).all()
    if not requests:
        return {"stream": stream, "dryRun": dry_run, "status": "empty", "written": 0,
                "message": f"No requests queued in the {stream} bucket."}

    df = flush_mapping.requests_to_dataframe(requests)
    if df.empty:
        return {"stream": stream, "dryRun": dry_run, "status": "no_sourced_lines", "written": 0,
                "message": "Queued requests contain no sourceable lines (nothing to cart)."}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    built = []
    try:
        m = _mouser_batch(df[df.selected_supplier == "mouser"], requests, dry_run)
        if m:
            built.append(m)
        d = _digikey_batch(df[df.selected_supplier == "digikey"], requests, dry_run,
                           f"AutoBOM {stream} {stamp}")
        if d:
            built.append(d)
    except Exception as exc:
        # scrub_secrets, never the raw exception: the Mouser cart client passes its
        # apiKey in the query string, so a network-level failure stringifies with it.
        safe = scrub_secrets(exc)
        log.warning("flush %s: cart/list build failed: %s", stream, safe)
        return {"stream": stream, "dryRun": dry_run, "status": "failed", "written": 0,
                "message": f"Cart/list build failed — batch stays queued: {safe}"}

    if not built:
        return {"stream": stream, "dryRun": dry_run, "status": "no_sourced_lines", "written": 0,
                "message": "No supplier group produced a cart."}

    # One sheet row per supplier per batch.
    carts = [{"supplier": b["supplier"], "category": "Electronic components",
              "cart_total": b["total"], "share_link": b["link"], "items_count": b["items_count"],
              "critical": stream == "critical", "entry_id": f"{stream}:{b['supplier']}"}
             for b in built]

    sheet = write_batch(carts)
    expected = sum(1 for c in carts if c["cart_total"] and float(c["cart_total"]) > 0)
    if sheet["written"] < expected:
        # Partial/failed write -> nothing is marked; batch stays queued (Pattern A).
        return {"stream": stream, "dryRun": dry_run, "status": "partial",
                "written": sheet["written"], "skipped": sheet["skipped"],
                "message": "Sheet write incomplete — requests remain QUEUED for the next flush."}

    # Success: persist batches, mark requests WRITTEN (write-once).
    now = datetime.now(timezone.utc)
    batch_ids = []
    for b in built:
        bid = _next_batch_id(db)
        db.add(Batch(id=bid, stream=stream, state="written", supplier=b["supplier"],
                     cart_url=b["link"], supplier_ref=str(b["ref"]),
                     item_count=b["items_count"], written_at=now))
        db.flush()
        batch_ids.append(bid)
    for r in requests:
        r.bucket_state = "WRITTEN"
    db.commit()
    # Restart this stream's countdown from now — a flush IS the timer's event,
    # so the clock has to reset here or the UI keeps counting toward a run that
    # already happened.
    mark_flushed(db, stream)

    log.info("flush %s: %d row(s) written (dry_run=%s), batches=%s", stream, sheet["written"], dry_run, batch_ids)
    return {"stream": stream, "dryRun": dry_run, "status": "written", "written": sheet["written"],
            "batches": batch_ids, "sheetMode": sheet["mode"],
            "suppliers": [{"supplier": b["supplier"], "ref": b["ref"], "total": b["total"],
                           "items": b["items_count"], "link": b["link"]} for b in built],
            "requests": [r.id for r in requests]}
