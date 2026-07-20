"""PartsBox live inventory -> the frontend inventory shape, with a cache-if-flaky
safety net (per the Phase 3 guardrail: real data live where it works, last-good
cached snapshot when PartsBox is flaky — the demo never makes a fragile live call
in the room without a fallback).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from services.partsbox_client import PartsBoxClient

log = logging.getLogger("autobom.inventory")

CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "partsbox_inventory.json"
DEFAULT_LIMIT = 600


def _data(resp):
    if isinstance(resp, dict):
        return resp.get("data") or resp.get("parts") or resp.get("value") or []
    return resp or []


def _storage_map(client) -> dict:
    smap = {}
    try:
        for s in _data(client.list_storage_locations()):
            sid = s.get("storage/id")
            if not sid:
                continue
            tags = [str(t).lower() for t in (s.get("storage/tags") or [])]
            kind = "wall" if any("develop" in t for t in tags) else "project"
            smap[sid] = {"name": s.get("storage/name") or sid, "kind": kind}
    except Exception as exc:
        log.warning("PartsBox storage list failed: %s", exc)
    return smap


def fetch_live(limit: int = DEFAULT_LIMIT) -> list:
    client = PartsBoxClient()
    parts = _data(client.list_parts())
    smap = _storage_map(client)
    inv = []
    for p in parts:
        by_loc, total = {}, 0
        for e in (p.get("part/stock") or []):
            q = e.get("stock/quantity") or 0
            total += q
            sid = e.get("stock/storage-id")
            if sid:
                by_loc[sid] = by_loc.get(sid, 0) + q
        if total <= 0:
            continue
        locations = [{"kind": smap.get(sid, {}).get("kind", "project"),
                      "name": smap.get(sid, {}).get("name", sid), "qty": q}
                     for sid, q in by_loc.items() if q]
        inv.append({
            "mpn": p.get("part/mpn") or p.get("part/name") or p.get("part/id"),
            "mfr": p.get("part/manufacturer") or "",
            "desc": p.get("part/description") or p.get("part/name") or "",
            "onHand": total, "low": total <= 5, "locations": locations,
            "tags": ["autobom-managed"] if any(l["kind"] == "project" for l in locations) else [],
        })
    inv.sort(key=lambda x: -x["onHand"])
    return inv[:limit]


def _stats(inv: list) -> dict:
    return {"parts": len(inv), "onHand": sum(p["onHand"] for p in inv),
            "low": sum(1 for p in inv if p["low"])}


def _save_cache(inv: list) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"cached_at": time.time(), "inventory": inv}))
    except OSError as exc:
        log.warning("inventory cache write failed: %s", exc)


def _load_cache():
    try:
        return json.loads(CACHE_PATH.read_text()).get("inventory")
    except (OSError, ValueError):
        return None


def get_inventory() -> dict:
    """Live PartsBox where it works; last-good cache when flaky; empty as a last
    resort (screens render a calm empty state, never crash)."""
    try:
        inv = fetch_live()
        _save_cache(inv)
        return {"inventory": inv, "source": "live", "stats": _stats(inv)}
    except Exception as exc:
        log.warning("PartsBox live inventory failed (%s); serving cache.", exc)
        cached = _load_cache()
        if cached is not None:
            return {"inventory": cached, "source": "cache", "stats": _stats(cached)}
        return {"inventory": [], "source": "empty", "error": str(exc)[:200], "stats": _stats([])}
