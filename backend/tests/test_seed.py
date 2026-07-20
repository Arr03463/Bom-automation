"""Seed — content, the three-login-user role model, and idempotency."""

from db.models import (
    Audit, Bom, BomLine, Collection, Configuration, Notification, Program,
    Project, Pushback, Request, Supplier, User, VALID_ROLES,
)
from db.seed import seed_all


def test_seed_loads_expected_ids(db):
    seed_all(db)
    assert db.get(User, "u-aaron") is not None
    assert db.get(Program, "terra-voyager") is not None
    assert db.get(Project, "tvca-rev2") is not None
    assert db.get(Collection, "COL-031") is not None
    assert db.get(Bom, "BOM-052") is not None
    assert db.get(Request, "REQ-018") is not None


def test_exactly_three_login_users_one_per_role(db):
    seed_all(db)
    login = [u for u in db.query(User).all() if (u.roles or [])]
    assert len(login) == 3
    by_role = {u.roles[0]: u.id for u in login}
    assert by_role == {"designer": "u-aaron", "production": "u-maria", "admin": "u-grace"}
    # each login user holds exactly one role
    assert all(len(u.roles) == 1 for u in login)


def test_no_legacy_role_strings_anywhere(db):
    seed_all(db)
    for u in db.query(User).all():
        for r in (u.roles or []):
            assert r in VALID_ROLES, f"legacy/invalid role {r!r} on {u.id}"
            assert r != "development"  # deferred; not seeded as a login role


def test_inert_users_are_referential_not_login(db):
    seed_all(db)
    # David/Sara/Noah/etc. exist for FK/actor resolution but carry no roles.
    for uid in ("u-david", "u-sara", "u-noah", "u-ava", "u-priya"):
        u = db.get(User, uid)
        assert u is not None
        assert (u.roles or []) == []


def test_pushback_and_actor_references_preserved(db):
    seed_all(db)
    pb = db.get(Pushback, "PB-052")
    assert pb.bom_id == "BOM-052" and pb.reason == "eol" and pb.urgency == "blocking"
    assert pb.from_user_id == "u-maria" and pb.to_user_id == "u-aaron"
    assert len(pb.flagged_lines) == 3
    # BOM-052 owner reference untouched (Aaron), demo "looks alive"
    assert db.get(Bom, "BOM-052").owner_id == "u-aaron"


def test_seed_is_idempotent(db):
    seed_all(db)
    counts1 = {m.__name__: db.query(m).count() for m in
               (User, Program, Project, Collection, Bom, BomLine, Pushback, Request,
                Notification, Audit, Supplier, Configuration)}
    seed_all(db)  # run again
    counts2 = {m.__name__: db.query(m).count() for m in
               (User, Program, Project, Collection, Bom, BomLine, Pushback, Request,
                Notification, Audit, Supplier, Configuration)}
    assert counts1 == counts2, f"seed not idempotent: {counts1} != {counts2}"
