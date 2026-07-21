"""Phase 4: the sourceability gate (root-cause fix) + flush mapping + sheet links."""

from services.bucket_flush import DIGIKEY_LIST_URL, MOUSER_CART_URL
from services.flush_mapping import from_snapshot_line, requests_to_dataframe
from services.sourcing_engine import decide_no_split_supplier, sourceable
from services.supplier_base import SupplierResult


def _res(**kw):
    base = dict(supplier="Mouser", manufacturer="M", mpn="X", stock=1000,
                unit_price="1.50", supplier_part_number="M-1", lifecycle_status="Active")
    base.update(kw)
    return SupplierResult(**base)


# --- sourceability gate: unavailable/$0/obsolete is a SOURCING FAILURE --------
def test_good_part_is_sourceable():
    ok, why = sourceable(_res(), 10)
    assert ok and why == ""


def test_zero_price_is_not_sourceable():
    ok, why = sourceable(_res(unit_price="0"), 10)
    assert not ok and "price" in why


def test_missing_price_is_not_sourceable():
    ok, why = sourceable(_res(unit_price=""), 10)
    assert not ok


def test_obsolete_is_not_sourceable_even_with_stock():
    ok, why = sourceable(_res(stock=9999, lifecycle_status="Obsolete"), 10)
    assert not ok and "lifecycle" in why


def test_not_available_note_is_not_sourceable():
    ok, why = sourceable(_res(notes="Not Available"), 10)
    assert not ok


def test_insufficient_stock_is_not_sourceable():
    ok, why = sourceable(_res(stock=5), 10)
    assert not ok and "insufficient stock" in why


def test_decision_flags_obsolete_instead_of_sourcing_it():
    """The exact bug the live probe exposed: stock present but $0 + Obsolete
    must NOT come back as sourced_* (it would have carted a $0 line)."""
    row = {"mpn": "X", "required_qty": 10, "qty_per_board": 1, "build_quantity": 10}
    dead = _res(stock=9999, unit_price="0", lifecycle_status="Obsolete")
    d = decide_no_split_supplier(row, dead, None)
    assert d["sourcing_status"] == "check_wall_inventory"
    assert "not sourceable" in d["sourcing_notes"].lower()


def test_digikey_fallback_when_mouser_unsourceable():
    row = {"mpn": "X", "required_qty": 10, "qty_per_board": 1, "build_quantity": 10}
    d = decide_no_split_supplier(row, _res(stock=0), _res(supplier="DigiKey", supplier_part_number="D-1"))
    assert d["sourcing_status"] == "sourced_digikey"


# --- flush mapping: both snapshot shapes, sourced-only ------------------------
def test_snapshot_accepts_camel_and_snake_supplier_pn():
    camel = from_snapshot_line({"mpn": "X", "mfr": "M", "supplierPn": "M-1", "qty": 5,
                                "status": "sourced-mouser", "supplier": "mouser"})
    snake = from_snapshot_line({"mpn": "X", "mfr": "M", "supplier_pn": "M-1", "qty": 5,
                                "status": "sourced-mouser", "supplier": "mouser"})
    assert camel and snake
    assert camel["sourcing_status"] == snake["sourcing_status"] == "sourced_mouser"
    assert camel["supplier_part_number"] == "M-1"


def test_unsourced_lines_never_flush():
    for status in ("needs-review", "check-wall", "normalised", "validated", ""):
        assert from_snapshot_line({"mpn": "X", "supplierPn": "M-1", "qty": 5,
                                   "status": status, "supplier": ""}) is None


def test_line_without_pn_or_qty_never_flushes():
    assert from_snapshot_line({"mpn": "X", "supplierPn": "", "qty": 5, "status": "sourced-mouser"}) is None
    assert from_snapshot_line({"mpn": "X", "supplierPn": "M-1", "qty": 0, "status": "sourced-mouser"}) is None


def test_requests_to_dataframe_groups_by_supplier():
    class R:
        items_snapshot = [
            {"mpn": "A", "supplierPn": "M-1", "qty": 2, "status": "sourced-mouser", "supplier": "mouser"},
            {"mpn": "B", "supplierPn": "D-1", "qty": 3, "status": "sourced-digikey", "supplier": "digikey"},
            {"mpn": "C", "supplierPn": "X", "qty": 1, "status": "needs-review", "supplier": ""},
        ]
    df = requests_to_dataframe([R()])
    assert len(df) == 2                                   # the needs-review line is dropped
    assert set(df.selected_supplier) == {"mouser", "digikey"}


# --- sheet links: per-batch deep link, never the API-URL form ----------------
# Verified live: ?cartKey= opens THAT cart; /mylists/list/<id> opens THAT list.
def test_links_are_account_deep_links_for_the_specific_batch():
    cart = MOUSER_CART_URL.format(cart_key="0c4b048b-8f43-4d0a-aefb-da74ef73ad6b")
    lst = DIGIKEY_LIST_URL.format(list_id="N0FTSYUTRG")
    assert cart == "https://www.mouser.com/cart?cartKey=0c4b048b-8f43-4d0a-aefb-da74ef73ad6b"
    assert lst == "https://www.digikey.com/en/mylists/list/N0FTSYUTRG"
    assert cart.startswith("https://www.mouser.com/")     # account domain, not api.mouser.com
    assert lst.startswith("https://www.digikey.com/")


def test_sheet_links_never_carry_an_api_key():
    """HARD SECURITY LINE: the API-URL form (api.mouser.com/api/v1/cart?apiKey=…)
    must never be constructible from these templates — it would put the secret on
    Josh's sheet, which is shared."""
    for tmpl in (MOUSER_CART_URL, DIGIKEY_LIST_URL):
        low = tmpl.lower()
        assert "apikey" not in low
        assert "api." not in low
        assert "/api/" not in low
