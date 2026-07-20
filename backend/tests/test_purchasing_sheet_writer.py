"""Purchasing sheet writer — 14-col contract, write-once, no empty rows,
append-only, console fallback, and CPN never on the sheet."""

import pytest

from services import purchasing_sheet_writer as psw


def _cart(**kw):
    base = {"supplier": "Mouser", "category": "Resistors", "cart_total": 12.50,
            "share_link": "https://mouser/cart/abc", "critical": False, "items_count": 3}
    base.update(kw)
    return base


def test_build_row_shape_and_defaults():
    row = psw.build_row(_cart(critical=True))
    assert len(row) == 14
    assert row[1] == "Other"                  # Project
    assert row[2] == "Mouser"                 # Vendor
    assert row[4] == "Component Purchasing"   # Need
    assert row[5] == 12.50                    # Unit Price = cart total
    assert row[6] == 1                        # Quantity
    assert row[7] == 12.50                    # Total Cost = price * 1
    assert row[8] == "https://mouser/cart/abc"  # Link to Product (share link)
    assert row[9] == "Next Day"               # Urgency (critical)
    assert row[10] == "Aaron Jones"           # Requestor
    assert row[11] == "" and row[12] == "" and row[13] == ""  # Status/PurchaseDate/LongLink blank


def test_cpn_is_never_written_to_the_sheet():
    row = psw.build_row(_cart(cpn="TVCA-R2-042"))
    assert "TVCA-R2-042" not in row           # CPN lives on the cart line, not the sheet


def test_console_fallback_writes_non_empty_and_skips_empty(monkeypatch):
    monkeypatch.setattr(psw.settings, "graph_enabled", False, raising=False)
    carts = [
        _cart(entry_id="e1"),                                    # written
        _cart(entry_id="e2", share_link="", cart_total=0),       # empty -> skipped
        _cart(entry_id="e3", bucket_state="WRITTEN"),            # write-once -> skipped
    ]
    out = psw.write_batch(carts)
    assert out["mode"] == "console"
    assert out["written"] == 1
    reasons = " ".join(s["reason"] for s in out["skipped"])
    assert "empty cart" in reasons and "already WRITTEN" in reasons


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def excel_create_session(self, item_id, drive_id=None):
        self.calls.append("create_session"); return "sid"

    def excel_add_table_rows(self, item_id, table, rows, session_id=None, drive_id=None):
        self.calls.append("add_table_rows"); return {"rowsAdded": len(rows)}

    def excel_close_session(self, item_id, session_id, drive_id=None):
        self.calls.append("close_session")


def test_graph_path_is_append_only(monkeypatch):
    """The live path uses ONLY session + rows/add + close — never update/clear/delete."""
    monkeypatch.setattr(psw.settings, "graph_enabled", True, raising=False)
    rec = _RecordingClient()
    monkeypatch.setattr(psw, "get_client", lambda: rec)
    out = psw.write_batch([_cart(entry_id="e1"), _cart(entry_id="e2", supplier="DigiKey")])
    assert out["mode"] == "graph" and out["written"] == 2
    # Exactly the append lifecycle; no mutating ops exist on the client at all.
    assert rec.calls == ["create_session", "add_table_rows", "close_session"]
