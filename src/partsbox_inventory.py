"""
Shared, cached, enriched PartsBox inventory snapshot -- one join of
part/all + storage/all + project/all + the signed stock-ledger netting +
storage-space classification, built once per cache generation and reused
by Main Search's PartsBox side, PartsBox Inventory, Needs Review's
PartsBox replacement lookup, and the inventory-location recommender.
None of those may build their own second PartsBox read/join.

Process-wide, not per-session: every operator on the eventual Yank PC
shares the same PartsBox account, so one cached snapshot (with a bounded
TTL, explicit refresh, and invalidation after a known AutoBOM PartsBox
write) avoids each browser session re-fetching the ~3,450-part catalog.
This module has no Streamlit dependency on purpose -- caching lives here
as plain Python (a module-level dict + lock), not as an
`st.cache_data`-decorated PartsBoxClient method, so it stays usable and
testable outside a running Streamlit app, and the low-level
PartsBoxClient stays a plain API adapter (see partsbox_client.py).
"""

import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from partsbox_client import PartsBoxClient
from storage_space_classifier import (
    DEVELOPMENT,
    MECHANICAL,
    OTHER,
    PROJECT,
    classify_storage,
    load_storage_space_rules,
)

DEFAULT_TTL_SECONDS = 300  # 5 minutes, per the audit's initial policy.


def net_quantities_by_storage(stock_ledger):
    """
    Confirmed live (2026-09-24): PartsBox's `part/stock` is a signed
    transaction ledger -- [{"stock/quantity": N, "stock/storage-id": id,
    ...}, ...] -- not a simple current-location field. Summing signed
    quantities per storage-id is the standard ledger interpretation, not
    a guess: a storage-id with a positive net sum currently holds stock;
    one with a net <= 0 has been fully consumed/relocated away and must
    never be reported as a current location.

    Public/shared (moved here from inventory_location_recommender.py,
    which now imports it from here) so Inventory display, Main Search
    enrichment, and location recommendation all use the exact same
    netting, never three independent reimplementations.
    """
    if not isinstance(stock_ledger, list):
        return {}

    totals = Counter()
    for entry in stock_ledger:
        if not isinstance(entry, dict):
            continue
        storage_id = entry.get("stock/storage-id")
        quantity = entry.get("stock/quantity")
        if storage_id is None or not isinstance(quantity, (int, float)):
            continue
        totals[storage_id] += quantity

    return {storage_id: total for storage_id, total in totals.items() if total > 0}


@dataclass
class InventoryPart:
    """
    One enriched PartsBox part. `raw` keeps the original part/all record
    (never dropped); `locations` is the full list of CURRENT (positive
    net) storage memberships for this part -- deliberately a list, never
    collapsed into one `storage_space`/`location` field, since a part
    can simultaneously exist in general Development storage and one or
    more Projects at once (confirmed against the operator-supplied
    export: at least 290 parts hold multiple simultaneous locations).
    """

    part_id: str
    mpn: str
    manufacturer: str
    description: str
    category: str
    package: str
    characteristics: dict
    raw: dict
    locations: list = field(default_factory=list)
    total_quantity: int = 0

    @property
    def development_locations(self):
        return [loc for loc in self.locations if loc["space_type"] == DEVELOPMENT]

    @property
    def project_locations(self):
        return [loc for loc in self.locations if loc["space_type"] == PROJECT]

    @property
    def mechanical_locations(self):
        return [loc for loc in self.locations if loc["space_type"] == MECHANICAL]

    @property
    def other_locations(self):
        return [loc for loc in self.locations if loc["space_type"] == OTHER]

    @property
    def projects(self):
        # Distinct project names this part currently sits in, in
        # encounter order -- convenience for a "Project" facet/filter
        # without every caller re-deriving it from locations.
        seen = []
        for loc in self.project_locations:
            name = loc.get("project_name") or loc.get("name")
            if name and name not in seen:
                seen.append(name)
        return seen

    def to_dict(self):
        """
        Flattens this enriched part into the same shape
        record_filter.search_and_filter()/generate_facets() and
        component_lookup.LookupResult.to_dict() already produce for
        Mouser/DigiKey/plain-PartsBox results -- source/mpn/manufacturer/
        description/category/package/stock/characteristics -- so Main
        Search's combined table and the shared Selected Part Details
        panel need no PartsBox-specific branch. `stock` here is the real
        net-ledger total_quantity (this snapshot's whole point -- the old
        component_lookup._partsbox_part_to_result() path left stock as
        None since it never joined the ledger). `location`/
        `storage_space`/`project` are list-valued so record_filter's
        membership-filter kind (a part can sit in several locations at
        once) can filter on them directly.
        """
        data = {
            "source": "PartsBox",
            "part_id": self.part_id,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "category": self.category,
            "package": self.package,
            "stock": self.total_quantity,
            "supplier_part_number": "",
            "unit_price": "",
            "lifecycle_status": "",
            "characteristics": self.characteristics,
            "raw": self.raw,
            "locations": self.locations,
            "location": [loc["name"] for loc in self.locations],
            "storage_space": sorted({loc["space_type"] for loc in self.locations}),
            "project": self.projects,
        }
        for key, value in (self.characteristics or {}).items():
            data.setdefault(key, value)
        return data


@dataclass
class PartsBoxInventorySnapshot:
    generation: int
    loaded_at: float
    parts: list
    storage_by_id: dict
    project_names: list

    @property
    def part_count(self):
        return len(self.parts)

    @property
    def storage_count(self):
        return len(self.storage_by_id)

    def age_seconds(self):
        return time.time() - self.loaded_at


def build_partsbox_inventory_snapshot(client=None):
    """
    Fetches part/all, storage/all, and project/all exactly once each and
    joins them into a PartsBoxInventorySnapshot. Pure with respect to
    caching -- this function always does a fresh fetch; get_snapshot()
    below is what applies the TTL/reuse policy. Never called from inside
    a per-keystroke UI path -- see get_snapshot().
    """
    client = client or PartsBoxClient()
    rules = load_storage_space_rules()

    storage_response = client.list_storage_locations()
    storage_records = storage_response.get("data", storage_response.get("storage", []))
    storage_by_id = {
        storage.get("storage/id"): storage
        for storage in storage_records
        if isinstance(storage, dict) and storage.get("storage/id")
    }

    project_response = client.list_projects()
    project_records = project_response.get("data", project_response.get("projects", []))
    project_names = sorted(
        {
            str(project.get("project/name") or project.get("name") or "").strip()
            for project in project_records
            if isinstance(project, dict) and (project.get("project/name") or project.get("name"))
        }
    )

    storage_classification = {
        storage_id: classify_storage(storage, project_names, rules=rules)
        for storage_id, storage in storage_by_id.items()
    }
    storage_names = {
        storage_id: storage.get("storage/name") or storage.get("name") or str(storage_id)
        for storage_id, storage in storage_by_id.items()
    }
    normalized_project_names = {name.strip().lower() for name in project_names}

    raw_parts = client.get_parts()
    parts = [
        _enrich_part(part, storage_by_id, storage_names, storage_classification, normalized_project_names)
        for part in raw_parts
        if isinstance(part, dict)
    ]

    return PartsBoxInventorySnapshot(
        generation=0,  # overwritten by get_snapshot()'s cache bookkeeping
        loaded_at=time.time(),
        parts=parts,
        storage_by_id=storage_by_id,
        project_names=project_names,
    )


def _enrich_part(part, storage_by_id, storage_names, storage_classification, normalized_project_names):
    net_by_storage = net_quantities_by_storage(part.get("part/stock"))

    locations = []
    for storage_id, quantity in net_by_storage.items():
        name = storage_names.get(storage_id, str(storage_id))
        space_type = storage_classification.get(storage_id, OTHER)
        location = {
            "storage_id": storage_id,
            "name": name,
            "quantity": int(quantity),
            "space_type": space_type,
        }
        if space_type == PROJECT and name.strip().lower() in normalized_project_names:
            location["project_name"] = name
        locations.append(location)

    # Deterministic order -- highest quantity first -- so "most of this
    # part lives here" is always first without the UI re-sorting.
    locations.sort(key=lambda loc: loc["quantity"], reverse=True)

    known_fields = {
        "part/id",
        "part/mpn",
        "part/name",
        "part/manufacturer",
        "part/description",
        "part/category",
        "part/package",
        "part/stock",
        "part/tags",
    }
    characteristics = {
        key.replace("part/", ""): value
        for key, value in part.items()
        if key not in known_fields and value not in (None, "", [], {})
    }

    return InventoryPart(
        part_id=part.get("part/id", ""),
        mpn=part.get("part/mpn") or part.get("part/name") or "",
        manufacturer=part.get("part/manufacturer", "") or "",
        description=part.get("part/description", "") or "",
        category=part.get("part/category", "") or "",
        package=part.get("part/package", "") or "",
        characteristics=characteristics,
        raw=part,
        locations=locations,
        total_quantity=sum(loc["quantity"] for loc in locations),
    )


# --- Process-wide cache -----------------------------------------------
#
# A plain module-level dict, not st.cache_data: this stays a pure-Python
# concern testable without Streamlit, and one process serving many
# browser sessions (the deployment recommendation) shares this single
# cache entry across all of them, rather than one per session.

_cache_lock = threading.Lock()
_cache = {"snapshot": None, "generation": 0}


def get_snapshot(ttl_seconds=DEFAULT_TTL_SECONDS, force_refresh=False, client=None):
    """
    Returns the shared snapshot, fetching a fresh one only when there is
    none yet, the cached one is older than ttl_seconds, or force_refresh
    is True. On a refresh failure, the previous snapshot (if any) is
    retained and re-returned rather than raising, so a transient
    PartsBox outage doesn't blank out Inventory/Search for every
    session -- callers that want to detect/report a failed refresh
    attempt should use refresh() directly instead.
    """
    with _cache_lock:
        cached = _cache["snapshot"]
        if cached is not None and not force_refresh and cached.age_seconds() < ttl_seconds:
            return cached

    try:
        return refresh(client=client)
    except Exception:
        with _cache_lock:
            if _cache["snapshot"] is not None:
                return _cache["snapshot"]
        raise


def refresh(client=None):
    """
    Unconditionally fetches a new snapshot and installs it as the shared
    cache entry, incrementing the generation counter (used by callers as
    part of a pagination/result-set signature -- see
    src/pagination.py's result_signature()). Raises on failure without
    touching the existing cached snapshot, so callers that want failure
    visibility (an explicit "Refresh PartsBox data" action) can catch
    and report it while get_snapshot() elsewhere keeps serving the last
    good snapshot.
    """
    snapshot = build_partsbox_inventory_snapshot(client=client)
    with _cache_lock:
        _cache["generation"] += 1
        snapshot.generation = _cache["generation"]
        _cache["snapshot"] = snapshot
        return snapshot


def invalidate():
    """
    Drops the cached snapshot (without fetching a replacement) so the
    next get_snapshot() call fetches fresh data. Called after an AutoBOM
    PartsBox write (project/storage creation, BOM-entry sync) that could
    affect the joined view, so Inventory/Search don't keep serving
    stock/location data that's now known stale.
    """
    with _cache_lock:
        _cache["snapshot"] = None


def peek_snapshot():
    """Returns the current cached snapshot without triggering a fetch (or None)."""
    with _cache_lock:
        return _cache["snapshot"]


def reset_cache_for_tests():
    """Test-only: clears the shared cache so tests don't leak state into each other."""
    with _cache_lock:
        _cache["snapshot"] = None
        _cache["generation"] = 0
