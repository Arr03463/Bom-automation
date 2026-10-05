import base64
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_FOLDER = PROJECT_ROOT / "src"

load_dotenv(PROJECT_ROOT / ".env", override=True)

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from bom_cleaner import apply_project_quantities  # noqa: E402
from component_lookup import (  # noqa: E402
    LookupQuery,
    build_query_from_bom_row,
    search_components,
)
from config_validation import collect_startup_warnings  # noqa: E402
from customer_reference import (  # noqa: E402
    MAX_LENGTH as CUSTOMER_REFERENCE_MAX_LENGTH,
    build_inventory_reference,
    build_project_reference,
    build_rnd_reference,
    validate_customer_reference,
)
from customer_reference_registry import (  # noqa: E402
    RegistryError,
    add_pcb_code,
    add_project,
    get_pcb_codes,
    get_projects,
)
from engineering_units import parse_engineering_value  # noqa: E402
from inventory_location_recommender import recommend_location  # noqa: E402
from pagination import DEFAULT_PAGE_SIZE, clamp_page, paginate, result_signature, total_pages_for  # noqa: E402
from partsbox_client import PartsBoxClient  # noqa: E402
from partsbox_inventory import get_snapshot as get_partsbox_snapshot  # noqa: E402
from partsbox_inventory import invalidate as invalidate_partsbox_snapshot  # noqa: E402
from partsbox_inventory import peek_snapshot as peek_partsbox_snapshot  # noqa: E402
from record_filter import generate_facets, search_and_filter  # noqa: E402
from review_actions import apply_replacement, retry_exact_sourcing  # noqa: E402
from run_workspace import build_run_workspace, save_uploaded_file  # noqa: E402
from search_events import search_event_input  # noqa: E402
from workflow_runner import (  # noqa: E402
    build_purchasing_summary,
    refresh_response_snapshot,
    regenerate_purchasing,
    run_bom_workflow,
    start_manual_bom_workflow,
)


RESULTS_SEARCH_FIELDS = ["mpn", "manufacturer", "description", "supplier_part_number", "designators"]

RESULTS_DISPLAY_COLUMNS = {
    "mpn": "Manufacturer Part Number",
    "manufacturer": "Manufacturer",
    "description": "Description",
    "designators": "Designators",
    "required_qty": "Quantity Required",
    "source": "Source",
    "customer_reference": "Customer Reference",
    "supplier_part_number": "Supplier Part Number",
    "result_status": "Status",
    "review_reason": "Review Reason",
}

LOOKUP_DISPLAY_COLUMNS = {
    "source": "Source",
    "mpn": "MPN",
    "manufacturer": "Manufacturer",
    "description": "Description",
    "category": "Category",
    "package": "Package",
    "stock": "Stock",
    "supplier_part_number": "Supplier Part Number",
    "unit_price": "Unit Price",
}

# Facets shown only when the current result set actually has data for
# them (record_filter.generate_facets) -- never a fixed always-shown
# list. Categorical facets get an exact-match selectbox; range facets get
# min/max numeric inputs parsed via engineering_units. "stock" is
# excluded from both since it already has its own dedicated In Stock/Out
# of Stock/Unknown filter. CATEGORICAL_FACET_FIELDS doubles as the
# candidate pool for the separate Component Characteristics surface (see
# render_component_characteristics()) -- same generate_facets() call,
# same "only offer what the current result set actually has" rule, just
# a second UI entry point over (mostly) the same field set, per the
# frontend design spec's Component Characteristics component.
CATEGORICAL_FACET_FIELDS = ["category", "package", "mounting", "dielectric", "lifecycle_status"]
CHARACTERISTIC_FIELDS = ["package", "voltage", "tolerance", "dielectric", "mounting"]
RANGE_FACET_FIELDS = [
    "voltage",
    "current",
    "power",
    "tolerance",
    "resistance",
    "capacitance",
    "inductance",
    "unit_price",
]

# Discovery Results (Main Search's PartsBox/Supplier tables): fixed-height,
# fixed-page-size tables per the frontend design spec -- a 5-result search
# and a 3,000+ part Browse Inventory render the same card height. 14/page
# is the spec's own demonstrated constant (its prose elsewhere says 20,
# but that contradicts both this constant and the spec's own "target
# 12-15" instruction -- 14 is the correct read).
DISCOVERY_PAGE_SIZE = 14
DISCOVERY_ROW_HEIGHT = 32
DISCOVERY_HEADER_HEIGHT = 30
DISCOVERY_TABLE_HEIGHT = DISCOVERY_HEADER_HEIGHT + DISCOVERY_PAGE_SIZE * DISCOVERY_ROW_HEIGHT

# Working Parts List: its own presentation-only pagination, independent
# of Discovery Results and of the canonical BOM's actual size -- a
# 5-line and a 500-line BOM render the same list height.
WORKING_LIST_PAGE_SIZE = 10
WORKING_LIST_TABLE_HEIGHT = DISCOVERY_HEADER_HEIGHT + WORKING_LIST_PAGE_SIZE * DISCOVERY_ROW_HEIGHT


RUN_SCOPED_STATE_DEFAULTS = {
    "selected_review_row_id": None,
    "replacement_panel_open": False,
    "results_search": "",
    "results_filter_source": "All",
    "results_filter_status": "All",
}


def init_session_state():
    """
    Every session gets its own st.session_state dict (Streamlit's own
    per-session isolation -- no extra code required for that). This just
    sets the defaults so the same keys exist on the first render.
    current_run holds the live ActiveBomState (via
    current_run["_active_bom_state"]) -- there is no second BOM state
    anywhere in this file.
    """
    st.session_state.setdefault("current_run", None)
    st.session_state.setdefault("replacement_lookup_sources", frozenset({"mouser", "digikey"}))
    # Shared Configuration section defaults -- set here (not just via each
    # widget's own value=) so Upload's button handler can safely read them
    # via st.session_state even on the very first page load, before the
    # Configuration section (rendered inside Add Parts' right column,
    # below Upload -- see render_add_parts_section()) has been
    # instantiated in this pass yet.
    st.session_state.setdefault("cfg_build_quantity", 1)
    st.session_state.setdefault("cfg_project_name", "")
    st.session_state.setdefault("cfg_project_description", "")
    st.session_state.setdefault("cfg_update_partsbox_project", True)
    for key, default in RUN_SCOPED_STATE_DEFAULTS.items():
        st.session_state.setdefault(key, default)


def reset_run_scoped_session_state():
    """
    Clears state tied to the PREVIOUS run's rows so it cannot reappear
    against a new run: the open review row, its in-progress replacement
    search results, and the results search/filters. Called whenever a
    new run replaces current_run.

    Main Search's own state (component_search_*) is deliberately left
    alone: it is a global entry point independent of any specific BOM
    run, not a per-run cache that needs clearing.
    """
    for key, default in RUN_SCOPED_STATE_DEFAULTS.items():
        st.session_state[key] = default

    stale_keys = [
        key
        for key in st.session_state
        if key.startswith("replacement_results_") or key.startswith("replacement_query_")
    ]
    for key in stale_keys:
        del st.session_state[key]


def _authoritative_sources():
    """
    The Sources checkboxes beside Search (component_search_partsbox/
    _mouser/_digikey) are authoritative for every later seam that can
    query a supplier -- Main Search, uploaded-part sourcing, Add to BOM,
    Retry Exact, and replacement re-sourcing alike (the architecture
    audit's precondition D). An unchecked supplier here must mean no
    later seam unexpectedly queries it; this is the one place that
    reads those checkboxes into the {"mouser", "digikey"}-shaped
    `sources` set review_actions.py's _lookup_functions() expects.
    Defaults to both enabled before the widgets have rendered/been set
    (mirrors their own default=True).
    """
    return {
        source
        for source, key in (("mouser", "component_search_mouser"), ("digikey", "component_search_digikey"))
        if st.session_state.get(key, True)
    }


def show_download(label, file_path, disabled=False):
    if not file_path:
        return

    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return

    with path.open("rb") as file_handle:
        st.download_button(
            label=label,
            data=file_handle,
            file_name=path.name,
            mime="application/octet-stream",
            disabled=disabled,
        )


def render_add_parts_section():
    """
    The unified BOM intake area: Search and Upload are two alternative
    ways to populate the SAME canonical working BOM (ActiveBomState),
    never two parallel BOM states -- see _add_search_result_to_working_bom()
    and render_upload_intake()'s merge-vs-replace logic, both of which
    write through the one shared active_bom_state, however it was
    started. Search is shown first/larger since it's the default intake
    method (works with no upload at all); Upload sits beside it as the
    secondary option, with Configuration stacked directly below it in
    the same narrower column -- Upload alone doesn't fill this column's
    height, and Configuration is what Upload's own processing reads at
    the moment a file is dropped, so keeping the two visually adjacent
    matches how they actually depend on each other. Run messages (the
    automation's own success/warning/info log for whatever run is
    current) are pushed to the very end of the page instead of showing
    here -- see render_autobom_workflow_page() -- so the operator sees
    the actual working BOM/results before a wall of run-log text.
    """
    st.subheader("Add Parts")

    left, right = st.columns([2, 1])
    with left:
        render_component_search_intake()
    with right:
        render_upload_intake()
        st.divider()
        render_configuration_section()


def _pagination_controls(total_items, key_prefix, signature, page_size=DEFAULT_PAGE_SIZE):
    """
    Shared pagination (src/pagination.py) for every paginated result
    table in this app (Main Search's PartsBox/Supplier Discovery Results,
    Working Parts List, Needs Review's replacement lookup) -- one
    paginator, not a per-table reimplementation; `page_size` is the only
    per-table knob (Discovery Results and Working Parts List each fix
    their own page size/table height independent of result count -- see
    DISCOVERY_PAGE_SIZE/WORKING_LIST_PAGE_SIZE). `signature` is a
    pagination.result_signature(...) of everything that defines the
    CURRENT result set (query text, selected sources, active filters,
    snapshot generation, ...); when it changes from the previous render,
    the page resets to 1 -- but a signature that only depends on those
    things, never on quantity/row-selection state, means selecting a row
    or adjusting a quantity stepper elsewhere on the page never resets
    pagination. The pagination row hides entirely (replaced by a plain
    count line) once everything already fits on one page.
    """
    sig_key = f"{key_prefix}_page_sig"
    page_key = f"{key_prefix}_page_num"
    if st.session_state.get(sig_key) != signature:
        st.session_state[sig_key] = signature
        st.session_state[page_key] = 1

    total_pages = total_pages_for(total_items, page_size=page_size)
    current_page = clamp_page(st.session_state.get(page_key, 1), total_pages)

    if total_pages > 1:
        nav_cols = st.columns([1, 3, 1])
        with nav_cols[0]:
            if st.button("< Prev", key=f"{key_prefix}_prev_page", disabled=current_page <= 1):
                current_page -= 1
        with nav_cols[1]:
            st.caption(f"Page {current_page} of {total_pages} · {total_items} result(s)")
        with nav_cols[2]:
            if st.button("Next >", key=f"{key_prefix}_next_page", disabled=current_page >= total_pages):
                current_page += 1
        current_page = clamp_page(current_page, total_pages)
    elif total_items:
        st.caption(f"{total_items} result(s)")

    st.session_state[page_key] = current_page
    return current_page


def _render_paginated_table(records, key_prefix, columns_map, signature, page_size=DEFAULT_PAGE_SIZE, height=None):
    """
    Filter-before-paginate: `records` must already be the fully
    filtered/sorted result set. Renders pagination controls, then a
    selectable st.dataframe scoped to just the current page's rows, and
    returns whichever row is selected on THIS page (or None) -- the
    single seam every result table in this app uses to populate the
    shared Selected Part Details panel instead of a per-row Add button.
    `height`, when given, fixes the table's rendered height regardless of
    how many rows are on the current page (Discovery Results/Working
    Parts List's "same card height whether 5 results or 3,000" rule) --
    st.dataframe pads/scrolls within it rather than the table growing or
    shrinking with row count.
    """
    current_page = _pagination_controls(len(records), key_prefix, signature, page_size=page_size)
    page = paginate(records, page=current_page, page_size=page_size)

    if not page.items:
        st.info("No results match the current search/filters.")
        return None

    table_df = pd.DataFrame(page.items)
    available_columns = [col for col in columns_map if col in table_df.columns]
    display_df = table_df[available_columns].rename(columns=columns_map)

    event = st.dataframe(
        display_df,
        width="stretch",
        height=height or "content",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}_table",
    )
    selected_positions = event.selection.rows if event is not None and event.selection else []
    if selected_positions:
        return page.items[selected_positions[0]]
    return None


def _membership_facet_filters(results, fields, key_prefix):
    """
    Multiselect filters for list-valued PartsBox fields (Storage Space /
    Location / Project -- a part can sit in several at once, see
    partsbox_inventory.InventoryPart) -- built only for fields that
    actually have data in the current result set
    (record_filter.generate_facets), same "don't offer an empty filter"
    rule render_dynamic_facet_filters() follows for its facets. Returns
    a filters dict of field -> list, ready for record_filter's
    membership-filter kind.
    """
    filters = {}
    facets = generate_facets(results, fields)
    for field, values in facets.items():
        selection = st.multiselect(
            field.replace("_", " ").title(), values, key=f"{key_prefix}_membership_{field}"
        )
        if selection:
            filters[field] = selection
    return filters


def render_component_characteristics(records, key_prefix):
    """
    A second, collapsible filter surface over parametric fields
    (CHARACTERISTIC_FIELDS), reusing the exact same "only offer a field
    the current result set actually has data for"
    (record_filter.generate_facets) rule Basic Filters uses -- never a
    fixed engineering-parameter list. There is one filtered-result
    computation (record_filter.apply_filters, via the returned dict);
    this is a second UI entry point into it, not a second engine.
    Entirely hidden when there's nothing to filter on. The design spec's
    add/remove chip picker becomes one st.multiselect choosing which
    characteristics are active (its native per-chip "x" already matches
    that removal UX) plus one st.selectbox per active field for its
    exact value (default "Any" = not filtered on that field yet).
    """
    available = generate_facets(records, CHARACTERISTIC_FIELDS)
    if not available:
        return {}

    filters = {}
    with st.expander("Component Characteristics", expanded=False):
        labels = {field: field.replace("_", " ").title() for field in available}
        active_fields = st.multiselect(
            "Add a characteristic to filter on",
            list(available.keys()),
            format_func=lambda field: labels.get(field, field),
            key=f"{key_prefix}_char_active",
        )
        for field in active_fields:
            selection = st.selectbox(
                labels.get(field, field),
                ["Any"] + available[field],
                key=f"{key_prefix}_char_value_{field}",
            )
            if selection != "Any":
                filters[field] = selection
    return filters


def _clear_component_search_filters():
    """
    "Clear All Filters" -- deletes every filter widget's session_state
    entry (Basic Filters' stock/manufacturer/dynamic-facet/membership
    keys, Component Characteristics' active-list/value keys) so they
    render back at their defaults on the next run, then reruns
    immediately: unlike the Add-to-BOM/mutation buttons elsewhere in this
    file, there is no later-section-ordering hazard here to avoid a
    rerun for (see render_selected_part_details()'s docstring for that
    concern) -- this button IS the whole interaction.
    """
    prefixes = (
        "component_search_stock_filter",
        "component_search_basic_membership_",
        "component_search_facet_",
        "component_search_range_min_",
        "component_search_range_max_",
        "component_search_membership_",
        "component_search_char_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]
    st.rerun()


def render_component_search_intake():
    """
    The PRIMARY way to add parts to the working BOM. PartsBox filters
    live over the shared snapshot (partsbox_inventory.get_snapshot(),
    the same snapshot Needs Review's Check PartsBox and the location
    recommender use) as the operator types -- no Search button, no
    PartsBox API call per keystroke. An explicit "Browse Inventory"
    button shows the complete catalog without requiring a query (folds
    the old standalone PartsBox Inventory page into this panel, per the
    frontend design spec's retirement of that separate page). Mouser/
    DigiKey are only ever queried when the operator presses Enter in the
    search box (see search_events.search_event_input() -- its
    `.submitted` is a one-shot trigger that is None on every rerun
    except the one where Enter was just pressed), never from typing,
    filter changes, pagination, or row selection -- this is the audit's
    core "Enter vs. live typing" boundary. Sources checkboxes here are
    authoritative for this search AND for later seams (see
    _authoritative_sources()); unchecking Mouser/DigiKey mid-session
    filters its already-fetched rows out of the displayed table
    immediately (the underlying stored result set is untouched, so
    re-checking it shows those rows again without a new call), and no
    NEW call is made while unchecked -- a stale-sources caption tells the
    operator to press Enter when the checked sources no longer match
    what was last actually searched.

    Nothing is added just by searching or selecting a row -- there is
    one shared Selected Part Details panel (render_selected_part_details())
    with the quantity input and the single "Add to BOM" button, not a
    per-row quantity/button pair.
    """
    st.markdown("#### Search")

    source_cols = st.columns(3)
    with source_cols[0]:
        use_partsbox = st.checkbox("PartsBox", value=True, key="component_search_partsbox")
    with source_cols[1]:
        use_mouser = st.checkbox("Mouser", value=True, key="component_search_mouser")
    with source_cols[2]:
        use_digikey = st.checkbox("DigiKey", value=True, key="component_search_digikey")
    st.caption(
        "PartsBox filters as you type. Mouser/DigiKey are only queried when you press Enter "
        "in the search box. These same checkboxes govern sourcing for uploaded parts, Add to "
        "BOM, Retry Exact, and Find Replacement -- uncheck a supplier here first to keep it "
        "out of all of them."
    )

    # Widget-key rotation is how the Clear (X) button below force-resets
    # search_event_input's remembered draft: the component's own CCv2
    # sync state (keyed by `key`) always wins over a plain `value=`
    # override once any real typing has happened, so the only reliable
    # reset is mounting a brand-new widget instance under a fresh key --
    # incrementing this counter and re-deriving the key does that.
    st.session_state.setdefault("component_search_event_generation", 0)
    search_widget_key = f"component_search_event_{st.session_state['component_search_event_generation']}"

    clear_col, search_col = st.columns([1, 5])
    with clear_col:
        if st.button("✕ Clear", key="component_search_clear_button"):
            st.session_state["component_search_event_generation"] += 1
            search_widget_key = f"component_search_event_{st.session_state['component_search_event_generation']}"
            st.session_state["component_search_text"] = ""
            # A blank query has no supplier meaning -- results clear
            # entirely and the panel returns to its idle "press Enter"
            # state, per the interaction spec's Search §1 "Clearing the
            # field" behavior (distinct from just leaving stale supplier
            # rows visible, which is what happens when the draft diverges
            # from the last Enter query without being fully cleared).
            st.session_state["component_search_supplier_results"] = []
            st.session_state["component_search_last_submitted"] = None
            st.session_state["component_search_selected_part"] = None
    with search_col:
        search_result = search_event_input(
            key=search_widget_key,
            value=st.session_state.get("component_search_text", ""),
            placeholder="MPN, manufacturer, or keywords",
            debounce_ms=350,
        )
    live_text = search_result.value if search_result.value is not None else ""

    # Selected-row lifecycle, rule 3: a selection is cleared when the
    # draft goes from non-blank to blank (typed away or Cleared above) --
    # but NOT merely because an unrelated filter/page/quantity changed.
    # Detected via a shadow "was it non-blank last render" flag since
    # neither `live_text` nor session_state alone expose "did this
    # transition just happen".
    if st.session_state.get("_component_search_had_query") and not live_text.strip():
        st.session_state["component_search_selected_part"] = None
    st.session_state["_component_search_had_query"] = bool(live_text.strip())
    st.session_state["component_search_text"] = live_text

    if search_result.submitted is not None:
        # Selected-row lifecycle, rule 1: a new committed Enter query
        # clears any current selection (the result sets it could have
        # come from are both about to change).
        st.session_state["component_search_selected_part"] = None
        enter_sources = {
            source for source, enabled in (("mouser", use_mouser), ("digikey", use_digikey)) if enabled
        }
        if enter_sources:
            query = LookupQuery(
                mpn=search_result.submitted,
                keywords=search_result.submitted,
                sources=frozenset(enter_sources),
            )
            supplier_errors = []
            with st.spinner("Searching suppliers..."):
                st.session_state["component_search_supplier_results"] = search_components(
                    query, errors=supplier_errors
                )
            # A supplier rejecting this exact query (e.g. Mouser's
            # part-number search endpoint returning HTTP 400 for
            # free-text keywords instead of a real MPN) no longer takes
            # the whole search down with it -- the other supplier's
            # results above still came back; this just reports which
            # one(s) failed and why.
            for failed_source, message in supplier_errors:
                st.warning(f"{failed_source.title()} search failed: {message}")
        else:
            st.session_state["component_search_supplier_results"] = []
        # Tracked separately from the live `.submitted` trigger value
        # itself (which resets to None on every subsequent rerun) so the
        # supplier table's pagination signature below still reflects
        # "what was last actually searched" on reruns that aren't
        # themselves an Enter press (e.g. adjusting a filter), and so the
        # stale-results caption below can compare the current draft
        # against the last thing actually searched for.
        st.session_state["component_search_last_submitted"] = (search_result.submitted, tuple(sorted(enter_sources)))

    # Selected-row lifecycle, rule 2: unchecking the source that produced
    # the current selection clears it (its result set may no longer even
    # be queried/displayed).
    _current_selection = st.session_state.get("component_search_selected_part")
    if _current_selection is not None:
        _selection_source = _current_selection.get("source")
        _source_now_off = (
            (_selection_source == "PartsBox" and not use_partsbox)
            or (_selection_source == "Mouser" and not use_mouser)
            or (_selection_source == "DigiKey" and not use_digikey)
        )
        if _source_now_off:
            st.session_state["component_search_selected_part"] = None

    # "Browse Inventory": an explicit action to view the whole PartsBox
    # catalog with no query -- distinct from live-typed filtering, and
    # cleared the moment the operator starts typing (typing always wins).
    if live_text.strip():
        st.session_state["component_search_browse_all"] = False
    elif use_partsbox:
        if st.button("Browse Inventory", key="component_search_browse_button"):
            st.session_state["component_search_browse_all"] = True
    browse_all = st.session_state.get("component_search_browse_all", False)

    partsbox_records = []
    partsbox_snapshot_generation = 0
    if use_partsbox:
        # Gated, not unconditional: a completely blank/cold AutoBOM
        # startup (empty search box, no Browse Inventory click yet,
        # nothing cached from earlier this process) must not itself
        # trigger a full-catalog PartsBox fetch just because this
        # section rendered -- the audit's "blank startup doesn't load
        # the full PartsBox catalog" requirement. Typing, Browse
        # Inventory, or an already-warm cache is what actually loads it;
        # once warm, every further keystroke/rerun reuses the shared
        # cached snapshot.
        should_load_partsbox = bool(live_text.strip()) or browse_all or peek_partsbox_snapshot() is not None
        if should_load_partsbox:
            try:
                snapshot = get_partsbox_snapshot()
            except Exception as exc:
                st.error(f"Could not load PartsBox inventory: {exc}")
                snapshot = None
            if snapshot is not None:
                partsbox_snapshot_generation = snapshot.generation
                all_partsbox_records = [part.to_dict() for part in snapshot.parts]
                partsbox_records = search_and_filter(
                    all_partsbox_records,
                    query_text=live_text,
                    search_fields=["mpn", "manufacturer", "description"],
                )
                st.caption(
                    f"PartsBox snapshot: {snapshot.part_count} part(s) -- "
                    f"updated {int(snapshot.age_seconds())}s ago."
                )
        else:
            st.caption("Type to search PartsBox inventory, or click Browse Inventory to see everything.")

    # Unchecking a supplier here must remove its already-fetched rows from
    # display, not just block new calls -- otherwise the Sources
    # checkboxes and the visible table contradict each other (QA/QC
    # deep-dive report, Q6). Filtered here, before facets/pagination/
    # selection, rather than left in the stored result set: re-checking a
    # supplier later can still show its last fetched rows again (the
    # underlying stored set is untouched), it's only display that's
    # gated on the current checkbox state.
    enabled_supplier_labels = {
        label for label, enabled in (("Mouser", use_mouser), ("DigiKey", use_digikey)) if enabled
    }
    supplier_records = [
        record
        for record in st.session_state.get("component_search_supplier_results", [])
        if record.get("source") in enabled_supplier_labels
    ]

    # Basic Filters -- Manufacturer is now a membership facet (checkbox-
    # style multiselect) across whatever records currently exist, not a
    # free-text exact match, matching the design spec's FilterRail
    # treatment; Storage Space/Location/Project stay PartsBox-only (only
    # that side's records carry them -- a part can sit in several at
    # once, see partsbox_inventory.InventoryPart). Computed from the
    # text-query-filtered (but not yet Basic-Filter-filtered) records, so
    # picking one filter value doesn't hide other values' facet options.
    combined_for_facets = partsbox_records + supplier_records
    with st.expander("Basic Filters", expanded=True):
        stock_filter = st.selectbox(
            "Stock", ["All", "In Stock", "Out of Stock", "Unknown"], key="component_search_stock_filter"
        )
        manufacturer_filters = _membership_facet_filters(
            combined_for_facets, ["manufacturer"], key_prefix="component_search_basic"
        )
        dynamic_filters = render_dynamic_facet_filters(combined_for_facets, key_prefix="component_search")
        partsbox_membership_filters = {}
        if use_partsbox and partsbox_records:
            partsbox_membership_filters = _membership_facet_filters(
                partsbox_records, ["storage_space", "location", "project"], key_prefix="component_search"
            )
        if st.button("Clear All Filters", key="component_search_clear_filters"):
            _clear_component_search_filters()

    characteristics_filters = {}
    if use_partsbox and partsbox_records:
        characteristics_filters = render_component_characteristics(partsbox_records, key_prefix="component_search")

    common_filters = {"stock": stock_filter, **manufacturer_filters, **dynamic_filters}
    partsbox_only_filters = {**partsbox_membership_filters, **characteristics_filters}

    if partsbox_records:
        partsbox_records = search_and_filter(partsbox_records, filters={**common_filters, **partsbox_only_filters})
    if supplier_records:
        supplier_records = search_and_filter(supplier_records, filters=common_filters)

    selected_part = None
    partsbox_signature = result_signature(
        live_text, browse_all, common_filters, partsbox_only_filters, partsbox_snapshot_generation
    )
    supplier_signature = result_signature(st.session_state.get("component_search_last_submitted"), common_filters)

    # If the draft has diverged from the last committed Enter query, OR
    # the checked Sources no longer match what was actually searched
    # (e.g. re-checking Mouser after a DigiKey-only search, without
    # pressing Enter again -- QA/QC deep-dive report, Q6), supplier
    # results stay visible (never cleared/greyed out -- the operator may
    # still want the last search while refining) but get a small
    # staleness caption instead of silently looking current/complete.
    _last_submitted_entry = st.session_state.get("component_search_last_submitted")
    _last_submitted_text = _last_submitted_entry[0] if _last_submitted_entry else None
    _last_submitted_sources = frozenset(_last_submitted_entry[1]) if _last_submitted_entry else frozenset()
    _current_enabled_sources = frozenset(
        source for source, enabled in (("mouser", use_mouser), ("digikey", use_digikey)) if enabled
    )
    _query_diverged = _last_submitted_text is not None and live_text.strip() != _last_submitted_text.strip()
    _sources_diverged = _last_submitted_entry is not None and _current_enabled_sources != _last_submitted_sources
    supplier_results_are_stale = bool(supplier_records and (_query_diverged or _sources_diverged))

    def _render_supplier_results_heading():
        st.markdown("**Supplier Results**")
        if supplier_results_are_stale:
            if _query_diverged and _sources_diverged:
                st.caption(
                    f"Results are for ‘{_last_submitted_text}’ with different sources checked "
                    "— press Enter to update."
                )
            elif _query_diverged:
                st.caption(f"Results are for ‘{_last_submitted_text}’ — press Enter to update.")
            else:
                st.caption(
                    "Sources changed since the last search -- press Enter to fetch results "
                    "for the currently checked sources."
                )

    if use_partsbox and not (use_mouser or use_digikey):
        st.markdown("**PartsBox Inventory**")
        selection = _render_paginated_table(
            partsbox_records,
            key_prefix="component_search_partsbox",
            columns_map=LOOKUP_DISPLAY_COLUMNS,
            signature=partsbox_signature,
            page_size=DISCOVERY_PAGE_SIZE,
            height=DISCOVERY_TABLE_HEIGHT,
        )
        selected_part = selected_part or selection
    elif not use_partsbox and (use_mouser or use_digikey):
        _render_supplier_results_heading()
        selection = _render_paginated_table(
            supplier_records,
            key_prefix="component_search_suppliers",
            columns_map=LOOKUP_DISPLAY_COLUMNS,
            signature=supplier_signature,
            page_size=DISCOVERY_PAGE_SIZE,
            height=DISCOVERY_TABLE_HEIGHT,
        )
        selected_part = selected_part or selection
    elif use_partsbox and (use_mouser or use_digikey):
        left, right = st.columns(2)
        with left:
            st.markdown("**PartsBox Inventory**")
            selection_left = _render_paginated_table(
                partsbox_records,
                key_prefix="component_search_partsbox",
                columns_map=LOOKUP_DISPLAY_COLUMNS,
                signature=partsbox_signature,
                page_size=DISCOVERY_PAGE_SIZE,
                height=DISCOVERY_TABLE_HEIGHT,
            )
        with right:
            _render_supplier_results_heading()
            selection_right = _render_paginated_table(
                supplier_records,
                key_prefix="component_search_suppliers",
                columns_map=LOOKUP_DISPLAY_COLUMNS,
                signature=supplier_signature,
                page_size=DISCOVERY_PAGE_SIZE,
                height=DISCOVERY_TABLE_HEIGHT,
            )
        selected_part = selection_left or selection_right
    else:
        st.warning("Select at least one source (PartsBox, Mouser, or DigiKey).")

    if selected_part is not None:
        st.session_state["component_search_selected_part"] = selected_part

    st.divider()
    render_selected_part_details()


def render_selected_part_details():
    """
    The one shared detail panel every result table (PartsBox side and
    Supplier side alike) populates by row selection -- quantity stepper
    and the single "Add to BOM" button live only here, never duplicated
    per table row. Shows whatever candidate dict was most recently
    selected, persisting across reruns that aren't a new selection
    (typing further, changing an unrelated filter, adjusting the
    quantity itself) so picking a part and then setting its quantity
    doesn't lose the selection.
    """
    candidate = st.session_state.get("component_search_selected_part")
    st.markdown("#### Selected Part Details")
    if candidate is None:
        st.caption("Select a row in a results table above to see its details here.")
        return

    is_partsbox = candidate.get("source") == "PartsBox"
    detail_cols = st.columns([3, 2])
    with detail_cols[0]:
        st.write(f"**{candidate.get('mpn') or '(missing MPN)'}**")
        st.write(f"Source: {candidate.get('source')}")
        st.write(f"Manufacturer: {candidate.get('manufacturer') or 'unknown manufacturer'}")
        st.write(f"Description: {candidate.get('description') or '—'}")
        st.write(f"Category: {candidate.get('category') or '—'} · Package: {candidate.get('package') or '—'}")

        if is_partsbox:
            # Grouped by storage space (Development/Project/Mechanical/
            # Other), never collapsed to one location -- a part can sit
            # in several at once (see partsbox_inventory.InventoryPart).
            locations = candidate.get("locations")
            if locations:
                st.caption("PartsBox locations -- positive current balances only. Read-only.")
                groups = {}
                for loc in locations:
                    groups.setdefault(loc["space_type"], []).append(loc)
                for space_type, group_locations in groups.items():
                    st.write(f"**{space_type}**")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Location": loc["name"],
                                    "Project": loc.get("project_name") or "—",
                                    "Quantity": loc["quantity"],
                                }
                                for loc in group_locations
                            ]
                        ),
                        width="stretch",
                        hide_index=True,
                    )
            else:
                st.caption("No current (positive-quantity) location for this part.")
        else:
            stock_display = candidate.get("stock") if candidate.get("stock") is not None else "Unknown"
            stat_cols = st.columns(3)
            stat_cols[0].metric("Stock", stock_display)
            stat_cols[1].metric("Unit Price", candidate.get("unit_price") or "—")
            stat_cols[2].metric("Supplier P/N", candidate.get("supplier_part_number") or "—")

        # Whatever parametric specs the source actually returned
        # (voltage, tolerance, current, temperature range, ...) -- shown
        # generically rather than a fixed set of expected fields, same
        # as PartsBox's own characteristics; added directly in response
        # to an operator report that Find Replacement gave no way to
        # judge a candidate ("can't make an effective replacement
        # without that"). Absent entirely (not even an empty caption)
        # when the source returned none, rather than implying every
        # candidate has parametric data available.
        characteristics = candidate.get("characteristics")
        if characteristics:
            st.caption("Characteristics (as returned by the source):")
            st.dataframe(
                pd.DataFrame(
                    [{"Attribute": name, "Value": value} for name, value in characteristics.items()]
                ),
                width="stretch",
                hide_index=True,
            )
    with detail_cols[1]:
        qty = st.number_input("Quantity", min_value=1, value=1, step=1, key="component_search_add_qty")
        st.caption("No purchasing action happens here -- this only adds a line to the working BOM.")
        if st.button("Add to BOM", key="component_search_add_button", type="primary"):
            with st.spinner("Adding to working BOM..."):
                _add_search_result_to_working_bom(candidate, int(qty))
            st.toast(f"Added ×{int(qty)} {candidate.get('mpn') or '(missing MPN)'} to the working BOM.")
            # Deliberately no st.rerun() -- this button is ABOVE
            # BOM Configuration/Results in page order, and every
            # section below it (including render_results_workspace()'s
            # results_search text_input) still renders normally
            # later in this SAME script pass, reflecting the new row.
            # An explicit rerun here would abort the script before
            # ever reaching those widgets, which Streamlit then
            # treats as "not present this run" and resets -- silently
            # wiping out things like an already-typed results_search
            # filter (confirmed via a live repro against this exact
            # page/button ordering).


def _add_search_result_to_working_bom(candidate, required_qty):
    """
    Search is allowed to start the working BOM itself, with no upload
    required first (workflow_runner.start_manual_bom_workflow() creates
    an empty, schema-correct one) -- Search is the default/primary
    intake method. Appends a blank line (ActiveBomState.add_row()) with
    just the operator-entered quantity, then reuses
    review_actions.apply_replacement() UNCHANGED to set the component
    identity and run it through the exact same Mouser-first/DigiKey-
    fallback sourcing decision (and PartsBox match recording, if
    discovered via PartsBox) Find Replacement already uses -- there is
    no second "manually added part" sourcing path. Never itself creates
    a Mouser cart or DigiKey cart/MyList.
    """
    if st.session_state.current_run is None:
        st.session_state.current_run = start_manual_bom_workflow()
        reset_run_scoped_session_state()

    current_run = st.session_state.current_run
    active_bom_state = current_run["_active_bom_state"]

    row_id = active_bom_state.add_row({"required_qty": required_qty})
    apply_replacement(active_bom_state, row_id, candidate, sources=_authoritative_sources())
    refresh_response_snapshot(current_run)


def _render_upload_failure_and_retry_button(uploaded_file, errors):
    """
    Shared by both the "just failed this pass" and "already failed on a
    prior pass" branches of render_upload_intake() below, so the Retry
    button appears immediately on the SAME run as the failure (not only
    after some later, unrelated rerun happens to re-render the page).
    Returns whether Retry was clicked.
    """
    st.error(f"'{uploaded_file.name}' could not be processed: " + ("; ".join(errors) or "unknown error"))
    return st.button("Retry Upload", key="upload_intake_retry_button")


def render_upload_intake():
    """
    The SECONDARY way to add parts to the working BOM, beside Search.
    Both feed the exact same canonical ActiveBomState. Uploading while a
    working BOM already exists (started via Search, or a previous
    upload) MERGES this file's cleaned/sourced rows into it
    (ActiveBomState.add_rows()) instead of discarding what's already
    there; uploading as the very first action still creates a new run
    exactly as before -- run_bom_workflow() itself is unchanged either
    way.

    Has no settings of its own -- build quantity, project name/
    description, and whether to update the PartsBox project all live in
    the one shared Configuration section (render_configuration_section()),
    read here via st.session_state rather than duplicated as local
    widgets (see section 16: one sourcing configuration, not
    upload_settings + search_settings). Which suppliers to source
    against is likewise read from the Sources checkboxes next to Search
    (component_search_mouser/component_search_digikey), not a second
    "use Mouser/DigiKey sourcing" toggle.

    Deliberately offers no "Create Mouser cart" / "Create DigiKey
    MyList" option -- neither is part of the normal purchasing handoff
    at all anymore (see render_purchasing_handoff_section()'s DigiKey
    FastAdd cart link + supplier CSVs), and nothing should happen merely
    from an intake upload regardless.

    Automatic, not a "Process Upload" button: processes exactly once per
    distinct dropped/selected file, tracked by Streamlit's own stable
    per-upload UploadedFile.file_id (changes each time a NEW file is
    picked, even a same-named re-drop; stays the same across every
    unrelated rerun of THIS file, e.g. typing in an unrelated widget) in
    upload_intake_processed_file_id below -- an unrelated rerun sees the
    same file_id already recorded and returns without reprocessing.
    """
    st.markdown("#### Upload")
    uploaded_file = st.file_uploader(
        "CSV or XLSX -- click to browse or drag and drop",
        type=["csv", "xlsx"],
        key="upload_intake_file",
    )

    if uploaded_file is None:
        return

    if st.session_state.get("upload_intake_processed_file_id") == uploaded_file.file_id:
        st.caption(f"'{uploaded_file.name}' already processed into the working BOM below.")
        return

    if st.session_state.get("upload_intake_failed_file_id") == uploaded_file.file_id:
        # An early parsing/configuration failure (see below) produced no
        # usable active_bom_state -- this file_id is deliberately NOT
        # marked processed, so it must not be silently reprocessed on
        # every unrelated rerun either (that would repeat the same
        # failing work pointlessly). Only an explicit Retry re-attempts
        # it (QA/QC deep-dive report, Q7).
        failed_errors = st.session_state.get("upload_intake_failed_errors", [])
        if not _render_upload_failure_and_retry_button(uploaded_file, failed_errors):
            return
        st.session_state.pop("upload_intake_failed_file_id", None)
        st.session_state.pop("upload_intake_failed_errors", None)

    build_quantity = st.session_state.cfg_build_quantity
    project_name = st.session_state.cfg_project_name
    project_description = st.session_state.cfg_project_description
    run_partsbox = st.session_state.cfg_update_partsbox_project
    # The Sources checkboxes beside Search are authoritative for
    # the whole sourcing job -- no separate "use Mouser/DigiKey
    # sourcing" toggle for uploads (see render_component_search_intake()).
    authoritative_sources = _authoritative_sources()
    use_mouser_sourcing = "mouser" in authoritative_sources
    use_digikey_sourcing = "digikey" in authoritative_sources
    run_sourcing = use_mouser_sourcing or use_digikey_sourcing

    workspace = build_run_workspace()
    source_path = save_uploaded_file(workspace["input_dir"], uploaded_file.name, uploaded_file.getbuffer())

    with st.spinner(f"Processing '{uploaded_file.name}'..."):
        result = run_bom_workflow(
            source_file_path=source_path,
            build_quantity=int(build_quantity),
            project_name=project_name,
            project_description=project_description,
            run_partsbox=run_partsbox,
            run_sourcing=run_sourcing,
            use_mouser_sourcing=use_mouser_sourcing,
            use_digikey_sourcing=use_digikey_sourcing,
            run_id=workspace["run_id"],
            output_folder=str(workspace["output_dir"]),
        )

    new_state = result.get("_active_bom_state")
    if new_state is None:
        # A parsing/configuration failure this early produced no usable
        # canonical BOM state at all -- must not be marked "processed"
        # (that would silently block an in-place retry until the
        # operator removes and reselects the file just to get a new
        # file_id). See the "upload_intake_failed_file_id" branch above.
        # Rendered here too (not just on a later rerun) so the operator
        # sees the Retry option immediately, on this same failed attempt.
        st.session_state["upload_intake_failed_file_id"] = uploaded_file.file_id
        st.session_state["upload_intake_failed_errors"] = result.get("errors", [])
        _render_upload_failure_and_retry_button(uploaded_file, result.get("errors", []))
        return

    st.session_state["upload_intake_processed_file_id"] = uploaded_file.file_id

    if run_partsbox:
        # A confirmed AutoBOM PartsBox write (project/storage creation +
        # BOM-entry sync) just happened -- the shared snapshot
        # (partsbox_inventory.get_snapshot(), used by Main Search/
        # PartsBox Inventory/Needs Review/the location recommender) can
        # no longer be trusted as current, so drop it; the next read
        # re-fetches instead of quietly serving pre-write data for up to
        # its 5-minute TTL.
        invalidate_partsbox_snapshot()

    existing_run = st.session_state.current_run
    existing_state = existing_run.get("_active_bom_state") if existing_run else None

    if existing_state is not None and new_state is not None:
        # A working BOM already exists -- merge this file's
        # rows into it rather than replacing current_run, so
        # parts added via Search (or a previous upload) survive.
        existing_state.add_rows(new_state.dataframe)
        existing_run["messages"] = existing_run.get("messages", []) + result.get("messages", [])
        existing_run["warnings"] = existing_run.get("warnings", []) + result.get("warnings", [])
        existing_run["errors"] = existing_run.get("errors", []) + result.get("errors", [])
        refresh_response_snapshot(existing_run)
    else:
        # Nothing to merge into -- this becomes the run, exactly
        # as a plain upload always has.
        st.session_state.current_run = result
        reset_run_scoped_session_state()

        # Deliberately no st.rerun() -- see the matching comment in
        # render_selected_part_details(). Everything below this point in
        # the page (BOM Configuration, Results, Purchasing Handoff)
        # still renders normally later in this SAME script pass and
        # reflects the merged/replaced state; an explicit rerun here
        # would abort the script before reaching those widgets and
        # reset them.


def render_run_messages(current_run):
    if current_run.get("success"):
        st.success("BOM automation completed.")
    else:
        st.warning("BOM automation finished with errors.")

    for error in current_run.get("errors", []):
        st.error(error)

    for message in current_run.get("messages", []):
        st.info(message)

    warnings = current_run.get("warnings", [])
    if warnings:
        with st.expander(f"Warnings ({len(warnings)})"):
            for warning in warnings:
                st.write(warning)


def render_downloads(current_run):
    """
    "Other Outputs" -- the non-supplier-specific artifacts, generalized
    per the frontend design spec's otherOutputs[] list. Excludes both
    mouser_export_csv and digikey_list_csv, each shown inline in its own
    supplier panel in render_purchasing_handoff_section() with its own
    bespoke button -- not duplicated here.
    """
    st.subheader("Other Outputs")

    artifact_status = current_run.get("artifact_status") or {}
    if bool(current_run.get("stale_after_mutation")):
        st.warning(
            "A Needs Review action changed the BOM since some of these files were "
            "generated. Files marked stale below are disabled until they're "
            "regenerated so nobody hands purchasing a BOM file that doesn't match "
            "what Results now shows. Click Regenerate Purchasing in Purchasing "
            "Handoff to update them."
        )

    outputs = current_run.get("outputs", {})
    download_labels = {
        "cleaned_workbook": "Download cleaned workbook",
        "cleaned_csv": "Download cleaned CSV",
        "sourcing_report": "Download sourcing report",
        "partsbox_import_csv": "Download PartsBox import CSV",
        "partsbox_unmatched_csv": "Download PartsBox unmatched CSV",
        "run_summary": "Download run summary",
    }
    stale_status_labels = {
        "stale": "(stale — regenerate to update)",
        "failed": "(last generation attempt failed)",
    }

    for key, label in download_labels.items():
        status = artifact_status.get(key)
        suffix = stale_status_labels.get(status, "")
        full_label = f"{label} {suffix}".strip()
        show_download(full_label, outputs.get(key), disabled=status in ("stale", "failed"))


def render_results_workspace(current_run):
    """
    Working Parts List and Needs Review are two separate, always-visible
    sections now (no "All Results"/"Needs Review (N)" tabs) -- per the
    frontend design spec, Needs Review is its own master-detail area, not
    one tab among the working BOM's results.
    """
    active_bom_state = current_run.get("_active_bom_state")
    if active_bom_state is None:
        return

    run_info = current_run.get("run", {})
    title = run_info.get("project_name") or run_info.get("source_file_name") or "Run"
    st.subheader(f"AutoBOM Results — {title}")

    render_working_parts_list(current_run, active_bom_state)

    st.divider()
    render_needs_review_section(current_run, active_bom_state)


def _options(rows, field):
    values = sorted({row.get(field) for row in rows if row.get(field)})
    return ["All"] + values


def render_working_parts_list(current_run, active_bom_state):
    """
    The canonical working BOM, with its own presentation-only pagination
    (WORKING_LIST_PAGE_SIZE, independent of the actual BOM size -- a
    5-line and a 500-line BOM render the same list height) and an
    inline-editable Customer Reference cell directly in the grid
    (st.data_editor with every other column disabled -- the native
    equivalent of the design spec's editable grid cell; Streamlit has no
    commit-on-blur, so an edit commits on the next rerun instead, noted
    as a simplification). Pagination never mutates ActiveBomState --
    slicing happens after search_and_filter(), same "filter before
    paginate" rule every other table in this app follows.
    """
    st.markdown("#### Working Parts List")

    summary = active_bom_state.summary_counts()
    count_cols = st.columns(4)
    count_cols[0].metric("PartsBox", summary["partsbox"])
    count_cols[1].metric("Mouser", summary["mouser"])
    count_cols[2].metric("DigiKey", summary["digikey"])
    count_cols[3].metric("Needs Review", summary["needs_review"])

    st.text_input("Search working parts...", key="results_search")

    rows = active_bom_state.rows()
    filter_cols = st.columns(2)
    with filter_cols[0]:
        st.selectbox("Source", _options(rows, "source"), key="results_filter_source")
    with filter_cols[1]:
        st.selectbox("Status", _options(rows, "result_status"), key="results_filter_status")

    filters = {
        "source": st.session_state.results_filter_source,
        "result_status": st.session_state.results_filter_status,
    }
    query_text = st.session_state.get("results_search", "")
    filtered_rows = search_and_filter(
        rows, query_text=query_text, search_fields=RESULTS_SEARCH_FIELDS, filters=filters
    )

    if not filtered_rows:
        st.info("No results match the current search/filters.")
        return

    # Page-state math happens here (signature tracking/clamping), but the
    # Prev/Next UI itself renders AFTER the table below -- per direct
    # operator feedback that it read as belonging above a different
    # section when it sat above this list.
    signature = result_signature(query_text, filters)
    sig_key = "working_parts_list_page_sig"
    page_key = "working_parts_list_page_num"
    if st.session_state.get(sig_key) != signature:
        st.session_state[sig_key] = signature
        st.session_state[page_key] = 1
    total_pages = total_pages_for(len(filtered_rows), page_size=WORKING_LIST_PAGE_SIZE)
    current_page = clamp_page(st.session_state.get(page_key, 1), total_pages)
    st.session_state[page_key] = current_page

    page = paginate(filtered_rows, page=current_page, page_size=WORKING_LIST_PAGE_SIZE)

    table_df = pd.DataFrame(page.items)
    available_columns = [col for col in RESULTS_DISPLAY_COLUMNS if col in table_df.columns]
    display_df = table_df[available_columns].rename(columns=RESULTS_DISPLAY_COLUMNS)

    edited_df = st.data_editor(
        display_df,
        width="stretch",
        height=WORKING_LIST_TABLE_HEIGHT,
        hide_index=True,
        disabled=[col for col in display_df.columns if col != "Customer Reference"],
        # Explicit per-column width hints so columns keep a readable
        # size and the grid scrolls horizontally for the rest instead of
        # auto-compressing every column to fit the container width.
        column_config={
            "Description": st.column_config.TextColumn(width="large"),
            "Manufacturer Part Number": st.column_config.TextColumn(width="medium"),
            "Manufacturer": st.column_config.TextColumn(width="medium"),
            "Designators": st.column_config.TextColumn(width="medium"),
            "Customer Reference": st.column_config.TextColumn(width="medium"),
            "Supplier Part Number": st.column_config.TextColumn(width="medium"),
            "Review Reason": st.column_config.TextColumn(width="large"),
        },
        key="working_parts_list_editor",
    )

    if "Customer Reference" in edited_df.columns:
        for position, edited_value in enumerate(edited_df["Customer Reference"]):
            original_row = page.items[position]
            new_value = str(edited_value or "").strip()
            if new_value != (original_row.get("customer_reference", "") or ""):
                active_bom_state.update_row(original_row["row_id"], {"customer_reference": new_value})
                refresh_response_snapshot(current_run)

    if total_pages > 1:
        nav_cols = st.columns([1, 3, 1])
        with nav_cols[0]:
            if st.button("< Prev", key="working_parts_list_prev_page", disabled=current_page <= 1):
                st.session_state[page_key] = current_page - 1
        with nav_cols[1]:
            st.caption(f"Page {current_page} of {total_pages} · {len(filtered_rows)} result(s)")
        with nav_cols[2]:
            if st.button("Next >", key="working_parts_list_next_page", disabled=current_page >= total_pages):
                st.session_state[page_key] = current_page + 1
    else:
        st.caption(f"{len(filtered_rows)} result(s)")


def render_needs_review_section(current_run, active_bom_state):
    """
    Master-detail layout (a fixed-narrow list column + a wider detail
    pane), replacing the old per-row st.expander list, per the frontend
    design spec's NeedsReview component. Selecting a different row clears
    any open replacement-search panel for the previously active row (the
    design spec's onSelectItem resetting `replacement: null`) -- tracked
    via a shadow "last shown" key since Streamlit's own radio widget only
    exposes the current value, not whether this run's value differs from
    the previous run's.
    """
    review_rows = active_bom_state.review_items()
    st.markdown("#### Needs Review")
    if not review_rows:
        st.success("Nothing currently needs review.")
        return

    labels = {
        row["row_id"]: f"{row.get('mpn') or '(missing MPN)'} — {row.get('manufacturer') or '(unknown manufacturer)'}"
        for row in review_rows
    }
    options = list(labels.keys())
    if st.session_state.get("selected_review_row_id") not in options:
        st.session_state["selected_review_row_id"] = options[0]

    list_col, detail_col = st.columns([1, 3])
    with list_col:
        selected_row_id = st.radio(
            "Needs Review items",
            options,
            format_func=lambda rid: labels[rid],
            key="selected_review_row_id",
            label_visibility="collapsed",
        )

    if st.session_state.get("_needs_review_shown_row_id") != selected_row_id:
        st.session_state["_needs_review_shown_row_id"] = selected_row_id
        st.session_state["replacement_panel_open"] = False

    with detail_col:
        active_row = next(row for row in review_rows if row["row_id"] == selected_row_id)
        row_id = active_row["row_id"]
        st.write(
            f"**{active_row.get('mpn') or '(missing MPN)'}** — "
            f"{active_row.get('manufacturer') or '(unknown manufacturer)'}"
        )
        st.write(f"Designators: {active_row.get('designators', '') or '—'}")
        st.write(f"Current status: {active_row.get('result_status')}")
        st.write(f"Reason: {active_row.get('review_reason') or 'Needs review'}")
        st.caption(
            "Stays here -- and keeps being sourceable via Retry Exact / Find Replacement -- "
            "until a match is found or a replacement is applied."
        )

        action_cols = st.columns(4)

        if action_cols[0].button("Retry Exact Part", key=f"retry_{row_id}"):
            with st.spinner("Retrying exact part lookup..."):
                retry_exact_sourcing(active_bom_state, row_id, sources=_authoritative_sources())
            refresh_response_snapshot(current_run)
            st.rerun()

        if action_cols[1].button("Find Replacement", key=f"find_replacement_{row_id}"):
            # The authoritative Sources checkboxes must govern which
            # suppliers Find Replacement searches too -- not just which
            # suppliers apply_replacement()'s later re-sourcing pass may
            # use. Previously this always searched both Mouser and
            # DigiKey regardless of what was checked (see the QA/QC
            # deep-dive report's Q5).
            st.session_state.replacement_lookup_sources = frozenset(
                source for source in _authoritative_sources() if source in {"mouser", "digikey"}
            )
            st.session_state["replacement_panel_open"] = True

        if action_cols[2].button("Check PartsBox", key=f"check_partsbox_{row_id}"):
            st.session_state.replacement_lookup_sources = frozenset({"partsbox"})
            st.session_state["replacement_panel_open"] = True

        if action_cols[3].button("Mark DNP", key=f"mark_dnp_{row_id}"):
            # Do Not Populate -- an explicit "stop tracking this line"
            # decision, distinct from resolving it via Retry/Replacement.
            # Immediately drops it out of review_items() (see
            # active_bom_state._needs_review()'s dnp check), so it no
            # longer blocks Regenerate Purchasing.
            active_bom_state.mark_as_dnp(row_id)
            refresh_response_snapshot(current_run)
            st.session_state["replacement_panel_open"] = False
            st.session_state.pop(f"replacement_results_{row_id}", None)
            st.session_state.pop(f"replacement_selected_{row_id}", None)
            # Not touching st.session_state.selected_review_row_id here --
            # see the matching comment in render_replacement_lookup()'s
            # "Use Selected Replacement" handler; it's a real widget key
            # already instantiated earlier in this same pass.
            st.rerun()

        if st.session_state.get("replacement_panel_open"):
            render_replacement_lookup(current_run, active_bom_state, row_id)


def render_replacement_lookup(current_run, active_bom_state, row_id):
    """
    Find Replacement / Check PartsBox share this exact function, and
    both prepopulate a LookupQuery from what AutoBOM already knows about
    the row (component_lookup.build_query_from_bom_row). Check PartsBox
    (sources == {"partsbox"}) filters the same shared snapshot
    (partsbox_inventory.get_snapshot()) Main Search/PartsBox Inventory/
    the location recommender use -- the audit's "one shared PartsBox
    snapshot" precondition applies here too, not just to Main Search --
    rather than a second live-per-search PartsBox read. Find Replacement
    (Mouser/DigiKey) still calls search_components(), the same lookup
    Main Search's Enter-triggered supplier query uses; there is still
    only one Mouser/DigiKey lookup implementation, just not the shared
    snapshot (Mouser/DigiKey have no such snapshot -- they're queried
    live, on this explicit Search click, same as always).
    """
    row = active_bom_state.get_row(row_id)
    sources = st.session_state.replacement_lookup_sources

    if sources != frozenset({"partsbox"}):
        # Reconcile against the Sources checkboxes on every rerun, not
        # just at the moment "Find Replacement" was clicked: if the
        # operator toggles Mouser/DigiKey while this panel is already
        # open, any previously fetched candidates from a supplier that's
        # now disabled must not remain displayed/selectable (QA/QC
        # deep-dive report, Q5's "toggling sources ... clears incompatible
        # results and selection" requirement). Check PartsBox's fixed
        # {"partsbox"} sources are a separate flow, not gated by these
        # checkboxes at all.
        current_external_sources = frozenset(
            source for source in _authoritative_sources() if source in {"mouser", "digikey"}
        )
        if sources != current_external_sources:
            st.session_state.replacement_lookup_sources = current_external_sources
            st.session_state.pop(f"replacement_results_{row_id}", None)
            st.session_state.pop(f"replacement_selected_{row_id}", None)
            sources = current_external_sources

        if not sources:
            st.warning(
                "No external supplier is selected. Check Mouser and/or DigiKey above, "
                "then click Find Replacement again."
            )
            return

    query = build_query_from_bom_row(row, sources=sources)

    source_label = ", ".join(sorted(source.title() for source in sources))
    st.caption(f"Searching {source_label} for a replacement for {row.get('mpn') or '(missing MPN)'}.")

    search_key = f"replacement_query_{row_id}"
    if search_key not in st.session_state:
        st.session_state[search_key] = query.mpn or query.keywords

    # Two one-click alternatives instead of requiring the operator to
    # erase the known MPN by hand: the MPN stays available for an exact
    # retry-style search, and the description offers a route to
    # alternatives without retyping anything AutoBOM already knows.
    quick_cols = st.columns(2)
    if row.get("mpn") and quick_cols[0].button(f"Search MPN: {row['mpn']}", key=f"search_by_mpn_{row_id}"):
        st.session_state[search_key] = row["mpn"]
    if row.get("description") and quick_cols[1].button(
        f"Search description instead: {row['description']}", key=f"search_by_desc_{row_id}"
    ):
        st.session_state[search_key] = row["description"]

    search_value = st.text_input("MPN / keywords (loosen or tighten as needed)", key=search_key)

    if st.button("Search", key=f"do_replacement_search_{row_id}"):
        if sources == frozenset({"partsbox"}):
            try:
                snapshot = get_partsbox_snapshot()
            except Exception as exc:
                st.error(f"Could not load PartsBox inventory: {exc}")
            else:
                all_partsbox_records = [part.to_dict() for part in snapshot.parts]
                manufacturer_filters = {"manufacturer": query.manufacturer} if query.manufacturer else {}
                results = search_and_filter(
                    all_partsbox_records,
                    query_text=search_value,
                    search_fields=["mpn", "manufacturer", "description"],
                    filters=manufacturer_filters,
                )
                required_qty = parse_engineering_value(row.get("required_qty"))
                for candidate in results:
                    stock = candidate.get("stock")
                    if required_qty is None or stock is None:
                        candidate["stock_sufficient"] = None
                    else:
                        candidate["stock_sufficient"] = float(stock) >= required_qty
                st.session_state[f"replacement_results_{row_id}"] = results
        else:
            query.mpn = search_value
            query.keywords = search_value
            replacement_search_errors = []
            with st.spinner("Searching..."):
                st.session_state[f"replacement_results_{row_id}"] = search_components(
                    query, errors=replacement_search_errors
                )
            # Free-text (e.g. "Search description instead" against
            # Mouser/DigiKey, which only implement a strict part-number
            # search) can fail without taking down the whole page or the
            # other supplier's results -- see search_components()'s
            # per-source isolation.
            for failed_source, message in replacement_search_errors:
                st.warning(f"{failed_source.title()} search failed: {message}")

    results = st.session_state.get(f"replacement_results_{row_id}", [])
    if not results:
        st.info("No candidates yet. Adjust the query above and click Search.")
        return

    # Same paginated/selectable table Main Search and PartsBox Inventory
    # use (_render_paginated_table), namespaced by row_id so each open
    # Needs Review row keeps its own page/selection state independent of
    # every other row's replacement search -- not a second presentation.
    columns_map = dict(LOOKUP_DISPLAY_COLUMNS)
    if any(candidate.get("stock_sufficient") is not None for candidate in results):
        columns_map = {**columns_map, "stock_sufficient": "Covers Required Qty?"}

    selection = _render_paginated_table(
        results,
        key_prefix=f"replacement_{row_id}",
        columns_map=columns_map,
        signature=result_signature(search_value, tuple(sorted(sources))),
    )
    if selection is not None:
        st.session_state[f"replacement_selected_{row_id}"] = selection

    selected_candidate = st.session_state.get(f"replacement_selected_{row_id}")
    if selected_candidate is not None:
        st.caption(
            f"Selected: {selected_candidate.get('source')} · {selected_candidate.get('mpn')} · "
            f"{selected_candidate.get('manufacturer') or 'unknown manufacturer'}"
        )
        if st.button("Use Selected Replacement", key=f"use_replacement_{row_id}", type="primary"):
            with st.spinner("Re-sourcing replacement..."):
                apply_replacement(
                    active_bom_state, row_id, selected_candidate, sources=_authoritative_sources()
                )
            refresh_response_snapshot(current_run)
            # Not touching st.session_state.selected_review_row_id here --
            # it's now a real widget key (the master-detail list's
            # st.radio in render_needs_review_section()), already
            # instantiated earlier in this same script pass by the time
            # this handler runs; writing to it now would raise
            # StreamlitWidgetAlreadyInstantiatedError. The row this
            # applied to naturally drops out of review_items() (it's no
            # longer Needs Review), and render_needs_review_section()'s
            # own pre-clamp picks a fresh valid selection before the
            # radio re-instantiates on the rerun below.
            st.session_state["replacement_panel_open"] = False
            st.session_state.pop(f"replacement_results_{row_id}", None)
            st.session_state.pop(f"replacement_selected_{row_id}", None)
            st.rerun()


def render_dynamic_facet_filters(results, key_prefix):
    """
    Main Search's Basic Filters: builds filter widgets only for facets
    that actually have data in the current result set
    (record_filter.generate_facets), instead of a fixed list of
    often-empty filters. Categorical facets (category, package, ...) get
    an exact-match selectbox; numeric facets (voltage, tolerance, ...)
    get min/max range inputs parsed through engineering_units. Returns a
    filters dict ready for record_filter.search_and_filter().
    """
    filters = {}

    categorical_facets = generate_facets(results, CATEGORICAL_FACET_FIELDS)
    if categorical_facets:
        facet_cols = st.columns(len(categorical_facets))
        for col, (field, values) in zip(facet_cols, categorical_facets.items()):
            with col:
                selection = st.selectbox(
                    field.replace("_", " ").title(), ["All"] + values, key=f"{key_prefix}_facet_{field}"
                )
                filters[field] = selection

    range_facets = generate_facets(results, RANGE_FACET_FIELDS)
    if range_facets:
        st.caption("Range filters (values shown in the current results):")
        for field in range_facets:
            range_cols = st.columns(2)
            with range_cols[0]:
                min_value = st.text_input(
                    f"Min {field}", key=f"{key_prefix}_range_min_{field}", placeholder="e.g. 10uF"
                )
            with range_cols[1]:
                max_value = st.text_input(
                    f"Max {field}", key=f"{key_prefix}_range_max_{field}", placeholder="e.g. 25V"
                )
            parsed_min = parse_engineering_value(min_value) if min_value else None
            parsed_max = parse_engineering_value(max_value) if max_value else None
            if min_value and parsed_min is None:
                st.warning(f"Could not parse Min {field} value '{min_value}' -- not applied.")
            if max_value and parsed_max is None:
                st.warning(f"Could not parse Max {field} value '{max_value}' -- not applied.")
            if parsed_min is not None or parsed_max is not None:
                filters[field] = {"min": parsed_min, "max": parsed_max}

    return filters


def _apply_customer_reference_to_all(current_run, active_bom_state, value):
    for row in active_bom_state.rows():
        active_bom_state.update_row(row["row_id"], {"customer_reference": value})
    # Same mutation seam Retry Exact/Find Replacement use: marks
    # regeneratable purchasing artifacts (including the DigiKey cart
    # link) stale so a CSV/link already generated under the OLD
    # reference isn't silently handed off as current. Never itself calls
    # a vendor -- neither this nor Regenerate Purchasing makes a live
    # vendor call at all in the normal flow.
    refresh_response_snapshot(current_run)


def _render_customer_reference_preview_and_apply(current_run, active_bom_state, preview, key_prefix):
    """
    The type/project/PCB/R&D picker and this preview/validity check work
    with no working BOM yet -- an operator can configure the reference
    from the start, before adding any parts (matches the mockup's plain,
    always-editable "Customer part number" field). Only "Apply to All
    BOM Lines" itself needs actual rows to write to, so only that
    specific action is guarded/disabled here, with an explicit reason
    -- the picker/preview above it are never gated.
    """
    result = validate_customer_reference(preview)
    if result.valid:
        st.success(f"{result.value}  —  {result.length} / {CUSTOMER_REFERENCE_MAX_LENGTH} characters  ✓ Valid")
    else:
        st.error(
            f"{result.value}  —  {result.length} / {CUSTOMER_REFERENCE_MAX_LENGTH} characters\n"
            + "\n".join(f"✗ {error}" for error in result.errors)
        )

    has_bom = active_bom_state is not None
    if st.button(
        "Apply to All BOM Lines", key=f"{key_prefix}_apply_all", disabled=not (result.valid and has_bom)
    ):
        _apply_customer_reference_to_all(current_run, active_bom_state, result.value)
        st.success(f"Applied {result.value} to every BOM line.")
    if result.valid and not has_bom:
        st.caption("Add parts to the working BOM to apply this reference.")
        # Deliberately no st.rerun() -- Customer Reference is nested in
        # the shared Configuration section, positioned before Results in
        # page order (see render_configuration_section()). Results
        # (including its results_search text_input) still renders normally later in
        # this SAME script pass, showing the newly applied reference; an
        # explicit rerun here would abort the script before reaching it
        # and reset it (see the matching comment in
        # render_add_to_bom_results()).


def _render_project_pcb_reference(current_run, active_bom_state):
    try:
        projects = get_projects()
        pcb_codes = get_pcb_codes()
    except RegistryError as exc:
        st.error(f"Customer Reference registry error: {exc}")
        return

    project_options = sorted(projects.keys())
    pcb_options = sorted(pcb_codes.keys())
    if not project_options or not pcb_options:
        st.warning("No approved Project or PCB codes in the registry yet. Add one below.")
        return

    cols = st.columns(2)
    with cols[0]:
        project = st.selectbox(
            "Project",
            project_options,
            key="cref_project",
            format_func=lambda code: f"{code} — {projects.get(code, '')}",
        )
    with cols[1]:
        selected_pcbs = st.multiselect(
            "PCB Code(s)",
            pcb_options,
            key="cref_pcb_codes",
            format_func=lambda code: f"{code} — {pcb_codes.get(code, '')}",
        )

    if not selected_pcbs:
        st.info("Select at least one PCB code to generate a reference.")
        return

    preview = build_project_reference(project, selected_pcbs)
    _render_customer_reference_preview_and_apply(current_run, active_bom_state, preview, "cref_prj")


def _render_rnd_reference(current_run, active_bom_state):
    try:
        projects = get_projects()
    except RegistryError as exc:
        st.error(f"Customer Reference registry error: {exc}")
        return

    project_options = sorted(projects.keys())
    if not project_options:
        st.warning("No approved Project codes in the registry yet. Add one below.")
        return

    cols = st.columns(2)
    with cols[0]:
        project = st.selectbox(
            "Project",
            project_options,
            key="cref_rnd_project",
            format_func=lambda code: f"{code} — {projects.get(code, '')}",
        )
    with cols[1]:
        # Deliberately free text, not a fixed registry -- staff/owners
        # change over time and are not an "approved code" concept.
        owner = st.text_input("Owner", key="cref_owner")

    if not owner.strip():
        st.info("Enter an owner to generate a reference.")
        return

    preview = build_rnd_reference(project, owner)
    _render_customer_reference_preview_and_apply(current_run, active_bom_state, preview, "cref_rnd")


def _render_inventory_reference(current_run, active_bom_state):
    """
    Evaluated per BOM line, not one part picked from a dropdown --
    recommend_location() (PartsBox-ledger-based: exact part match first,
    similarity scoring as a fallback) is the same recommender used
    before, just called once per row in the CURRENT BOM instead of only
    for a single manually-selected row, and shown as one table the
    operator can accept or override per line. Only runs on an explicit
    button click -- selecting "Inventory" above never triggers this by
    itself, since it's one PartsBox read per BOM line.

    Inherently needs actual BOM rows to recommend locations for -- this
    is the one Customer Reference mode that genuinely can't be
    configured before parts exist (contrast Project/PCB and R&D, whose
    picker/preview work with no BOM at all).
    """
    if active_bom_state is None:
        st.info("Add parts to the working BOM first, then generate location recommendations here.")
        return

    rows = active_bom_state.rows()
    if not rows:
        st.info("No BOM lines to assign.")
        return

    if st.button("Get Recommendations for All Parts", key="cref_inventory_recommend_all"):
        with st.spinner("Checking PartsBox for existing/similar placement for every BOM line..."):
            st.session_state["cref_inventory_recommendations"] = {
                row["row_id"]: recommend_location(
                    mpn=row.get("mpn", ""),
                    manufacturer=row.get("manufacturer", ""),
                    description=row.get("description", ""),
                )
                for row in rows
            }

    recommendations = st.session_state.get("cref_inventory_recommendations")
    if not recommendations:
        st.caption(
            "Click 'Get Recommendations for All Parts' to see a suggested storage "
            "location for every BOM line."
        )
        return

    try:
        storage_response = PartsBoxClient().list_storage_locations()
        storage_names = sorted(
            {
                storage.get("storage/name", "")
                for storage in storage_response.get("data", [])
                if isinstance(storage, dict) and storage.get("storage/name")
            }
        )
    except Exception as exc:
        storage_names = []
        st.warning(f"Could not load PartsBox storage locations for manual selection: {exc}")

    header_cols = st.columns([3, 2, 3, 2, 1])
    for col, heading in zip(header_cols, ["Part", "Match", "Reason", "Location", ""]):
        col.markdown(f"**{heading}**")

    for row in rows:
        row_id = row["row_id"]
        recommendation = recommendations.get(row_id)
        if recommendation is None:
            continue

        label = f"{row.get('mpn') or '(missing MPN)'} — {row.get('manufacturer', '') or '(unknown manufacturer)'}"
        cols = st.columns([3, 2, 3, 2, 1])
        cols[0].write(label)
        cols[1].write(recommendation.confidence)
        cols[2].write(recommendation.reason)

        options = [recommendation.location] if recommendation.location else []
        options.extend(name for name in storage_names if name != recommendation.location)

        with cols[3]:
            if options:
                chosen_location = st.selectbox(
                    "Location",
                    options,
                    key=f"cref_inv_location_{row_id}",
                    label_visibility="collapsed",
                )
            else:
                chosen_location = st.text_input(
                    "Location",
                    value=recommendation.location or "",
                    key=f"cref_inv_location_text_{row_id}",
                    label_visibility="collapsed",
                )

        with cols[4]:
            if st.button("Save", key=f"cref_inv_save_{row_id}", disabled=not chosen_location):
                preview = build_inventory_reference(chosen_location)
                result = validate_customer_reference(preview)
                if not result.valid:
                    st.error("; ".join(result.errors))
                else:
                    # Inventory reference assignment only writes the
                    # canonical customer_reference field -- it never
                    # triggers a PartsBox stock-movement/relocation
                    # operation. Assigning a Customer Reference and
                    # moving physical/PartsBox stock are different
                    # actions.
                    active_bom_state.update_row(row_id, {"customer_reference": result.value})
                    refresh_response_snapshot(current_run)
                    st.success(f"Saved {result.value} for this line.")
                    # Deliberately no st.rerun() -- same reasoning as
                    # "Apply to All BOM Lines" above: this section is
                    # positioned before Results in page order, and
                    # Results still renders normally later in this SAME
                    # pass.


def _render_customer_reference_overrides(current_run, active_bom_state):
    if active_bom_state is None:
        st.caption("No BOM lines yet.")
        return

    rows = active_bom_state.rows()
    if not rows:
        st.caption("No BOM lines.")
        return

    for row in rows:
        row_id = row["row_id"]
        label = f"{row.get('mpn') or '(missing MPN)'} — {row.get('manufacturer', '') or '(unknown manufacturer)'}"
        cols = st.columns([3, 3, 1])
        cols[0].write(label)
        new_value = cols[1].text_input(
            "Reference",
            value=row.get("customer_reference", "") or "",
            key=f"cref_override_{row_id}",
            label_visibility="collapsed",
        )
        if cols[2].button("Save", key=f"cref_override_save_{row_id}"):
            normalized = new_value.strip().upper()
            if normalized:
                result = validate_customer_reference(normalized)
                if not result.valid:
                    st.error("; ".join(result.errors))
                    continue
                normalized = result.value
            active_bom_state.update_row(row_id, {"customer_reference": normalized})
            refresh_response_snapshot(current_run)
            st.rerun()


def _render_add_approved_code():
    with st.expander("+ Add Approved Project or PCB Code"):
        st.caption(
            "Today's codes are the current approved registry, not a permanent "
            "list -- add a new one here as projects/boards are approved. See "
            "config/customer_reference_registry.json."
        )
        code_type = st.radio(
            "Type", ["Project Code", "PCB Code"], key="cref_add_type", horizontal=True
        )
        code = st.text_input("Code (uppercase letters/digits only)", key="cref_add_code")
        description = st.text_input("Description", key="cref_add_description")
        if st.button("Save New Code", key="cref_add_save"):
            try:
                if code_type == "Project Code":
                    add_project(code, description)
                else:
                    add_pcb_code(code, description)
            except RegistryError as exc:
                st.error(str(exc))
            else:
                st.success(f"Added {code.strip().upper()!r} to the approved registry.")
                st.rerun()


def render_customer_reference_summary(current_run, active_bom_state):
    """
    Configuration's compact Customer Reference control -- the one
    thing in Configuration that's ALWAYS visible (per the interaction
    spec's §8: "shows the currently-applied reference (or 'Set once
    parts are added' before a BOM exists) plus a validity chip and an
    'Edit ▾' affordance... Disabled/hinted, not clickable, until a BOM
    exists"), not something that disappears entirely with no working
    BOM -- a prior version of this gated the whole control behind
    `current_run is not None`, which silently dropped the only
    Configuration-card control replacing the mockup's plain "Customer
    part number" field whenever the page was still blank.

    A one-line summary of whatever reference the working BOM currently
    carries (the first row's value stands in for "the BOM's" reference,
    same as the design spec's crefSummary), plus an "Edit Customer
    Reference" trigger that opens the full generator/override UI in a
    st.popover() rather than as an always-expanded inline section --
    matches the frontend design spec's CustomerReferenceEditor being a
    popover anchored off Configuration, not a permanent page section.
    `current_run`/`active_bom_state` are None before any BOM exists.
    """
    has_bom = current_run is not None and active_bom_state is not None
    current_value = ""
    if has_bom:
        rows = active_bom_state.rows()
        current_value = (rows[0].get("customer_reference") or "").strip() if rows else ""

    summary_cols = st.columns([3, 1])
    with summary_cols[0]:
        if not has_bom:
            st.caption("Customer Reference: configure now, apply once parts are added.")
        elif current_value:
            result = validate_customer_reference(current_value)
            status = "valid" if result.valid else "invalid"
            st.write(f"**Customer Reference:** {current_value} ({status})")
        else:
            st.caption("Customer Reference: not set yet.")
    with summary_cols[1]:
        # The popover itself is never disabled -- Project/PCB and R&D
        # references can be picked/previewed before any BOM exists (the
        # operator asked for this explicitly: "it should be able to be
        # configured from the start"). Only the specific actions that
        # need actual rows (Apply to All, per-line overrides, Inventory
        # recommendations) are individually guarded inside the section
        # -- see _render_customer_reference_preview_and_apply(),
        # _render_inventory_reference(), _render_customer_reference_overrides().
        with st.popover("Edit Customer Reference", width="stretch"):
            render_customer_reference_section(current_run, active_bom_state)


def render_customer_reference_section(current_run, active_bom_state):
    """
    Customer Reference / Customer Part Number assignment (Yank naming
    convention, YT-SOP-00-01-A) -- feeds the Mouser CSV / DigiKey cart
    link+CSV / export handoff, never an order. Rendered inside the
    st.popover() render_customer_reference_summary() opens, not as a
    permanent Configuration section.
    """
    st.subheader("Customer Reference")
    st.caption(
        "Sets the Customer Reference / Customer Part Number used on Mouser "
        "and DigiKey orders. AutoBOM prepares this field; purchasing still "
        "completes checkout manually outside AutoBOM."
    )

    st.radio(
        "Reference Type",
        ["Project / PCB", "Inventory", "R&D"],
        key="cref_reference_type",
        horizontal=True,
    )
    reference_type = st.session_state["cref_reference_type"]

    if reference_type == "Project / PCB":
        _render_project_pcb_reference(current_run, active_bom_state)
    elif reference_type == "R&D":
        _render_rnd_reference(current_run, active_bom_state)
    else:
        _render_inventory_reference(current_run, active_bom_state)

    with st.expander("Override individual lines"):
        _render_customer_reference_overrides(current_run, active_bom_state)

    _render_add_approved_code()


def _apply_build_quantity(current_run, active_bom_state, new_build_quantity):
    """
    Recomputes required_qty using the exact same pure function
    (bom_cleaner.apply_project_quantities()) Upload's initial processing
    uses -- not a second quantity-math implementation -- then writes
    each row's recomputed fields back through ActiveBomState.update_row(),
    the one shared mutation seam. A changed required_qty can make an old
    sourcing decision wrong (a supplier that covered the old quantity may
    not cover the new one, or a different candidate/stock split may now
    apply) -- so every affected row is also re-sourced through the same
    shared retry_exact_sourcing() seam Retry Exact uses, honoring the
    current authoritative Sources selection, rather than leaving the old
    selected_supplier/supplier_order_qty/stock fields stale and
    misreporting Ready. See the QA/QC deep-dive report's Q2.

    Only touches rows that actually have a qty_per_board (i.e. came from
    an uploaded file): a row added manually via Search has no per-board
    quantity to multiply -- its required_qty was entered directly at Add
    time and must not be silently overwritten by a build-quantity
    multiplier that doesn't apply to it.
    """
    recomputed = apply_project_quantities(active_bom_state.dataframe, int(new_build_quantity))
    affected_row_ids = []
    for row in active_bom_state.rows():
        if not str(row.get("qty_per_board", "")).strip():
            continue

        row_id = row["row_id"]
        index = active_bom_state.index_for_row_id(row_id)
        active_bom_state.update_row(
            row_id,
            {
                "build_quantity": recomputed.at[index, "build_quantity"],
                "required_qty": recomputed.at[index, "required_qty"],
                "status": recomputed.at[index, "status"],
                "notes": recomputed.at[index, "notes"],
            },
        )
        affected_row_ids.append(row_id)

    sources = _authoritative_sources()
    for row_id in affected_row_ids:
        retry_exact_sourcing(active_bom_state, row_id, sources=sources)

    current_run["run"]["build_quantity"] = int(new_build_quantity)
    refresh_response_snapshot(current_run)


def render_configuration_section():
    """
    One shared configuration for the whole parts-sourcing job -- applies
    regardless of whether parts came from Search or Upload (there is no
    separate upload_settings/search_settings split; see
    render_upload_intake()'s docstring). Always visible, not gated
    behind a working BOM existing, since Upload's very first click reads
    these same st.session_state values before any working BOM exists
    yet -- Customer Reference is the only part of this section that
    needs an actual working BOM to apply to, so only it is guarded
    below.
    """
    st.subheader("Configuration")

    # Single stacked column, not a 2-column grid -- this now renders
    # inside Add Parts' narrower right-hand column (under Upload), where
    # a further column split would leave too little width per field.
    st.number_input("Build quantity", min_value=1, step=1, key="cfg_build_quantity")
    st.text_input("Project Name", key="cfg_project_name")
    st.text_input("Project Description", key="cfg_project_description")
    write_enabled = st.checkbox("Update PartsBox Project", key="cfg_update_partsbox_project")
    # Two-tone microcopy per the frontend design spec's write-toggle:
    # distinct explanatory copy for the on/off state, not just a
    # static help tooltip -- distinct from the PartsBox Source
    # checkbox next to Search, which only searches PartsBox and
    # never writes either way.
    if write_enabled:
        st.caption(
            "Creates or reuses the PartsBox project and storage (tagged production) "
            "and adds matched BOM entries."
        )
    else:
        st.caption("Uploads source parts only. PartsBox is read, never written.")

    current_run = st.session_state.current_run
    active_bom_state = current_run.get("_active_bom_state") if current_run else None
    if current_run is not None and active_bom_state is not None:
        build_quantity = st.session_state.cfg_build_quantity
        if st.button("Apply Build Quantity to Uploaded Lines", key="cfg_apply_build_quantity"):
            _apply_build_quantity(current_run, active_bom_state, build_quantity)
            st.success(f"Applied build quantity {build_quantity} to uploaded lines.")
            # Deliberately no st.rerun() -- same reasoning as "Apply to
            # All BOM Lines" below: Results still renders normally later
            # in this SAME pass, reflecting the recomputed required_qty.

    # Always rendered -- see render_customer_reference_summary()'s
    # docstring for why this must not be gated behind current_run. No
    # divider above it -- it's part of this same Configuration card, not
    # a visually separate section below it (matches the mockup's
    # ConfigurationCard, where Customer Reference is just another field
    # in the same card).
    render_customer_reference_summary(current_run, active_bom_state)


def render_purchasing_handoff_section():
    """
    Purchasing summary/status/regeneration all derive from the canonical
    ActiveBomState via workflow_runner's build_purchasing_summary()/
    regenerate_purchasing() -- no sourcing decision is recalculated here.
    Customer Reference assignment is its own section earlier on the same
    page (see render_autobom_workflow_page()), not here -- this is
    purchasing OUTPUT, generated from whatever Customer Reference/BOM
    state is currently canonical.

    DigiKey: a direct FastAdd cart-loading link the recipient opens
    themselves (no DigiKey account action or OAuth from AutoBOM) plus a
    verified-format supplier CSV, replacing the old DigiKey MyList
    created/List ID/Share Identifier display. Mouser: a verified-format
    supplier CSV only. Neither makes a live vendor API call as part of
    this normal flow -- see
    Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md and
    Documentation/AutoBOM_Claude_Code_Direct_Cart_Handoff_Implementation_Prompt.md.
    """
    current_run = st.session_state.current_run
    if current_run is None:
        st.info("Run a BOM first to see purchasing handoff information.")
        return

    active_bom_state = current_run.get("_active_bom_state")
    if active_bom_state is None:
        st.info("No active BOM state for the current run.")
        return

    summary = build_purchasing_summary(current_run)
    st.subheader(f"Purchasing Handoff — {summary['status']}")

    if summary["status"] == "Stale — BOM Changed":
        st.warning(
            "The BOM changed (via Retry/Find Replacement) since purchasing artifacts "
            "were last generated. Regenerate before handing off to purchasing."
        )
    elif summary["status"] == "Needs Review":
        st.warning(
            f"{summary['needs_review_count']} part(s) still need review. Resolve them "
            "in Results → Needs Review before generating purchasing artifacts."
        )
    elif summary["status"] in ("Generation Failed", "Partial — Generation Failed"):
        for error in current_run.get("purchasing_regeneration_errors", []):
            st.error(error)

    artifact_status_labels = {
        "current": "Current / Ready",
        "stale": "Stale — BOM Changed",
        "not_generated": "Not Yet Generated",
        "failed": "Generation Failed",
        "not_required": "Not Required (no items for this supplier)",
        "csv_fallback": "CSV Fallback (cart link too long)",
    }
    _disabled_download_statuses = ("stale", "failed", "not_required", "not_generated")

    outputs = current_run.get("outputs", {})

    cols = st.columns(2)
    with cols[0]:
        st.markdown("#### Mouser")
        mouser = summary["mouser"]
        st.write(f"Status: {artifact_status_labels.get(mouser['artifact_status'], 'Unknown')}")
        st.write(f"Items: {mouser['item_count']}")
        st.write(f"Total quantity: {mouser['total_quantity']}")
        for error in mouser["errors"]:
            st.error(error)
        show_download(
            "Download Mouser CSV",
            outputs.get("mouser_export_csv"),
            disabled=mouser["artifact_status"] in _disabled_download_statuses,
        )
        st.caption(
            "Download this file and upload it to Mouser's BOM Tool to source/order the "
            "Mouser-selected parts -- AutoBOM does not create a Mouser cart as part of "
            "this normal flow."
        )

    with cols[1]:
        st.markdown("#### DigiKey")
        digikey = summary["digikey"]
        st.write(f"Items: {digikey['item_count']}")
        st.write(f"Total quantity: {digikey['total_quantity']}")
        for error in digikey["errors"]:
            st.error(error)

        link_status = digikey["cart_link_status"]
        if link_status == "current":
            st.link_button("Open DigiKey Cart", digikey["cart_link_url"])
            st.caption("Cart link (copy from the box below):")
            st.code(digikey["cart_link_url"], language=None)
        elif link_status == "csv_fallback":
            st.warning(
                "The DigiKey cart link is too long to load reliably "
                f"({digikey['cart_link_encoded_length']} characters) -- use the CSV "
                "download instead."
            )
        elif link_status == "not_required":
            st.caption("No DigiKey-sourced items in this BOM.")
        elif link_status == "failed":
            st.error("DigiKey cart link could not be generated. See the errors above.")
        else:
            st.write(f"Cart link status: {artifact_status_labels.get(link_status, 'Unknown')}")

        show_download(
            "Download DigiKey CSV",
            outputs.get("digikey_list_csv"),
            disabled=digikey["csv_artifact_status"] in _disabled_download_statuses,
        )
        st.caption(
            "Open DigiKey Cart loads a DigiKey shopping cart directly with these parts "
            "and quantities -- no DigiKey account action from AutoBOM. Download DigiKey "
            "CSV is the supported fallback."
        )

    st.divider()

    can_regenerate = summary["needs_review_count"] == 0
    if st.button("Regenerate Purchasing", disabled=not can_regenerate, type="primary"):
        with st.spinner("Regenerating purchasing artifacts from the current BOM..."):
            regenerate_purchasing(current_run)
        st.rerun()

    if not can_regenerate:
        st.caption("Resolve remaining Needs Review items before regenerating purchasing.")

    st.divider()
    render_downloads(current_run)


def render_autobom_workflow_page():
    """
    One continuous AutoBOM parts-sourcer workspace -- NOT separate pages/
    tabs, and NOT "Search mode" vs. "Upload mode". Search and Upload
    (render_add_parts_section()) are two intake methods for the SAME
    canonical working BOM -- Search is the default/primary one and needs
    no upload first; Configuration lives inside that same section now,
    stacked under Upload (see render_add_parts_section()'s docstring).
    The working BOM/results (with Needs Review actioned inline) and
    Purchasing Handoff then apply to whatever is currently in that
    working BOM, however it got there. Every section reads/writes the
    same st.session_state.current_run and its _active_bom_state, so
    scrolling between sections never loses canonical BOM state. Run
    messages render last, after the actual results/purchasing content,
    not immediately under Add Parts -- an operator's first look at the
    page should be the working BOM, not a wall of run-log text.
    """
    render_add_parts_section()

    current_run = st.session_state.current_run
    active_bom_state = current_run.get("_active_bom_state") if current_run else None

    if current_run is not None and active_bom_state is not None:
        st.divider()
        render_results_workspace(current_run)

        st.divider()
        render_purchasing_handoff_section()

    if current_run is not None:
        st.divider()
        render_run_messages(current_run)


ASSETS_FOLDER = PROJECT_ROOT / "assets"

# Minimal supplementary CSS -- the light/soft-blue/navy/rounded-controls
# palette itself comes from .streamlit/config.toml's [theme] section
# (Streamlit's own theming, not CSS overrides), per the mockup-alignment
# instruction to avoid brittle selectors tied to generated DOM classes.
# This block only styles the two header text elements below, which have
# no native Streamlit equivalent (st.title is a single fixed size).
_HEADER_CSS = """
<style>
.autobom-header-title {
  font-size: 2rem; font-weight: 700; line-height: 1.1;
  color: var(--st-text-color, inherit);
}
.autobom-header-subtitle {
  font-size: 0.95rem; margin-top: 0.1rem;
  color: var(--st-secondary-text-color, var(--st-text-color, inherit));
  opacity: 0.75;
}
</style>
"""


def render_app_header():
    """
    Title/subtitle per the mockup ("AutoBOM" / "Parts Sourcing ·
    Inventory · BOM Management"), with the Yank/Arro ownership marks
    small and upper-right -- assets/*_mark.png are pre-processed
    (symbol only, wordmark text cropped out; monochrome; ~60% opacity
    baked into the PNG alpha channel) from the original supplied
    artwork, not redrawn -- see the Phase M implementation report for
    the exact crop/processing. No brand text is rendered beside them.
    """
    st.markdown(_HEADER_CSS, unsafe_allow_html=True)
    title_col, badge_col = st.columns([6, 1])
    with title_col:
        st.markdown(
            '<div class="autobom-header-title">AutoBOM</div>'
            '<div class="autobom-header-subtitle">Parts Sourcing · Inventory · BOM Management</div>',
            unsafe_allow_html=True,
        )
    with badge_col:
        yank_mark = ASSETS_FOLDER / "yank_mark.png"
        arro_mark = ASSETS_FOLDER / "arro_mark.png"
        if yank_mark.exists() and arro_mark.exists():
            # Inline HTML instead of two st.columns -- st.columns' own
            # gutter spacing pushed the two marks far apart regardless of
            # image size; a flex row with an explicit small gap is the
            # only way to control both size AND spacing directly, per
            # direct operator feedback ("bigger and closer together").
            yank_b64 = base64.b64encode(yank_mark.read_bytes()).decode("ascii")
            arro_b64 = base64.b64encode(arro_mark.read_bytes()).decode("ascii")
            st.markdown(
                '<div style="display:flex;align-items:center;justify-content:flex-end;gap:6px;height:44px">'
                f'<img src="data:image/png;base64,{yank_b64}" style="height:40px;width:auto" />'
                f'<img src="data:image/png;base64,{arro_b64}" style="height:40px;width:auto" />'
                "</div>",
                unsafe_allow_html=True,
            )


st.set_page_config(page_title="AutoBOM", layout="wide")
init_session_state()

render_app_header()

for warning in collect_startup_warnings():
    st.warning(warning)

# Single continuous page -- no sidebar navigation. Browsing the full
# PartsBox catalog is folded into Main Search's PartsBox panel (the
# "Browse Inventory" button in render_component_search_intake()) rather
# than a separate top-level destination, per the frontend design spec's
# retirement of the old standalone PartsBox Inventory page.
render_autobom_workflow_page()
