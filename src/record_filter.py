"""
Shared search/filter layer over lists of dict-like records.

Deliberately generic: it knows nothing about BOM rows or supplier
lookups specifically. The Results Workspace filters ActiveBomState rows
through this; Component Search and the future Needs Review replacement
lookup filter component_lookup results through the same functions. One
filtering implementation, multiple callers -- no page gets its own
one-off filter logic.
"""

STOCK_FILTER_FIELD = "stock"


def text_search(records, query_text, search_fields):
    """Case-insensitive substring search across the given fields."""
    query_text = str(query_text or "").strip().lower()
    if not query_text:
        return list(records)

    matched = []
    for record in records:
        haystack = " ".join(str(record.get(field, "") or "") for field in search_fields).lower()
        if query_text in haystack:
            matched.append(record)

    return matched


def apply_filters(records, filters):
    """
    filters: dict of field name -> desired value. A filter is skipped when
    its value is empty/None or the sentinel "All" (the usual "no
    selection" state for a UI dropdown). Every other field does a
    case-insensitive exact match against the record's value. The "stock"
    field is a special case: desired value "In Stock"/"Out of Stock"/
    "Unknown" compares against a numeric threshold (or its absence)
    instead of an exact string match -- a record with no confirmed stock
    figure (e.g. a PartsBox match) is Unknown, never treated as zero.
    """
    if not filters:
        return list(records)

    return [record for record in records if _matches_filters(record, filters)]


def search_and_filter(records, query_text="", search_fields=(), filters=None):
    matched = text_search(records, query_text, search_fields)
    return apply_filters(matched, filters)


def _matches_filters(record, filters):
    for field, desired in filters.items():
        if desired in (None, "", "All"):
            continue

        if field == STOCK_FILTER_FIELD:
            if not _matches_stock_filter(record, desired):
                return False
            continue

        actual = str(record.get(field, "") or "").strip().lower()
        if actual != str(desired).strip().lower():
            return False

    return True


def _matches_stock_filter(record, desired):
    stock = coerce_int_or_none(record.get(STOCK_FILTER_FIELD))
    desired_normalized = str(desired).strip().lower()

    if desired_normalized == "in stock":
        return stock is not None and stock > 0
    if desired_normalized == "out of stock":
        return stock is not None and stock <= 0
    if desired_normalized == "unknown":
        return stock is None

    return True


def coerce_int_or_none(value):
    """
    Shared numeric coercion: used here for the stock filter, and by
    active_bom_state.py to derive a normalized display `stock` field from
    a row's supplier-specific mouser_stock/digikey_stock columns -- one
    implementation instead of two.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
