"""PartsBox live inventory -> the frontend inventory shape, with a cache-if-flaky
safety net (per the Phase 3 guardrail: real data live where it works, last-good
cached snapshot when PartsBox is flaky — the demo never makes a fragile live call
in the room without a fallback).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from services.partsbox_client import PartsBoxClient

log = logging.getLogger("autobom.inventory")

CACHE_PATH = Path(__file__).resolve().parents[2] / ".cache" / "partsbox_inventory.json"
# No row cap. `part/all` already returns the WHOLE account in one response
# (verified: 3121 parts / 1881 storage / 116 projects) — there is no pagination
# to follow. The old DEFAULT_LIMIT=600 + `inv[:limit]` silently truncated the
# result to the first 600 parts, which is why the UI showed ~19% of inventory
# with no "load more" affordance anywhere.
DEFAULT_LIMIT = None


def _data(resp):
    if isinstance(resp, dict):
        return resp.get("data") or resp.get("parts") or resp.get("value") or []
    return resp or []


def _project_names(client) -> set:
    """Lower-cased PartsBox project names, used to spot project boxes by name."""
    try:
        return {(p.get("project/name") or "").strip().lower()
                for p in _data(client.list_projects()) if p.get("project/name")}
    except Exception as exc:
        log.warning("PartsBox project list failed: %s", exc)
        return set()


def _storage_map(client) -> dict:
    """Classify every storage location as a project box or a development wall bin.

    Ground truth from the connected account (1881 locations): NO location
    carries a `development` tag. 18 are tagged `Production` and their names are
    board/variant names that also appear in `project/all`; a further 3 match a
    project name without the tag. Everything else is the pre-existing wall
    infrastructure — either untagged (`M5-2`, `Cabinet Bin-#46`, `box1-C32`) or
    tagged with a COMPONENT CATEGORY (`Resistor`, `Inductors`, `HV-Capacitor`),
    which is how the wall is organised, not a storage kind.

    So the only reliable signal is "is this a project box?"; the wall is the
    default. Two previous attempts both got this wrong: defaulting unknown to
    `project` made the Project-boxes filter match everything, and defaulting to
    `other` meant `wall` was never emitted at all and the Development-wall tab
    always showed 0 of 0.

    NOTE (divergence from CLAUDE.md): the spec says wall bins are "discovered
    via development tag". No such tag exists in this account, so the wall is
    derived by exclusion instead. Flagging rather than silently diverging.
    """
    smap = {}
    project_names = _project_names(client)
    try:
        for s in _data(client.list_storage_locations()):
            sid = s.get("storage/id")
            if not sid:
                continue
            name = s.get("storage/name") or sid
            tags = [str(t).lower() for t in (s.get("storage/tags") or [])]
            is_project = (
                any(("production" in t or "project" in t) for t in tags)
                or name.strip().lower() in project_names
            )
            smap[sid] = {"name": name, "kind": "project" if is_project else "wall"}
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
        # Zero-stock parts are kept: they are real rows in the PartsBox library
        # and dropping them made the part count disagree with PartsBox itself.
        # Unknown locations now fall back to "wall" (the default infrastructure)
        # rather than silently inventing a project box.
        locations = [{"kind": smap.get(sid, {}).get("kind", "wall"),
                      "name": smap.get(sid, {}).get("name", sid), "qty": q}
                     for sid, q in by_loc.items() if q]
        part_id = p.get("part/id")
        inv.append({
            "id": part_id,
            # Real deep link into the PartsBox web app. The UI renders the
            # "Open in PartsBox" affordance only when this is present, instead
            # of the old href="#" that silently did nothing.
            "url": client.part_web_url(part_id),
            "mpn": p.get("part/mpn") or p.get("part/name") or part_id,
            "mfr": p.get("part/manufacturer") or "",
            "desc": p.get("part/description") or p.get("part/name") or "",
            "onHand": total, "low": total <= 5, "locations": locations,
            "tags": ["autobom-managed"] if any(l["kind"] == "project" for l in locations) else [],
        })
    inv.sort(key=lambda x: -x["onHand"])
    # `limit` stays supported for callers that genuinely want a slice, but the
    # default is now None = return everything.
    return inv[:limit] if limit else inv


def _stats(inv: list) -> dict:
    """Counts the Inventory header renders.

    `distinctBins` / `projectBoxes` / `wallBins` are derived from the real
    payload. The frontend previously read these from a stale bundled fixture
    (window.PARTSBOX_STATS), so the storage-location tile never reflected the
    connected account at all.
    """
    bins, project_bins, wall_bins = set(), set(), set()
    for p in inv:
        for l in (p.get("locations") or []):
            bins.add(l["name"])
            (project_bins if l["kind"] == "project" else wall_bins).add(l["name"])
    return {"parts": len(inv), "onHand": sum(p["onHand"] for p in inv),
            "low": sum(1 for p in inv if p["low"]),
            "distinctBins": len(bins), "projectBoxes": len(project_bins),
            "wallBins": len(wall_bins)}


def _save_cache(inv: list) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"cached_at": time.time(), "inventory": inv}))
    except OSError as exc:
        log.warning("inventory cache write failed: %s", exc)


def _load_cache(max_age: float | None = None):
    """Cached inventory, or None. With max_age, an older snapshot is a miss.

    Two distinct uses:
      - max_age set  -> TTL cache: is the snapshot fresh enough to serve?
      - max_age None -> last-good fallback: serve it at any age rather than
                        showing an empty screen when PartsBox is down.
    """
    try:
        blob = json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None
    if max_age is not None and (time.time() - float(blob.get("cached_at") or 0)) > max_age:
        return None
    return blob.get("inventory")


def cache_ttl_seconds() -> int:
    """CLAUDE.md: 60s default, Admin-configurable."""
    try:
        return int(os.getenv("INVENTORY_CACHE_TTL_SECONDS", "60"))
    except ValueError:
        return 60


def get_inventory() -> dict:
    """Fresh cache -> live -> last-good cache -> empty.

    The TTL short-circuit (audit item C1) matters a lot here: `part/all` returns
    the WHOLE account and measured ~10s / ~1MB, and this endpoint was refetching
    all of it on every single call. Serving a fresh snapshot turns repeat loads
    (second tab, navigating back to Inventory) into an instant local read.
    """
    fresh = _load_cache(max_age=cache_ttl_seconds())
    if fresh is not None:
        return {"inventory": fresh, "source": "cache", "stats": _stats(fresh)}
    try:
        inv = fetch_live()
        _save_cache(inv)
        return {"inventory": inv, "source": "live", "stats": _stats(inv)}
    except Exception as exc:
        log.warning("PartsBox live inventory failed (%s); serving cache.", exc)
        cached = _load_cache()          # any age beats an empty screen
        if cached is not None:
            return {"inventory": cached, "source": "cache", "stats": _stats(cached)}
        return {"inventory": [], "source": "empty", "error": str(exc)[:200], "stats": _stats([])}


def get_inventory_stats() -> dict:
    """Just the aggregate numbers the header tiles render.

    Same data source as get_inventory(), but the ~1MB of part records never
    leaves the server. This is what loads eagerly on session hydration; the full
    payload is now fetched only when the Inventory screen actually mounts.
    """
    data = get_inventory()
    return {"stats": data.get("stats") or _stats([]), "source": data.get("source")}
