"""Build overlay -> PartsBox consumption, and the push-back gate.

These matter more than most: an error here silently decrements REAL stock in
PartsBox, which is not cheaply reversible.
"""

import pytest

from db.models import Bom, BomLine, Project, Pushback, User
from services.build_service import (
    BuildGateError, build_gate, consumption_plan,
)


class _Bom:
    def __init__(self, build_qty=10, version=1, name="B"):
        self.build_qty, self.version, self.name = build_qty, version, name
        self.id, self.project_id = "B-1", "p-1"


def _line(no, mpn="MPN-A", qty=10, mfr="Acme"):
    li = BomLine(bom_id="B-1", line_no=no, mpn=mpn, mfr=mfr, qty=qty)
    return li


# --- overlay semantics ------------------------------------------------------
def test_default_state_is_used_and_consumes():
    plan = consumption_plan(_Bom(), [_line(1)], {}, 10)
    assert plan["summary"]["consumed"] == 1
    assert plan["consume"][0] == {"lineNo": 1, "mpn": "MPN-A", "mfr": "Acme",
                                  "qty": 10, "state": "used"}


def test_skipped_and_deferred_never_consume():
    """CLAUDE.md: skipped omits the line; deferred defers to a future rework.
    Neither may decrement stock now."""
    plan = consumption_plan(_Bom(), [_line(1), _line(2), _line(3)],
                            {"2": {"state": "skipped"}, "3": {"state": "deferred"}}, 10)
    assert [e["lineNo"] for e in plan["consume"]] == [1]
    assert plan["summary"]["skipped"] == 1 and plan["summary"]["deferred"] == 1
    assert plan["summary"]["units"] == 10


def test_rework_consumes_the_substitute_not_the_master_part():
    """The whole point of rework: PartsBox consumes what was ACTUALLY fitted."""
    plan = consumption_plan(_Bom(), [_line(1, mpn="ORIGINAL")],
                            {"1": {"state": "rework", "mpn": "SUBSTITUTE",
                                   "mfr": "Other", "reworkType": "realtime"}}, 10)
    e = plan["consume"][0]
    assert e["mpn"] == "SUBSTITUTE" and e["mfr"] == "Other"
    assert e["replaces"] == {"mpn": "ORIGINAL", "mfr": "Acme"}
    assert plan["summary"]["rework"] == 1


def test_rework_without_a_substitute_mpn_is_rejected():
    with pytest.raises(ValueError, match="substitute MPN"):
        consumption_plan(_Bom(), [_line(1)], {"1": {"state": "rework"}}, 10)


def test_invalid_overlay_state_is_rejected():
    with pytest.raises(ValueError, match="invalid overlay state"):
        consumption_plan(_Bom(), [_line(1)], {"1": {"state": "installed"}}, 10)


def test_invalid_rework_type_is_rejected():
    with pytest.raises(ValueError, match="realtime or post_hoc"):
        consumption_plan(_Bom(), [_line(1)],
                         {"1": {"state": "rework", "mpn": "X", "reworkType": "later"}}, 10)


def test_overlay_accepts_int_or_string_line_keys():
    for key in (1, "1"):
        plan = consumption_plan(_Bom(), [_line(1)], {key: {"state": "skipped"}}, 10)
        assert plan["summary"]["consumed"] == 0, f"key {key!r} not honored"


# --- quantity scaling -------------------------------------------------------
def test_same_build_qty_uses_stored_qty_verbatim():
    """BomLine.qty is already the total for the BOM's build_qty; when the build
    matches, do no arithmetic at all."""
    plan = consumption_plan(_Bom(build_qty=10), [_line(1, qty=80)], {}, 10)
    assert plan["consume"][0]["qty"] == 80
    assert plan["warnings"] == []


def test_scales_down_for_a_smaller_build():
    plan = consumption_plan(_Bom(build_qty=10), [_line(1, qty=80)], {}, 5)
    assert plan["consume"][0]["qty"] == 40


def test_non_integral_per_board_qty_is_flagged_not_silently_rounded():
    # 25 over a build of 10 = 2.5/board -> rounding up must be visible.
    plan = consumption_plan(_Bom(build_qty=10), [_line(1, qty=25)], {}, 4)
    assert plan["consume"][0]["qty"] == 10
    assert any("not a whole per-board quantity" in w for w in plan["warnings"])


def test_explicit_overlay_qty_wins():
    plan = consumption_plan(_Bom(build_qty=10), [_line(1, qty=80)], {"1": {"qty": 3}}, 10)
    assert plan["consume"][0]["qty"] == 3


def test_zero_qty_line_is_warned_and_not_consumed():
    plan = consumption_plan(_Bom(), [_line(1, qty=0)], {}, 10)
    assert plan["consume"] == []
    assert any("not consumed" in w for w in plan["warnings"])


# --- the push-back gate -----------------------------------------------------
def _gate_fixture(db, pb_state=None):
    db.add(User(id="u-x", name="X", email="x@y.com", roles=["production"],
                primary_role="production", active=True))
    db.add(Project(id="p-1", name="P1", status="active"))
    db.flush()
    db.add(Bom(id="B-1", project_id="p-1", name="B1", version=1, state="validated",
               build_qty=10, overage=0))
    db.flush()
    if pb_state:
        db.add(Pushback(id="PB-1", bom_id="B-1", reason="unsourceable", urgency="standard",
                        from_user_id="u-x", state=pb_state, loop=1, flagged_lines=[]))
        db.flush()


def test_build_allowed_when_no_open_pushback(db):
    _gate_fixture(db)
    assert build_gate(db, "B-1")["allowed"] is True


def test_build_blocked_by_an_open_pushback(db):
    """Hard rule: Run Build is gated while any push-back is unresolved."""
    _gate_fixture(db, pb_state="open")
    with pytest.raises(BuildGateError, match="blocked"):
        build_gate(db, "B-1")


def test_resolved_pushback_does_not_block(db):
    _gate_fixture(db, pb_state="resolved")
    assert build_gate(db, "B-1")["allowed"] is True


def test_force_waive_overrides_with_a_reason(db):
    _gate_fixture(db, pb_state="open")
    g = build_gate(db, "B-1", force_waive_reason="Customer ship date, risk accepted by lead")
    assert g["allowed"] and g["waived"] and g["blockedBy"] == ["PB-1"]


def test_force_waive_requires_a_substantive_reason(db):
    """Bounded Admin Authority: overrides carry a real audit reason."""
    _gate_fixture(db, pb_state="open")
    with pytest.raises(BuildGateError, match="at least 10 characters"):
        build_gate(db, "B-1", force_waive_reason="ok")


# --- QR delivery: ask PartsBox, never generate ------------------------------
def test_qr_url_comes_from_partsbox_and_is_configurable(monkeypatch):
    """API-leverage tenet: AutoBOM must not build a QR generator. The exact
    ID-Anything path is UNVERIFIED (the committed PartsBox PDF is a corrupted
    export), so the template is env-overridable rather than hard-coded."""
    from services.partsbox_client import PartsBoxClient
    c = PartsBoxClient()
    assert "{id}" not in c.build_qr_image_url("BID123")
    assert "BID123" in c.build_qr_image_url("BID123")
    monkeypatch.setenv("PARTSBOX_QR_URL_TEMPLATE", "https://x.test/q/{id}.png")
    assert c.build_qr_image_url("BID123") == "https://x.test/q/BID123.png"


def test_qr_and_web_url_are_none_without_a_build_id():
    """A dry run returns no build id; callers must fall back cleanly."""
    from services.partsbox_client import PartsBoxClient
    c = PartsBoxClient()
    assert c.build_qr_image_url(None) is None
    assert c.build_web_url(None) is None


def test_build_create_is_gated_by_the_partsbox_dry_run_flag(monkeypatch):
    """build/create decrements REAL stock - it must honor PARTSBOX_DRY_RUN like
    every other write, and echo the payload back for an honest preview."""
    from services.partsbox_client import PartsBoxClient
    monkeypatch.setenv("PARTSBOX_DRY_RUN", "true")
    monkeypatch.setenv("PARTSBOX_API_KEY", "test-key")
    c = PartsBoxClient()
    out = c.create_build("proj-1", 2, [{"mpn": "A", "mfr": "Acme", "qty": 4}])
    assert out["dry_run"] is True and out["operation"] == "build/create"
    assert out["payload"]["build/entries"] == [
        {"part/mpn": "A", "part/manufacturer": "Acme", "build/quantity": 4}]
