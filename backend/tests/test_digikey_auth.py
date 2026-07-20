"""DigiKey token cache — the key guide refactor (10-min cache, 401 refresh)."""

import responses

from services import digikey_auth
from services.digikey_auth import get_auth, reset_auth

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"


def _env(monkeypatch):
    monkeypatch.setenv("SUPPLIER_DRY_RUN", "false")
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "cid")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DIGIKEY_TOKEN_URL", TOKEN_URL)
    monkeypatch.setenv("DIGIKEY_BASE_URL", "https://api.digikey.com")
    reset_auth()


@responses.activate
def test_token_is_cached_not_refetched(monkeypatch):
    _env(monkeypatch)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "T1", "expires_in": 600}, status=200)
    auth = get_auth()
    assert auth.token() == "T1"
    assert auth.token() == "T1"          # cached
    assert len(responses.calls) == 1     # only ONE token fetch for two token() calls


@responses.activate
def test_force_refresh_refetches(monkeypatch):
    _env(monkeypatch)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "T1", "expires_in": 600}, status=200)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "T2", "expires_in": 600}, status=200)
    auth = get_auth()
    assert auth.token() == "T1"
    assert auth.token(force_refresh=True) == "T2"   # e.g. after a 401
    assert len(responses.calls) == 2


@responses.activate
def test_expired_token_refreshes(monkeypatch):
    _env(monkeypatch)
    # expires_in tiny -> next token() sees it as expired (refresh 30s before expiry).
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "T1", "expires_in": 1}, status=200)
    responses.add(responses.POST, TOKEN_URL, json={"access_token": "T2", "expires_in": 600}, status=200)
    auth = get_auth()
    assert auth.token() == "T1"
    assert auth.token() == "T2"          # expired (1s < 30s guard) -> refetch
    assert len(responses.calls) == 2


def test_sandbox_env_selects_sandbox_host(monkeypatch):
    monkeypatch.delenv("DIGIKEY_BASE_URL", raising=False)
    monkeypatch.setenv("DIGIKEY_ENV", "sandbox")
    reset_auth()
    assert "sandbox-api.digikey.com" in digikey_auth._host()
