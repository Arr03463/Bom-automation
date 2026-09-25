"""
Inventory Customer Reference location recommendation (INV-<LOCATION>).

Reuses component_lookup.search_components() and PartsBoxClient -- the
SAME PartsBox search/matching every other AutoBOM screen uses. No second
PartsBox matching engine.

Priority order (per the feature spec):
  1. Exact Manufacturer+MPN match already in PartsBox, with a reliably
     determinable current storage location.
  2/3. Similar components (structured characteristics when available,
     description/manufacturer overlap otherwise), recommending wherever
     those similar parts are actually stored.

This is a transparent, rule-based scorer -- not a machine-learning
system, per the feature spec's explicit instruction not to build one.
"""

from collections import Counter
from dataclasses import dataclass

from component_lookup import LookupQuery, search_components
from manufacturer_aliases import manufacturers_equivalent
from partsbox_client import PartsBoxClient
from partsbox_inventory import net_quantities_by_storage as _net_quantities_by_storage
from storage_space_classifier import DEVELOPMENT, classify_storage, load_storage_space_rules

CONFIDENCE_EXACT_PART = "Exact Part"
CONFIDENCE_STRONG_SIMILARITY = "Strong Similarity"
CONFIDENCE_SIMILAR_FAMILY = "Similar Family"
CONFIDENCE_LOW = "Low Confidence"
CONFIDENCE_MANUAL = "Manual Selection Required"


@dataclass
class LocationRecommendation:
    location: str = ""
    confidence: str = CONFIDENCE_MANUAL
    reason: str = ""


def _storage_lookup(partsbox_client):
    """
    Returns (name_by_id, classification_by_id) built through the exact
    same storage-space classification Main Search/PartsBox Inventory use
    (storage_space_classifier.classify_storage()) -- not a second
    Development/Project rule for recommendations specifically.
    """
    storage_response = partsbox_client.list_storage_locations()
    storage_data = storage_response.get("data", []) if isinstance(storage_response, dict) else []
    storage_records = {
        storage.get("storage/id"): storage
        for storage in storage_data
        if isinstance(storage, dict) and storage.get("storage/id")
    }

    project_response = partsbox_client.list_projects()
    project_data = (
        project_response.get("data", project_response.get("projects", []))
        if isinstance(project_response, dict)
        else []
    )
    project_names = [
        str(project.get("project/name") or project.get("name") or "").strip()
        for project in project_data
        if isinstance(project, dict) and (project.get("project/name") or project.get("name"))
    ]

    rules = load_storage_space_rules()
    name_by_id = {
        storage_id: storage.get("storage/name") or storage.get("name") or str(storage_id)
        for storage_id, storage in storage_records.items()
    }
    classification_by_id = {
        storage_id: classify_storage(storage, project_names, rules=rules)
        for storage_id, storage in storage_records.items()
    }
    return name_by_id, classification_by_id


def _recommend_exact_part_location(mpn, manufacturer, partsbox_client):
    """
    Codex/audit finding: Project storage must never outrank Development
    storage for an ordinary INV-<LOCATION> recommendation merely because
    it happens to hold more stock or appear more often -- a part with 10
    units in Development storage and 100 in a Project location should
    still recommend the Development location. Development evidence is
    therefore considered FIRST and exclusively when any exists; Project/
    Mechanical/Other locations are only surfaced (at a visibly lower
    confidence) when there is no Development evidence at all.
    """
    part = partsbox_client.find_part_by_mpn_and_manufacturer(mpn, manufacturer)
    if not part:
        return None

    net_by_storage = _net_quantities_by_storage(part.get("part/stock"))
    if not net_by_storage:
        # Exact part exists but current storage cannot be determined
        # reliably (no ledger entries, or every entry nets to zero/negative)
        # -- fall through to similarity analysis rather than guessing.
        return None

    name_by_id, classification_by_id = _storage_lookup(partsbox_client)
    development_storage = {
        storage_id: qty
        for storage_id, qty in net_by_storage.items()
        if classification_by_id.get(storage_id) == DEVELOPMENT
    }

    if len(development_storage) == 1:
        storage_id = next(iter(development_storage))
        name = name_by_id.get(storage_id, storage_id)
        return LocationRecommendation(
            location=name,
            confidence=CONFIDENCE_EXACT_PART,
            reason="Exact manufacturer part already stored here (Development storage).",
        )

    if len(development_storage) > 1:
        # Multiple DEVELOPMENT locations currently hold stock -- don't
        # guess which one is "the" answer. Surface the highest-quantity
        # one, but at a lower confidence tier so the operator double-checks.
        storage_id, _quantity = max(development_storage.items(), key=lambda item: item[1])
        name = name_by_id.get(storage_id, storage_id)
        return LocationRecommendation(
            location=name,
            confidence=CONFIDENCE_STRONG_SIMILARITY,
            reason=(
                f"Exact manufacturer part is currently stocked in {len(development_storage)} "
                "Development locations; showing the one with the most stock. Verify before accepting."
            ),
        )

    # No Development evidence at all -- the part IS stocked somewhere
    # (Project/Mechanical/Other), but ordinary inventory placement must
    # not silently point there just because that's where stock happens
    # to be.
    if len(net_by_storage) == 1:
        storage_id = next(iter(net_by_storage))
        name = name_by_id.get(storage_id, storage_id)
        space_type = classification_by_id.get(storage_id, "Other")
        return LocationRecommendation(
            location=name,
            confidence=CONFIDENCE_LOW,
            reason=(
                f"Exact manufacturer part is only currently stocked in a {space_type} "
                f"location ({name!r}), not general Development storage. Shown for context -- "
                "verify before using it as an ordinary inventory location."
            ),
        )

    return LocationRecommendation(
        confidence=CONFIDENCE_MANUAL,
        reason=(
            f"Exact manufacturer part is currently stocked in {len(net_by_storage)} "
            "non-Development locations (Project/Mechanical/Other); manual selection "
            "recommended for ordinary inventory placement."
        ),
    )


def _similarity_tier(candidate, description_tokens, manufacturer):
    """
    Uses whatever signal is actually available: category/package/
    characteristics when PartsBox has them (some accounts do), degrading
    to description-keyword overlap + manufacturer match when it doesn't
    (confirmed live: this account's real data has neither category nor
    package populated). Returns None when there isn't even that much
    signal, so the caller can exclude a near-zero-evidence "match".
    """
    category = str(candidate.get("category") or "").strip().lower()
    package = str(candidate.get("package") or "").strip().lower()
    characteristics = candidate.get("characteristics") or {}
    structured_signal = int(bool(category)) + int(bool(package)) + min(len(characteristics), 2)

    candidate_tokens = set(str(candidate.get("description") or "").lower().split())
    token_overlap = len(description_tokens & candidate_tokens)

    candidate_manufacturer = str(candidate.get("manufacturer") or "")
    manufacturer_match = bool(manufacturer) and manufacturers_equivalent(manufacturer, candidate_manufacturer)

    if structured_signal >= 2 or (manufacturer_match and token_overlap >= 2):
        return CONFIDENCE_STRONG_SIMILARITY
    if structured_signal >= 1 or token_overlap >= 1 or manufacturer_match:
        return CONFIDENCE_SIMILAR_FAMILY
    return None


def _recommend_similar_location(mpn, manufacturer, description, partsbox_client):
    # Deliberately a BROAD candidate pool, not a tight keyword search:
    # search_components()'s PartsBox matching requires the keywords
    # string to appear as a literal substring of each candidate's
    # mpn/manufacturer/description -- exactly right for a human typing a
    # search box, but far too strict for "find anything similar" (a
    # different value, e.g. "4.7k" vs "10k", would never substring-match).
    # Scope by manufacturer instead (or browse-all if manufacturer is
    # unknown, which search_components already supports for an empty
    # query) to gather candidates, then rank them with _similarity_tier()
    # below -- still the same PartsBoxClient/search_components this app
    # uses everywhere else, just a broader query feeding our own scorer.
    query = LookupQuery(
        keywords="",
        manufacturer=manufacturer,
        sources=frozenset({"partsbox"}),
    )
    candidates = search_components(query, partsbox_client=partsbox_client)

    normalized_mpn = str(mpn or "").strip().lower()
    candidates = [c for c in candidates if str(c.get("mpn", "")).strip().lower() != normalized_mpn]

    description_tokens = set(str(description or "").lower().split())

    tiered = []
    for candidate in candidates:
        tier = _similarity_tier(candidate, description_tokens, manufacturer)
        if tier:
            tiered.append((tier, candidate))

    if not tiered:
        return LocationRecommendation(
            confidence=CONFIDENCE_MANUAL,
            reason="No sufficiently similar PartsBox parts found.",
        )

    best_tier = CONFIDENCE_STRONG_SIMILARITY if any(t == CONFIDENCE_STRONG_SIMILARITY for t, _ in tiered) else CONFIDENCE_SIMILAR_FAMILY
    tier_candidates = [c for t, c in tiered if t == best_tier]

    name_by_id, classification_by_id = _storage_lookup(partsbox_client)

    all_location_counts = Counter()
    development_location_counts = Counter()
    for candidate in tier_candidates:
        raw = candidate.get("raw") or {}
        for storage_id in _net_quantities_by_storage(raw.get("part/stock")):
            all_location_counts[storage_id] += 1
            if classification_by_id.get(storage_id) == DEVELOPMENT:
                development_location_counts[storage_id] += 1

    if not all_location_counts:
        return LocationRecommendation(
            confidence=CONFIDENCE_MANUAL,
            reason=(
                f"Found {len(tier_candidates)} similar part(s), but none has a "
                "determinable current storage location."
            ),
        )

    if not development_location_counts:
        # Similar parts exist, but only in Project/Mechanical/Other
        # storage -- never point ordinary inventory placement there
        # without flagging it (Codex/audit finding: Project-only
        # evidence must not become a high-confidence recommendation).
        return LocationRecommendation(
            confidence=CONFIDENCE_LOW,
            reason=(
                f"Found {len(tier_candidates)} similar part(s), but they are only stored "
                "in Project/Mechanical/Other locations, not general Development storage; "
                "manual selection recommended."
            ),
        )

    top_storage_id, top_count = development_location_counts.most_common(1)[0]
    total = sum(development_location_counts.values())
    name = name_by_id.get(top_storage_id, top_storage_id)

    if len(development_location_counts) > 1 and top_count / total < 0.5:
        return LocationRecommendation(
            confidence=CONFIDENCE_LOW,
            reason=(
                f"Similar parts are stored across {len(development_location_counts)} different "
                "Development locations with no clear majority; manual selection recommended."
            ),
        )

    return LocationRecommendation(
        location=name,
        confidence=best_tier,
        reason=f"{len(tier_candidates)} similar part(s) found; most are stored in Development at {name!r}.",
    )


def recommend_location(mpn, manufacturer="", description="", partsbox_client=None):
    """
    The one entry point: Priority 1 (exact part, reliable location) then
    Priority 2/3 (similar parts' storage pattern), never silently
    finalizing a location -- always returns a LocationRecommendation for
    the caller (the UI) to present as Accept/Override, never applied
    automatically.
    """
    client = partsbox_client or PartsBoxClient()

    if str(mpn or "").strip():
        exact = _recommend_exact_part_location(mpn, manufacturer, client)
        if exact is not None:
            return exact

    return _recommend_similar_location(mpn, manufacturer, description, client)
