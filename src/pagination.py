"""
Shared, pure pagination helper -- one implementation for Main Search
(PartsBox side and Supplier side), PartsBox Inventory, and each active
Needs Review replacement lookup, instead of a page-specific paginator
for each. Takes an already filtered/sorted list and slices it; contains
no Streamlit, no filtering, and no knowledge of what the records
represent.
"""

from dataclasses import dataclass, field

DEFAULT_PAGE_SIZE = 20


@dataclass
class Page:
    items: list
    total_items: int
    page: int
    page_size: int
    total_pages: int
    start_index: int
    end_index: int
    all_items: list = field(default_factory=list, repr=False)


def total_pages_for(total_items, page_size=DEFAULT_PAGE_SIZE):
    if total_items <= 0:
        return 1
    return -(-total_items // page_size)  # ceil division


def clamp_page(page, total_pages):
    """
    Keeps a stored page number valid after the underlying result set
    shrinks (a filter narrows the set, or the PartsBox snapshot
    refreshes with fewer matches) -- never lets a stale page number
    point past the end, and never below page 1.
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    return max(1, min(page, total_pages))


def paginate(records, page=1, page_size=DEFAULT_PAGE_SIZE):
    """
    Slices `records` (already text-searched, filtered, and sorted by the
    caller -- this function does none of that) into one page. `page` is
    clamped into range rather than raising, so a caller doesn't need to
    separately validate a page number restored from session_state before
    calling this.
    """
    records = list(records)
    total_items = len(records)
    pages = total_pages_for(total_items, page_size)
    page = clamp_page(page, pages)

    start_index = (page - 1) * page_size
    end_index = min(start_index + page_size, total_items)

    return Page(
        items=records[start_index:end_index],
        total_items=total_items,
        page=page,
        page_size=page_size,
        total_pages=pages,
        start_index=start_index,
        end_index=end_index,
        all_items=records,
    )


def result_signature(*parts):
    """
    A deterministic signature of whatever inputs define the current
    result set (normalized query text, selected sources, filter values,
    sort, snapshot generation, ...). Callers store the previous
    signature in session_state and reset the relevant page to 1 only
    when it changes -- selecting a row or changing a quantity never
    touches the inputs this is built from, so it never resets the page.
    """
    normalized = []
    for part in parts:
        if isinstance(part, (set, frozenset)):
            normalized.append(tuple(sorted(str(item) for item in part)))
        elif isinstance(part, dict):
            normalized.append(tuple(sorted((str(k), _freeze(v)) for k, v in part.items())))
        else:
            normalized.append(_freeze(part))
    return tuple(normalized)


def _freeze(value):
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(str(item) for item in value))
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    return value
