"""Josh's Daily Purchasing List writer (Purchasing v4.2).

Writes ONE row per supplier per batch to a fixed 14-column Excel table via
Microsoft Graph. HARD RULES (programmed in here):
- APPEND-ONLY: the only sheet op is appending rows (never edit/clear/delete).
- WRITE-ONCE: an entry already `WRITTEN` is never re-written.
- NO EMPTY ROWS: a cart with no share link or no cost is skipped entirely.
- GRACEFUL FALLBACK: when Graph isn't configured, log the rows to console.

The Phase 4 flush pipeline calls this with real carts (built by the cart/list
clients). Phase 2 builds + tests it via the console path.

The 14 columns are fixed and never reordered/renamed. AutoBOM writes only its
defined columns and leaves human-managed columns blank.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from config import settings
from integrations.microsoft_graph import get_client

log = logging.getLogger("autobom.purchasing.sheet")

# Column order (fixed). Index matches the 14-column table.
COLUMNS = ["Date", "Project", "Vendor", "Item", "Need", "Unit Price", "Quantity",
           "Total Cost", "Link to Product", "Urgency", "Requestor", "Status",
           "Purchase Date", "Long Link (alternative)"]

# Fixed write defaults (Admin-configurable later; temporary per v4.2 summary).
DEFAULT_PROJECT = "Other"
DEFAULT_NEED = "Component Purchasing"
DEFAULT_REQUESTOR = "Aaron Jones"


def _urgency(critical: bool) -> str:
    return "Next Day" if critical else "2-Day"


def _is_empty_cart(cart: dict) -> bool:
    """A row is written only when it carries real data (real cart w/ link + cost)."""
    share_link = str(cart.get("share_link", "")).strip()
    total = cart.get("cart_total")
    try:
        has_cost = total is not None and float(str(total)) > 0
    except (ValueError, TypeError):
        has_cost = False
    return not share_link or not has_cost or not cart.get("items_count", 1)


def build_row(cart: dict, *, written_at: datetime | None = None) -> list:
    """Build the 14 cells for one supplier's cart in a batch. CPN is NOT written
    to the sheet (it lives on the supplier cart line + internal state)."""
    ts = (written_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    unit_price = cart.get("cart_total")
    quantity = 1
    try:
        total_cost = round(float(str(unit_price)) * quantity, 2)
    except (ValueError, TypeError):
        total_cost = unit_price
    return [
        ts,                                    # 1 Date (write timestamp)
        DEFAULT_PROJECT,                       # 2 Project
        cart.get("supplier", ""),              # 3 Vendor (Mouser/DigiKey)
        cart.get("category", ""),              # 4 Item (category label)
        DEFAULT_NEED,                          # 5 Need
        unit_price,                            # 6 Unit Price (cart total)
        quantity,                              # 7 Quantity = 1
        total_cost,                            # 8 Total Cost
        cart.get("share_link", ""),            # 9 Link to Product (cart share link)
        _urgency(bool(cart.get("critical"))),  # 10 Urgency
        DEFAULT_REQUESTOR,                     # 11 Requestor
        "",                                    # 12 Status (blank, buyer-managed)
        "",                                    # 13 Purchase Date (blank)
        "",                                    # 14 Long Link (blank)
    ]


def write_batch(carts: list[dict]) -> dict:
    """Append one row per non-empty, not-yet-written cart. Returns a summary.

    Each cart: {supplier, category, cart_total, share_link, critical, items_count,
                entry_id?, bucket_state?}.
    """
    written_at = datetime.now()
    rows, skipped = [], []
    for cart in carts:
        if str(cart.get("bucket_state", "")).upper() == "WRITTEN":
            skipped.append({"entry_id": cart.get("entry_id"), "reason": "already WRITTEN (write-once)"})
            continue
        if _is_empty_cart(cart):
            skipped.append({"entry_id": cart.get("entry_id"), "reason": "empty cart (no link/cost) — skipped"})
            continue
        rows.append(build_row(cart, written_at=written_at))

    if not rows:
        log.info("Purchasing sheet: nothing to write (0 rows; %d skipped).", len(skipped))
        return {"mode": "none", "written": 0, "skipped": skipped, "rows": []}

    client = get_client() if settings.graph_enabled else None
    if client is None:
        # Graceful fallback — show exactly what WOULD be written.
        log.info("[PURCHASING SHEET — console fallback] %d row(s):", len(rows))
        for row in rows:
            log.info("  %s", dict(zip(COLUMNS, row)))
        return {"mode": "console", "written": len(rows), "skipped": skipped, "rows": rows}

    # Live Graph append — atomic within a workbook session (all-or-nothing).
    item_id = os.getenv("ONEDRIVE_PURCHASING_SHEET_ID", "").strip()
    drive_id = os.getenv("ONEDRIVE_DRIVE_ID", "").strip() or None
    table = os.getenv("ONEDRIVE_PURCHASING_TABLE", "PurchasingList").strip()
    session_id = client.excel_create_session(item_id, drive_id=drive_id)
    try:
        client.excel_add_table_rows(item_id, table, rows, session_id=session_id, drive_id=drive_id)
    finally:
        client.excel_close_session(item_id, session_id, drive_id=drive_id)
    log.info("Purchasing sheet: appended %d row(s) via Graph.", len(rows))
    return {"mode": "graph", "written": len(rows), "skipped": skipped, "rows": rows}
