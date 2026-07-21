"""Regressions for the two flow-breakers the Phase 4 dress rehearsal found.

1. A bad enum string was written to the DB unvalidated and then raised
   LookupError on every read. Because /api/bootstrap reads pushbacks on login,
   ONE bad row bricked the whole app for every user.
2. Both halves of the Designer->Production handshake selected the open
   push-back with `.first()` and NO ORDER BY, so with more than one open
   push-back the recommendation and the apply could target different rows.
"""

import pytest
from sqlalchemy.exc import StatementError

from api.entities import _enum_val, _open_pushback
from db.models import Bom, Project, Pushback, PushbackUrgency, User


def _fixture(db):
    # Flush between groups: these carry FKs to each other, and a single batched
    # INSERT does not guarantee parent-before-child ordering.
    db.add(User(id="u-x", name="X", email="x@y.com", roles=["production"],
                primary_role="production", active=True))
    db.add(Project(id="p-1", name="P1", status="active"))
    db.flush()
    db.add(Bom(id="B-1", project_id="p-1", name="B1", version=1, state="validated",
               build_qty=1, overage=0))
    db.flush()


def _pb(pid, **kw):
    base = dict(id=pid, bom_id="B-1", reason="unsourceable", urgency="standard",
                from_user_id="u-x", state="open", loop=1, flagged_lines=[])
    base.update(kw)
    return Pushback(**base)


# --- 1. a bad enum value must never reach the database ----------------------
def test_bad_enum_value_is_rejected_at_write_not_silently_stored(db):
    """The bug: this INSERT used to succeed, and every later SELECT raised
    LookupError -> /api/bootstrap 500 -> nobody can log in."""
    _fixture(db)
    db.add(_pb("PB-1", urgency="Standard"))          # Title Case is NOT a value
    with pytest.raises(StatementError):
        db.flush()


def test_valid_enum_values_still_write(db):
    _fixture(db)
    db.add(_pb("PB-1", urgency="standard"))
    db.add(_pb("PB-2", urgency="blocking"))
    db.flush()
    assert db.query(Pushback).count() == 2


# --- 2. the API boundary coerces/rejects before it ever reaches the DB ------
def test_enum_val_accepts_exact_value():
    assert _enum_val("blocking", PushbackUrgency, "standard") == "blocking"


def test_enum_val_coerces_ui_title_case():
    """UI labels are Title Case ("Standard"); stored values are lower."""
    assert _enum_val("Standard", PushbackUrgency, "standard") == "standard"
    assert _enum_val("BLOCKING", PushbackUrgency, "standard") == "blocking"


def test_enum_val_defaults_on_empty():
    for empty in (None, "", "   "):
        assert _enum_val(empty, PushbackUrgency, "standard") == "standard"


def test_enum_val_rejects_garbage_as_400_not_500():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _enum_val("NOT_A_VALUE", PushbackUrgency, "standard")
    assert exc.value.status_code == 400
    assert "blocking" in str(exc.value.detail)      # names the allowed values


# --- 3. the handshake targets ONE deterministic push-back -------------------
def test_selection_is_deterministic_across_multiple_open_pushbacks(db):
    """Unordered .first() made this a coin flip: Designer's recommendation
    could attach to PB-1 while Production's Apply read PB-3."""
    _fixture(db)
    for pid in ("PB-3", "PB-1", "PB-2"):            # inserted out of order
        db.add(_pb(pid))
    db.flush()
    picked = {_open_pushback(db, "B-1").id for _ in range(5)}
    assert picked == {"PB-1"}                        # oldest, every time


def test_apply_targets_the_pushback_that_carries_the_recommendation(db):
    """The exact rehearsal failure: recommendation on PB-1, but apply read a
    different open row and returned 'No recommendation to apply.'"""
    _fixture(db)
    db.add(_pb("PB-1", recommendation={"picks": [{"lineNo": 1, "mpn": "NEW"}]}))
    db.add(_pb("PB-2"))
    db.add(_pb("PB-3"))
    db.flush()
    pb = _open_pushback(db, "B-1", with_recommendation=True)
    assert pb.id == "PB-1" and pb.recommendation["picks"][0]["mpn"] == "NEW"


def test_explicit_pushback_id_wins(db):
    _fixture(db)
    db.add(_pb("PB-1"))
    db.add(_pb("PB-2"))
    db.flush()
    assert _open_pushback(db, "B-1", pushback_id="PB-2").id == "PB-2"


def test_resolved_pushbacks_are_never_selected(db):
    _fixture(db)
    db.add(_pb("PB-1", state="resolved", recommendation={"picks": []}))
    db.add(_pb("PB-2"))
    db.flush()
    assert _open_pushback(db, "B-1").id == "PB-2"
    assert _open_pushback(db, "B-1", with_recommendation=True) is None
