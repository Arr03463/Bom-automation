"""Models — CRUD round-trip, FK enforcement, uniqueness, the pushback linkage."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import (
    Bom, BomLine, BomVersion, ForceWaiver, Program, Project, Pushback, User,
)


def _user(db, uid="u-x", email="x@yanktech.com", roles=("designer",)):
    u = User(id=uid, name="X", email=email, roles=list(roles), primary_role=roles[0] if roles else None)
    db.add(u); db.flush()
    return u


def _project(db, pid="p1"):
    db.add(Program(id="prog1", name="Prog")); db.flush()
    db.add(Project(id=pid, name="Proj", program_id="prog1")); db.flush()
    return pid


def test_crud_roundtrip(db):
    _user(db)
    pid = _project(db)
    db.add(Bom(id="B1", name="BOM", project_id=pid, state="draft", version=1))
    db.flush()
    db.add(BomLine(bom_id="B1", line_no=1, mpn="STM32", qty=10, status="validated"))
    db.commit()

    bom = db.get(Bom, "B1")
    assert bom.name == "BOM" and bom.version == 1
    assert len(bom.lines) == 1 and bom.lines[0].mpn == "STM32"


def test_fk_enforced_bom_needs_real_project(db):
    with pytest.raises(IntegrityError):
        db.add(Bom(id="B2", name="orphan", project_id="does-not-exist", state="draft", version=1))
        db.flush()


def test_unique_email(db):
    _user(db, uid="u-a", email="dup@yanktech.com")
    with pytest.raises(IntegrityError):
        _user(db, uid="u-b", email="dup@yanktech.com")


def test_one_master_bom_per_project(db):
    _user(db)
    pid = _project(db)
    db.add(Bom(id="B1", name="first", project_id=pid, state="draft", version=1)); db.flush()
    with pytest.raises(IntegrityError):
        db.add(Bom(id="B2", name="second", project_id=pid, state="draft", version=1))
        db.flush()


def test_force_waiver_reason_min_length(db):
    with pytest.raises(IntegrityError):
        db.add(ForceWaiver(id="fw1", reason="short", ts=datetime.now(timezone.utc)))
        db.flush()


def test_pushback_links_to_bom_version(db):
    _user(db)
    pid = _project(db)
    db.add(Bom(id="B1", name="BOM", project_id=pid, state="exceptions", version=1)); db.flush()
    db.add(BomVersion(id="V2", bom_id="B1", version=2, reason={"applied_recommendation": {"mpn": "IPB014N06N"}},
                      ts=datetime.now(timezone.utc))); db.flush()
    db.add(Pushback(id="PB1", bom_id="B1", reason="eol", urgency="blocking", state="resolved",
                    resolved_at_version_id="V2")); db.commit()

    pb = db.get(Pushback, "PB1")
    assert pb.resolved_at_version_id == "V2"
    ver = db.get(BomVersion, "V2")
    assert ver.reason["applied_recommendation"]["mpn"] == "IPB014N06N"
