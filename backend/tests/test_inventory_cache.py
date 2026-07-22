"""Inventory TTL cache (audit C1), the stats-only endpoint, and PartsBox deep links.

Context: /api/inventory refetched the WHOLE PartsBox account on every call
(~1MB, measured ~10s) and the frontend called it on every session hydration.
"""

import json
import time

import pytest

from services import partsbox_inventory as pi
from services.partsbox_client import PartsBoxClient

SAMPLE = [{"id": "p1", "mpn": "A", "mfr": "Acme", "desc": "d", "onHand": 10,
           "low": False, "locations": [{"kind": "project", "name": "box-1", "qty": 10}],
           "tags": [], "url": "u"}]


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, "CACHE_PATH", tmp_path / "inv.json")
    return pi.CACHE_PATH


def _write(path, inv, age_seconds=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cached_at": time.time() - age_seconds, "inventory": inv}))


# --- TTL semantics ----------------------------------------------------------
def test_fresh_cache_is_served_without_calling_partsbox(cache, monkeypatch):
    """The C1 fix: a fresh snapshot must short-circuit the ~10s live fetch."""
    _write(cache, SAMPLE, age_seconds=5)
    monkeypatch.setattr(pi, "fetch_live", lambda *a, **k: pytest.fail("called PartsBox despite a fresh cache"))
    out = pi.get_inventory()
    assert out["source"] == "cache" and out["inventory"] == SAMPLE


def test_stale_cache_triggers_a_live_refetch(cache, monkeypatch):
    _write(cache, SAMPLE, age_seconds=99999)
    monkeypatch.setattr(pi, "fetch_live", lambda *a, **k: SAMPLE)
    assert pi.get_inventory()["source"] == "live"


def test_ttl_is_configurable(monkeypatch):
    monkeypatch.setenv("INVENTORY_CACHE_TTL_SECONDS", "600")
    assert pi.cache_ttl_seconds() == 600
    monkeypatch.setenv("INVENTORY_CACHE_TTL_SECONDS", "not-a-number")
    assert pi.cache_ttl_seconds() == 60          # falls back, never crashes


def test_stale_cache_still_beats_an_empty_screen_when_partsbox_is_down(cache, monkeypatch):
    """Cache-if-flaky must survive the TTL change: an OLD snapshot is still
    better than an empty inventory when the live call fails."""
    _write(cache, SAMPLE, age_seconds=99999)
    def boom(*a, **k):
        raise RuntimeError("PartsBox unreachable")
    monkeypatch.setattr(pi, "fetch_live", boom)
    out = pi.get_inventory()
    assert out["source"] == "cache" and out["inventory"] == SAMPLE


def test_no_cache_and_dead_partsbox_yields_a_calm_empty(cache, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(pi, "fetch_live", boom)
    out = pi.get_inventory()
    assert out["source"] == "empty" and out["inventory"] == []
    assert out["stats"]["parts"] == 0


# --- stats-only endpoint ----------------------------------------------------
def test_stats_endpoint_omits_the_part_records(cache, monkeypatch):
    """This is the call that now runs on every hydration - the ~1MB of part
    records must NOT be in it."""
    _write(cache, SAMPLE, age_seconds=1)
    out = pi.get_inventory_stats()
    assert "inventory" not in out
    assert out["stats"]["parts"] == 1 and out["stats"]["onHand"] == 10


def test_stats_match_the_full_payloads_stats(cache, monkeypatch):
    _write(cache, SAMPLE, age_seconds=1)
    assert pi.get_inventory_stats()["stats"] == pi.get_inventory()["stats"]


# --- PartsBox deep links ----------------------------------------------------
def test_part_url_pins_the_workspace(monkeypatch):
    """Without the workspace slug the link resolves against whatever workspace
    the VIEWER's PartsBox session has selected, so it lands on a foreign parts
    list instead of our part."""
    monkeypatch.delenv("PARTSBOX_WORKSPACE", raising=False)
    monkeypatch.delenv("PARTSBOX_WEB_URL", raising=False)
    url = PartsBoxClient().part_web_url("abc123")
    assert url == "https://partsbox.com/yanktechinventory/parts/abc123"


def test_workspace_is_overridable(monkeypatch):
    monkeypatch.setenv("PARTSBOX_WORKSPACE", "otherworkspace")
    assert "/otherworkspace/parts/" in PartsBoxClient().part_web_url("abc123")


def test_part_url_is_none_without_an_id():
    assert PartsBoxClient().part_web_url(None) is None


def test_inventory_rows_carry_a_workspace_pinned_url(cache, monkeypatch):
    monkeypatch.delenv("PARTSBOX_WORKSPACE", raising=False)
    assert "/yanktechinventory/parts/" in PartsBoxClient().part_web_url("x")
