"""3-legged (MyLists) token manager — the auto-refresh path.

These lock the three failure modes that previously forced a manual re-auth:
rotation races from per-request exchanges, a static token shadowing the
refresh path, and no reactive retry on a 401.
"""

import time

import pytest

from services import digikey_user_auth as ua


class _Resp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text or ""

    def json(self):
        return self._payload


@pytest.fixture
def auth(tmp_path, monkeypatch):
    """A fresh manager with .env and the token cache redirected into tmp."""
    env = tmp_path / ".env"
    env.write_text("DIGIKEY_REFRESH_TOKEN=refresh-v1\n")
    monkeypatch.setattr(ua, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ua, "TOKEN_CACHE_PATH", tmp_path / ".cache" / "tok.json")
    monkeypatch.setenv("SUPPLIER_DRY_RUN", "false")
    monkeypatch.setenv("DIGIKEY_REFRESH_TOKEN", "refresh-v1")
    monkeypatch.delenv("DIGIKEY_ACCESS_TOKEN", raising=False)
    ua.reset_user_auth()
    yield ua.DigiKeyUserAuth()
    ua.reset_user_auth()


def _stub(monkeypatch, responses):
    """Queue of responses; records how many exchanges actually happened."""
    calls = []

    def fake(method, url, **kw):
        calls.append(kw.get("data", {}).get("refresh_token"))
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(ua, "http_request", fake)
    return calls


# --- the rotation race: one exchange serves many calls ----------------------
def test_token_is_cached_not_re_exchanged_per_call(auth, monkeypatch):
    """The bug: exchanging per request burned a refresh-token rotation each
    time, and concurrent calls invalidated each other."""
    calls = _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800})])
    assert auth.token() == "at-1"
    for _ in range(5):
        assert auth.token() == "at-1"
    assert len(calls) == 1


def test_rotated_refresh_token_is_persisted_to_env(auth, monkeypatch, tmp_path):
    _stub(monkeypatch, [_Resp({"access_token": "at-1", "refresh_token": "refresh-v2",
                               "expires_in": 1800})])
    auth.token()
    assert "DIGIKEY_REFRESH_TOKEN=refresh-v2" in (tmp_path / ".env").read_text()


def test_persist_appends_when_key_absent(monkeypatch, tmp_path):
    """The old helper silently no-op'd on a missing key — that drops a rotation
    and locks the account out of MyLists entirely."""
    monkeypatch.setattr(ua, "REPO_ROOT", tmp_path)
    (tmp_path / ".env").write_text("OTHER=1\n")
    assert ua.persist_refresh_token("refresh-v9") is True
    assert "DIGIKEY_REFRESH_TOKEN=refresh-v9" in (tmp_path / ".env").read_text()


def test_expiry_triggers_a_refresh(auth, monkeypatch):
    calls = _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800}),
                                _Resp({"access_token": "at-2", "expires_in": 1800})])
    assert auth.token() == "at-1"
    auth._expires_at = time.time() + 5          # inside the early-refresh window
    assert auth.token() == "at-2"
    assert len(calls) == 2


def test_force_refresh_bypasses_the_cache(auth, monkeypatch):
    """Backs the reactive 401 retry in DigiKeyMyListsClient._request."""
    _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800}),
                        _Resp({"access_token": "at-2", "expires_in": 1800})])
    assert auth.token() == "at-1"
    assert auth.token(force_refresh=True) == "at-2"


def test_invalidate_forces_the_next_call_to_re_exchange(auth, monkeypatch):
    _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800}),
                        _Resp({"access_token": "at-2", "expires_in": 1800})])
    auth.token()
    auth.invalidate()
    assert auth.token() == "at-2"


# --- static token must never shadow the self-healing path -------------------
def test_static_token_is_ignored_when_a_refresh_token_exists(auth, monkeypatch):
    """DIGIKEY_ACCESS_TOKEN used to be returned forever with no expiry check, so
    once it aged out every call 401'd and the refresh path was never tried."""
    monkeypatch.setenv("DIGIKEY_ACCESS_TOKEN", "stale-static-token")
    _stub(monkeypatch, [_Resp({"access_token": "at-fresh", "expires_in": 1800})])
    assert auth.token() == "at-fresh"


def test_static_token_used_only_as_a_last_resort(auth, monkeypatch):
    monkeypatch.setenv("DIGIKEY_ACCESS_TOKEN", "manual-token")
    monkeypatch.setenv("DIGIKEY_REFRESH_TOKEN", "")
    assert auth.token() == "manual-token"


# --- failure surfaces are actionable ----------------------------------------
def test_dead_refresh_token_gives_an_actionable_error(auth, monkeypatch):
    _stub(monkeypatch, [_Resp({}, status=400, text='{"error":"invalid_grant"}')])
    with pytest.raises(RuntimeError, match="digikey_oauth_setup"):
        auth.token()


def test_no_credentials_at_all_raises(auth, monkeypatch):
    monkeypatch.setenv("DIGIKEY_REFRESH_TOKEN", "")
    monkeypatch.delenv("DIGIKEY_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="digikey_oauth_setup"):
        auth.token()


def test_dry_run_never_touches_the_network(auth, monkeypatch):
    calls = _stub(monkeypatch, [_Resp({"access_token": "nope"})])
    monkeypatch.setenv("SUPPLIER_DRY_RUN", "true")
    assert auth.token() == "dry-run-token"
    assert calls == []


# --- status feeds the Admin system-status row -------------------------------
def test_status_reports_self_refresh_capability(auth, monkeypatch):
    _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800})])
    auth.token()
    st = auth.status()
    assert st["state"] == "ok" and st["canSelfRefresh"] and st["cached"]
    assert st["expiresInSeconds"] > 0


def test_status_flags_a_static_token_as_unable_to_self_refresh(auth, monkeypatch):
    monkeypatch.setenv("DIGIKEY_REFRESH_TOKEN", "")
    monkeypatch.setenv("DIGIKEY_ACCESS_TOKEN", "manual-token")
    st = auth.status()
    assert st["state"] == "static_token_no_refresh"
    assert st["canSelfRefresh"] is False


# --- cross-process cache -----------------------------------------------------
def test_disk_cache_is_reused_by_a_second_process(auth, monkeypatch):
    calls = _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800})])
    auth.token()
    second = ua.DigiKeyUserAuth()               # simulates another worker
    assert second.token() == "at-1"
    assert len(calls) == 1                       # no second rotation


def test_disk_cache_is_rejected_after_the_refresh_token_changes(auth, monkeypatch):
    _stub(monkeypatch, [_Resp({"access_token": "at-1", "expires_in": 1800})])
    auth.token()
    monkeypatch.setenv("DIGIKEY_REFRESH_TOKEN", "some-other-token")
    assert ua.DigiKeyUserAuth()._token is None
