"""Sourcing decision (Mouser-then-DigiKey) + validate_mpn (B2 guard)."""

from services.supplier_base import SupplierResult
from services.sourcing_engine import decide_no_split_supplier, validate_mpn


def _row(**kw):
    base = {"mpn": "X", "manufacturer": "M", "required_qty": 100, "qty_per_board": 10, "build_quantity": 10}
    base.update(kw)
    return base


def _res(supplier, stock):
    return SupplierResult(supplier=supplier, manufacturer="M", mpn="X", stock=stock,
                          supplier_part_number=f"{supplier}-X", unit_price="0.10")


def test_mouser_covers_full_qty():
    d = decide_no_split_supplier(_row(), _res("Mouser", 500), _res("DigiKey", 500))
    assert d["selected_supplier"] == "Mouser"
    assert d["sourcing_status"] == "sourced_mouser"
    assert d["supplier_order_qty"] == 100      # qty_per_board(10) * build_quantity(10)


def test_digikey_fallback_when_mouser_short():
    d = decide_no_split_supplier(_row(), _res("Mouser", 5), _res("DigiKey", 500))
    assert d["selected_supplier"] == "DigiKey"
    assert d["sourcing_status"] == "sourced_digikey"


def test_check_wall_when_neither_covers():
    d = decide_no_split_supplier(_row(), _res("Mouser", 5), _res("DigiKey", 5))
    assert d["sourcing_status"] == "check_wall_inventory"


def test_manual_review_without_mpn():
    d = decide_no_split_supplier(_row(mpn=""), None, None)
    assert d["sourcing_status"] == "manual_review"


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def find_best_match(self, mpn, manufacturer="", required_qty=None):
        return self._result


def test_validate_mpn_found_at_a_supplier():
    out = validate_mpn("X", "M", mouser_client=_FakeClient(None),
                       digikey_client=_FakeClient(_res("DigiKey", 10)))
    assert out["valid"] is True
    assert out["sources"] == ["digikey"]
    assert out["digikey"]["supplier_part_number"] == "DigiKey-X"


def test_validate_mpn_not_found():
    out = validate_mpn("NOPE", "", mouser_client=_FakeClient(None), digikey_client=_FakeClient(None))
    assert out["valid"] is False
    assert out["sources"] == []
