"""Auth flow — seed login, effective caps, role switch, logout, graceful fallback.

These go through the real FastAPI app + TestClient, so seed data must be
committed (the app opens its own sessions). clean_schema (autouse) drops tables
after each test.
"""

import pytest
from fastapi.testclient import TestClient

from app.factory import app
from db.seed import seed_all
from db.session import SessionLocal


@pytest.fixture
def seeded():
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


def test_login_mode_is_seed_with_three_users(seeded, client):
    r = client.get("/api/auth/login")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "seed"
    assert len(body["users"]) == 3
    assert {u["role"] for u in body["users"]} == {"designer", "production", "admin"}


def test_seed_login_success_and_me(seeded, client):
    r = client.post("/api/auth/login", json={"email": "aaron.jones@yanktech.com"})
    assert r.status_code == 200, r.text
    user = r.json()
    assert user["id"] == "u-aaron"
    assert user["roles"] == ["designer"]
    assert user["activeRole"] == "designer"
    # effective caps from the designer role
    assert "collection.create" in user["caps"]

    me = client.get("/api/auth/me").json()
    assert me["user"]["id"] == "u-aaron"
    assert me["auth_mode"] == "seed-users"


def test_login_unknown_email_rejected(seeded, client):
    r = client.post("/api/auth/login", json={"email": "nobody@yanktech.com"})
    assert r.status_code == 401
    assert "recognize" in r.json()["detail"].lower()


def test_login_inactive_user_rejected(seeded, client):
    r = client.post("/api/auth/login", json={"email": "quinn.a@yanktech.com"})
    assert r.status_code == 401
    assert "deactivated" in r.json()["detail"].lower()


def test_inert_user_is_not_a_login_account(seeded, client):
    # David exists as referential data but has no role -> not a login account.
    r = client.post("/api/auth/login", json={"email": "david.okafor@yanktech.com"})
    assert r.status_code == 401
    assert "login account" in r.json()["detail"].lower()


def test_role_switch_scoped_to_held_roles(seeded, client):
    client.post("/api/auth/login", json={"email": "aaron.jones@yanktech.com"})
    # Aaron holds only 'designer' now -> cannot switch to production.
    bad = client.post("/api/auth/role", json={"role": "production"})
    assert bad.status_code == 403
    ok = client.post("/api/auth/role", json={"role": "designer"})
    assert ok.status_code == 200
    assert ok.json()["activeRole"] == "designer"


def test_logout_clears_session(seeded, client):
    client.post("/api/auth/login", json={"email": "grace.hill@yanktech.com"})
    assert client.get("/api/auth/me").json()["user"]["id"] == "u-grace"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["user"] is None


def test_admin_caps(seeded, client):
    r = client.post("/api/auth/login", json={"email": "grace.hill@yanktech.com"})
    assert "admin.users" in r.json()["caps"]
    assert r.json()["roleSource"] == "seed"
