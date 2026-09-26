"""
Shared component-lookup/search foundation.

One search capability, multiple entry points: general Component Search,
Needs Review's Find Replacement / Check PartsBox, and (eventually)
BOM-line alternative lookup and PartsBox Inventory discovery all call
search_components() with a LookupQuery. None of them gets its own
supplier client, its own PartsBox parsing, or its own result shape.

Reuses, rather than reimplements:
- PartsBoxClient.get_parts() / find_part_by_mpn_and_manufacturer()
- MouserClient.search_candidates() (same candidate objects sourcing uses)
- DigiKeyClient.search_candidates() (same candidate objects sourcing uses)
- manufacturer_aliases.manufacturers_equivalent() for fuzzy manufacturer
  matching, instead of a second manufacturer-normalization scheme.
"""

from dataclasses import asdict, dataclass, field

from engineering_units import parse_engineering_value
from manufacturer_aliases import manufacturers_equivalent
from partsbox_client import PartsBoxClient
from mouser_client import MouserClient
from digikey_client import DigiKeyClient

DEFAULT_SOURCES = frozenset({"partsbox"})
ALL_SOURCES = frozenset({"partsbox", "mouser", "digikey"})

# PartsBox part fields already mapped onto a named LookupResult field --
# everything else on the raw part dict is exposed generically through
# `characteristics` (see _partsbox_part_to_result) instead of being
# dropped, so a category-specific field PartsBox actually returns (e.g.
# a capacitance or voltage attribute) becomes filterable without this
# module needing to know its name in advance.
#
# Confirmed live (2026-09-24, real part/all response, ~3450 parts): NONE
# of them include a "part/category" or "part/package" key at all -- these
# two fields are not present in this account's PartsBox part records via
# this endpoint (a "part/type" field exists but is a PartsBox internal
# record-type discriminator, i.e. "linked"/"local"/"meta", unrelated to
# electronic component category). category/package will read as "" for
# every PartsBox result until either a per-part detail endpoint exposing
# them is confirmed and added, or this account begins populating those
# fields -- this is expected/confirmed behavior, not a bug in the
# extraction below.
_KNOWN_PARTSBOX_FIELDS = {
    "part/id",
    "part/mpn",
    "part/name",
    "part/manufacturer",
    "part/description",
    "part/category",
    "part/package",
}


@dataclass
class LookupQuery:
    """
    Query/filter object for the shared lookup. Only mpn/manufacturer/
    keywords actually reach the PartsBox/Mouser/DigiKey searches in this
    phase -- the remaining fields are accepted now so callers (e.g. a
    future Find Replacement prefill for a capacitor: category, value,
    voltage, package, dielectric, tolerance) have somewhere to put what
    AutoBOM already knows without requiring a second query model later.
    `characteristics` is an open dict for anything category-specific that
    doesn't have a named field yet.
    """

    mpn: str = ""
    manufacturer: str = ""
    keywords: str = ""
    category: str = ""
    package: str = ""
    mounting: str = ""
    dielectric: str = ""
    tolerance: str = ""
    voltage: str = ""
    current: str = ""
    power: str = ""
    value: str = ""
    required_qty: object = None
    sources: frozenset = field(default_factory=lambda: DEFAULT_SOURCES)
    characteristics: dict = field(default_factory=dict)

    def search_term(self):
        return (self.mpn or self.keywords or "").strip()


@dataclass
class LookupResult:
    """
    Normalized-enough-to-display-together result. Category-specific or
    source-specific detail that doesn't fit a named field lives in
    `characteristics` (parsed, when available) and `raw` (the original
    payload, always preserved) rather than being dropped or forced into a
    field that doesn't really fit every category.
    """

    source: str
    manufacturer: str = ""
    mpn: str = ""
    description: str = ""
    category: str = ""
    package: str = ""
    stock: object = None
    supplier_part_number: str = ""
    unit_price: str = ""
    lifecycle_status: str = ""
    characteristics: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    # Display-only fact, not a sourcing decision: whether this candidate's
    # known stock covers a required quantity the caller supplied (e.g. a
    # BOM row's required_qty during Find Replacement). None when unknown
    # (stock or the requirement itself isn't known) -- never guessed.
    stock_sufficient: object = None

    def to_dict(self):
        data = asdict(self)
        # Flatten characteristics onto the top level too, so
        # record_filter's generic field-based facet/range filtering can
        # operate on them directly (filters={"voltage": {...}}) without
        # needing to know about the nested "characteristics" dict.
        # setdefault avoids a characteristic overwriting a named field.
        for key, value in (self.characteristics or {}).items():
            data.setdefault(key, value)
        return data


def build_query_from_bom_row(row, sources=None):
    """
    Builds a LookupQuery prepopulated with everything AutoBOM already
    knows about a BOM row, so a Needs Review recovery action never makes
    the operator re-enter data the app already has. Only uses fields that
    actually exist on the row (bom_cleaner's current schema has no parsed
    voltage/tolerance/package/etc. fields); it never fabricates a
    specification AutoBOM doesn't actually have. The same function serves
    both Find Replacement (sources defaults to Mouser+DigiKey, per the
    required recovery order) and Check PartsBox (call again with
    sources={"partsbox"}) -- one prepopulation implementation, not two.
    """
    resolved_sources = frozenset({"mouser", "digikey"}) if sources is None else frozenset(sources)
    return LookupQuery(
        mpn=str(row.get("mpn", "") or "").strip(),
        manufacturer=str(row.get("manufacturer", "") or "").strip(),
        keywords=str(row.get("description", "") or "").strip(),
        required_qty=row.get("required_qty"),
        sources=resolved_sources,
    )


def search_components(query, partsbox_client=None, mouser_client=None, digikey_client=None, errors=None):
    """
    Runs the query against every source enabled on it and returns a flat
    list of normalized dicts (LookupResult.to_dict()), ready to hand to
    record_filter.search_and_filter() for further text search/filtering --
    the same filtering layer the Results Workspace uses.

    Each source is isolated: a Mouser/DigiKey API failure (e.g. a query
    string their part-number search endpoint rejects -- confirmed live,
    typing a plain-English description into what only accepts a real
    part number returns an HTTP 400) no longer aborts the whole call and
    silently drops PartsBox/the other supplier's results too. When
    `errors` is a list, a `(source, message)` tuple is appended for each
    source that failed, so a caller can surface "DigiKey failed, Mouser
    results below are still current" instead of losing everything or
    crashing the page. `errors=None` (the default) keeps every existing
    caller's behavior unchanged except no longer crashing on a bad
    query -- that source's results are just empty.
    """
    # An explicitly empty source set must stay empty (no results) rather
    # than silently falling back to PartsBox -- only a genuinely unset
    # (None) sources value uses the default.
    sources = query.sources if query.sources is not None else DEFAULT_SOURCES
    results = []

    def _run_source(source_name, search_fn):
        try:
            results.extend(search_fn())
        except Exception as exc:  # noqa: BLE001 -- one supplier's failure must never sink the others
            if errors is not None:
                errors.append((source_name, str(exc)))

    if "partsbox" in sources:
        client = partsbox_client or PartsBoxClient()
        _run_source("partsbox", lambda: _search_partsbox(query, client))

    if "mouser" in sources:
        client = mouser_client or MouserClient()
        _run_source("mouser", lambda: _search_mouser(query, client))

    if "digikey" in sources:
        client = digikey_client or DigiKeyClient()
        _run_source("digikey", lambda: _search_digikey(query, client))

    required_qty = parse_engineering_value(query.required_qty)
    for result in results:
        result.stock_sufficient = _stock_covers_requirement(result.stock, required_qty)

    return [result.to_dict() for result in results]


def _stock_covers_requirement(stock, required_qty):
    if required_qty is None or stock is None:
        return None
    try:
        return float(stock) >= required_qty
    except (TypeError, ValueError):
        return None


def _search_partsbox(query, client):
    """
    An empty query (no mpn/keywords/manufacturer) matches every part --
    this is what lets the PartsBox Inventory workspace browse the full
    catalog through the exact same function Component Search and Find
    Replacement use, rather than a separate "list everything" path.
    """
    matches = []
    for part in client.get_parts():
        if _partsbox_part_matches(part, query):
            matches.append(_partsbox_part_to_result(part))

    return matches


def _partsbox_part_matches(part, query):
    mpn = str(part.get("part/mpn") or part.get("part/name") or "").lower()
    manufacturer = str(part.get("part/manufacturer") or "").lower()
    description = str(part.get("part/description") or "").lower()

    if query.manufacturer and query.manufacturer.strip().lower() not in manufacturer:
        if not manufacturers_equivalent(query.manufacturer, part.get("part/manufacturer") or ""):
            return False

    search_term = query.search_term().strip().lower()
    if search_term:
        haystack = " ".join([mpn, manufacturer, description])
        if search_term not in haystack:
            return False

    return True


def _partsbox_part_to_result(part):
    characteristics = {
        key.replace("part/", ""): value
        for key, value in part.items()
        if key not in _KNOWN_PARTSBOX_FIELDS
        and key != "part/tags"
        and value not in (None, "", [], {})
    }

    return LookupResult(
        source="PartsBox",
        manufacturer=part.get("part/manufacturer", "") or "",
        mpn=part.get("part/mpn") or part.get("part/name") or "",
        description=part.get("part/description", "") or "",
        category=part.get("part/category", "") or "",
        package=part.get("part/package", "") or "",
        # PartsBox does not have a confirmed stock/quantity field
        # available through this client (see the Codex audit); left
        # unknown rather than guessed.
        stock=None,
        supplier_part_number="",
        unit_price="",
        lifecycle_status="",
        characteristics=characteristics,
        raw=part,
    )


def _search_mouser(query, client):
    search_term = query.search_term()
    if not search_term:
        return []

    candidates = client.search_candidates(search_term)
    results = [_supplier_result_to_lookup_result(candidate, "Mouser") for candidate in candidates]
    return _filter_by_manufacturer(results, query.manufacturer)


def _search_digikey(query, client):
    search_term = query.search_term()
    if not search_term:
        return []

    candidates = client.search_candidates(search_term)
    results = [_supplier_result_to_lookup_result(candidate, "DigiKey") for candidate in candidates]
    return _filter_by_manufacturer(results, query.manufacturer)


def _filter_by_manufacturer(results, manufacturer):
    if not manufacturer:
        return results

    return [
        result
        for result in results
        if not result.manufacturer or manufacturers_equivalent(manufacturer, result.manufacturer)
    ]


def _supplier_result_to_lookup_result(supplier_result, source):
    return LookupResult(
        source=source,
        manufacturer=supplier_result.manufacturer,
        mpn=supplier_result.mpn,
        description=supplier_result.description,
        category=supplier_result.category,
        package=supplier_result.package,
        stock=supplier_result.stock,
        supplier_part_number=supplier_result.supplier_part_number,
        unit_price=supplier_result.unit_price,
        lifecycle_status="",
        characteristics=supplier_result.characteristics,
        raw=asdict(supplier_result),
    )
