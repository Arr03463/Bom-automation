"""A failed sheet write must not orphan a cart that already exists.

The supplier side of a flush is NOT rollback-able: by the time the sheet write
runs, the Mouser cart and DigiKey list have already been created. The early
return on a partial write persisted nothing, so a real cart was left with no
Batch row, no supplier_ref, and no way to find it — and the next flush built
another one for the same requests.

This can't happen while Graph is unconfigured (the console fallback always
succeeds); it becomes reachable the moment the real workbook is attached.
"""

import pytest

from db.models import Batch, Bom, BomLine, Project, Request, User
from services import bucket_flush


@pytest.fixture
def queued(db):
    db.add(User(id="u-x", name="X", email="x@y.com", roles=["production"],
                primary_role="production", active=True))
    db.add(Project(id="p-1", name="P1", status="active"))
    db.flush()
    db.add(Bom(id="B-1", project_id="p-1", name="B1", version=1, state="submitted",
               build_qty=1, overage=0))
    db.flush()
    db.add(BomLine(bom_id="B-1", line_no=1, mpn="MPN-A", mfr="Acme", qty=5,
                   status="sourced-mouser", supplier="mouser", supplier_pn="M-1"))
    db.add(Request(id="REQ-1", kind="bom", source_id="B-1", title="t",
                   from_user_id="u-x", bucket_state="QUEUED_MAIN",
                   items_snapshot=[{"mpn": "MPN-A", "mfr": "Acme", "supplierPn": "M-1",
                                    "qty": 5, "status": "sourced-mouser",
                                    "supplier": "mouser", "ext": 12.5}]))
    db.flush()
    return db


def _stub_builders(monkeypatch, ref="CART-REAL-123"):
    """Pretend the supplier calls succeeded — a real cart now exists."""
    monkeypatch.setattr(bucket_flush, "_mouser_batch",
                        lambda df, reqs, dry: {"supplier": "Mouser", "ref": ref, "total": 12.5,
                                               "items_count": 1, "link": "https://x/cart", "raw": {}})
    monkeypatch.setattr(bucket_flush, "_digikey_batch", lambda df, reqs, dry, name: None)


def test_failed_sheet_write_still_records_the_created_cart(queued, monkeypatch):
    _stub_builders(monkeypatch)
    monkeypatch.setattr(bucket_flush, "write_batch",
                        lambda carts: {"written": 0, "skipped": ["boom"], "mode": "graph", "rows": []})
    out = bucket_flush.flush_stream(queued, "main", dry_run=False)

    assert out["status"] == "partial"
    batches = queued.query(Batch).all()
    assert len(batches) == 1, "the created cart was orphaned — no Batch row persisted"
    assert batches[0].supplier_ref == "CART-REAL-123"
    assert batches[0].state == "pending"          # not 'written': it never reached the sheet
    assert batches[0].written_at is None
    # the ref must reach the caller too, so a human can find the cart
    assert out["suppliers"][0]["ref"] == "CART-REAL-123"
    assert "already created" in out["message"]


def test_requests_stay_queued_so_the_row_can_still_be_written(queued, monkeypatch):
    _stub_builders(monkeypatch)
    monkeypatch.setattr(bucket_flush, "write_batch",
                        lambda carts: {"written": 0, "skipped": ["boom"], "mode": "graph", "rows": []})
    bucket_flush.flush_stream(queued, "main", dry_run=False)
    assert queued.get(Request, "REQ-1").bucket_state == "QUEUED_MAIN"


def test_successful_write_marks_written_and_stamps_the_time(queued, monkeypatch):
    _stub_builders(monkeypatch)
    monkeypatch.setattr(bucket_flush, "write_batch",
                        lambda carts: {"written": len(carts), "skipped": [], "mode": "console", "rows": []})
    out = bucket_flush.flush_stream(queued, "main", dry_run=False)

    assert out["status"] == "written"
    assert queued.get(Request, "REQ-1").bucket_state == "WRITTEN"
    b = queued.query(Batch).all()[0]
    assert b.state == "written" and b.written_at is not None


def test_cart_creation_does_not_depend_on_graph_being_configured(queued, monkeypatch):
    """The reported expectation: no OneDrive sheet yet must NOT stop the flush
    from building the cart/list. The sheet writer's console fallback is a
    successful write, so the batch completes normally."""
    calls = {}
    monkeypatch.setattr(bucket_flush, "_mouser_batch",
                        lambda df, reqs, dry: calls.setdefault("mouser", True) and None
                        or {"supplier": "Mouser", "ref": "C1", "total": 12.5,
                            "items_count": 1, "link": "https://x/cart", "raw": {}})
    monkeypatch.setattr(bucket_flush, "_digikey_batch", lambda df, reqs, dry, name: None)
    monkeypatch.setattr(bucket_flush, "write_batch",
                        lambda carts: {"written": len(carts), "skipped": [], "mode": "console", "rows": []})
    out = bucket_flush.flush_stream(queued, "main", dry_run=False)
    assert calls.get("mouser") is True, "cart builder was never called"
    assert out["status"] == "written" and out["sheetMode"] == "console"
