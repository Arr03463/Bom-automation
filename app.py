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

from component_lookup import (  # noqa: E402
    LookupQuery,
    build_query_from_bom_row,
    search_components,
)
from engineering_units import parse_engineering_value  # noqa: E402
from partsbox_client import PartsBoxClient  # noqa: E402
from partsbox_project_builder import PRODUCTION_STORAGE_TAG, storage_has_tag  # noqa: E402
from record_filter import generate_facets, search_and_filter  # noqa: E402
from review_actions import apply_replacement, retry_exact_sourcing  # noqa: E402
from run_workspace import build_run_workspace, save_uploaded_file  # noqa: E402
from workflow_runner import (  # noqa: E402
    build_purchasing_summary,
    refresh_response_snapshot,
    regenerate_purchasing,
    run_bom_workflow,
)


RESULTS_SEARCH_FIELDS = ["mpn", "manufacturer", "description", "supplier_part_number", "designators"]

RESULTS_DISPLAY_COLUMNS = {
    "mpn": "Manufacturer Part Number",
    "manufacturer": "Manufacturer",
    "description": "Description",
    "designators": "Designators",
    "required_qty": "Quantity Required",
    "source": "Source",
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

INVENTORY_DISPLAY_COLUMNS = {
    "mpn": "Manufacturer Part Number",
    "manufacturer": "Manufacturer",
    "description": "Description",
    "category": "Category",
    "package": "Package",
}

# Facets shown only when the current result set actually has data for
# them (record_filter.generate_facets) -- never a fixed always-shown
# list. Categorical facets get an exact-match selectbox; range facets get
# min/max numeric inputs parsed via engineering_units. "stock" is
# excluded from both since it already has its own dedicated In Stock/Out
# of Stock/Unknown filter.
CATEGORICAL_FACET_FIELDS = ["category", "package", "mounting", "dielectric", "lifecycle_status"]
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


RUN_SCOPED_STATE_DEFAULTS = {
    "selected_review_row_id": None,
    "results_search": "",
    "results_filter_source": "All",
    "results_filter_status": "All",
    "results_filter_manufacturer": "All",
    "results_filter_stock": "All",
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
    st.session_state.setdefault("lookup_results", [])
    st.session_state.setdefault("inventory_results", [])
    st.session_state.setdefault("inventory_storage_locations", None)
    for key, default in RUN_SCOPED_STATE_DEFAULTS.items():
        st.session_state.setdefault(key, default)


def reset_run_scoped_session_state():
    """
    Clears state tied to the PREVIOUS run's rows so it cannot reappear
    against a new run: the open review row, its in-progress replacement
    search results, and the results search/filters. Called whenever a
    new run replaces current_run.

    General Component Search (lookup_results) is deliberately left
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


def render_run_bom_page():
    uploaded_file = st.file_uploader("Upload BOM", type=["csv", "xlsx"])

    left, right = st.columns(2)
    with left:
        build_quantity = st.number_input("Build quantity", min_value=1, value=1, step=1)
        project_name = st.text_input("PartsBox project name")
        project_description = st.text_input("Project description")

    with right:
        run_partsbox = st.checkbox("Run PartsBox", value=True)
        run_sourcing = st.checkbox("Run supplier sourcing", value=True)
        use_mouser_sourcing = st.checkbox("Use Mouser sourcing", value=True, disabled=not run_sourcing)
        use_digikey_sourcing = st.checkbox("Use DigiKey sourcing", value=True, disabled=not run_sourcing)
        run_mouser_cart = st.checkbox("Create Mouser cart", value=False)
        run_digikey_mylist = st.checkbox("Create DigiKey MyList", value=False)

    if st.button("Run BOM Automation", type="primary"):
        if uploaded_file is None:
            st.error("Upload a CSV or XLSX BOM before running.")
        else:
            workspace = build_run_workspace()
            source_path = save_uploaded_file(
                workspace["input_dir"], uploaded_file.name, uploaded_file.getbuffer()
            )

            with st.spinner("Running BOM automation..."):
                result = run_bom_workflow(
                    source_file_path=source_path,
                    build_quantity=int(build_quantity),
                    project_name=project_name,
                    project_description=project_description,
                    run_partsbox=run_partsbox,
                    run_sourcing=run_sourcing,
                    run_mouser_cart=run_mouser_cart,
                    run_digikey_mylist=run_digikey_mylist,
                    use_mouser_sourcing=run_sourcing and use_mouser_sourcing,
                    use_digikey_sourcing=run_sourcing and use_digikey_sourcing,
                    run_id=workspace["run_id"],
                    output_folder=str(workspace["output_dir"]),
                )

            # A new run replaces the session's active state outright --
            # one canonical run per session, never two held side by side.
            st.session_state.current_run = result
            reset_run_scoped_session_state()

    current_run = st.session_state.current_run
    if current_run is None:
        return

    st.divider()
    render_run_messages(current_run)
    render_downloads(current_run)
    st.divider()
    render_results_workspace(current_run)


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
    st.subheader("Outputs")

    artifact_status = current_run.get("artifact_status") or {}
    if bool(current_run.get("stale_after_mutation")):
        st.warning(
            "A Needs Review action changed the BOM since some of these files were "
            "generated. Files marked stale below are disabled until they're "
            "regenerated so nobody hands purchasing a BOM file that doesn't match "
            "what Results now shows. Go to the Purchasing page and click "
            "Regenerate Purchasing, or re-run BOM Automation, to update them."
        )

    outputs = current_run.get("outputs", {})
    download_labels = {
        "cleaned_workbook": "Download cleaned workbook",
        "cleaned_csv": "Download cleaned CSV",
        "sourcing_report": "Download sourcing report",
        "digikey_list_csv": "Download DigiKey list CSV",
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
    active_bom_state = current_run.get("_active_bom_state")
    if active_bom_state is None:
        return

    run_info = current_run.get("run", {})
    title = run_info.get("project_name") or run_info.get("source_file_name") or "Run"
    st.subheader(f"AutoBOM Results — {title}")

    # Summary metrics come straight from ActiveBomState -- the UI never
    # recomputes these counts itself.
    summary = active_bom_state.summary_counts()
    metric_cols = st.columns(5)
    metric_cols[0].metric("Total Parts", summary["total_parts"])
    metric_cols[1].metric("PartsBox", summary["partsbox"])
    metric_cols[2].metric("Mouser", summary["mouser"])
    metric_cols[3].metric("DigiKey", summary["digikey"])
    metric_cols[4].metric("Needs Review", summary["needs_review"])

    st.text_input("Search current BOM results...", key="results_search")

    rows = active_bom_state.rows()
    filter_cols = st.columns(4)
    with filter_cols[0]:
        st.selectbox("Source", _options(rows, "source"), key="results_filter_source")
    with filter_cols[1]:
        st.selectbox("Status", _options(rows, "result_status"), key="results_filter_status")
    with filter_cols[2]:
        st.selectbox("Manufacturer", _options(rows, "manufacturer"), key="results_filter_manufacturer")
    with filter_cols[3]:
        st.selectbox("Stock", ["All", "In Stock", "Out of Stock", "Unknown"], key="results_filter_stock")

    filters = {
        "source": st.session_state.results_filter_source,
        "result_status": st.session_state.results_filter_status,
        "manufacturer": st.session_state.results_filter_manufacturer,
        "stock": st.session_state.results_filter_stock,
    }
    query_text = st.session_state.get("results_search", "")

    tab_all, tab_review = st.tabs(["All Results", f"Needs Review ({summary['needs_review']})"])

    with tab_all:
        filtered_rows = search_and_filter(
            rows, query_text=query_text, search_fields=RESULTS_SEARCH_FIELDS, filters=filters
        )
        render_results_table(filtered_rows)

    with tab_review:
        review_rows = search_and_filter(
            active_bom_state.review_items(),
            query_text=query_text,
            search_fields=RESULTS_SEARCH_FIELDS,
            filters=filters,
        )
        render_needs_review(current_run, active_bom_state, review_rows)


def _options(rows, field):
    values = sorted({row.get(field) for row in rows if row.get(field)})
    return ["All"] + values


def render_results_table(rows):
    if not rows:
        st.info("No results match the current search/filters.")
        return

    table_df = pd.DataFrame(rows)
    available_columns = [col for col in RESULTS_DISPLAY_COLUMNS if col in table_df.columns]
    table_df = table_df[available_columns].rename(columns=RESULTS_DISPLAY_COLUMNS)
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_needs_review(current_run, active_bom_state, review_rows):
    if not review_rows:
        st.success("Nothing currently needs review.")
        return

    for row in review_rows:
        row_id = row["row_id"]
        label = f"{row.get('mpn') or '(missing MPN)'} — {row.get('manufacturer', '') or '(unknown manufacturer)'}"

        with st.expander(label):
            st.write(f"**Designators:** {row.get('designators', '') or '—'}")
            st.write(f"**Current status:** {row.get('result_status')}")
            st.write(f"**Reason:** {row.get('review_reason') or 'Needs review'}")

            action_cols = st.columns(3)

            if action_cols[0].button("Retry Exact Part", key=f"retry_{row_id}"):
                with st.spinner("Retrying exact part lookup..."):
                    retry_exact_sourcing(active_bom_state, row_id)
                refresh_response_snapshot(current_run)
                st.rerun()

            if action_cols[1].button("Find Replacement", key=f"find_replacement_{row_id}"):
                st.session_state.selected_review_row_id = row_id
                st.session_state.replacement_lookup_sources = frozenset({"mouser", "digikey"})

            if action_cols[2].button("Check PartsBox", key=f"check_partsbox_{row_id}"):
                st.session_state.selected_review_row_id = row_id
                st.session_state.replacement_lookup_sources = frozenset({"partsbox"})

            if st.session_state.selected_review_row_id == row_id:
                render_replacement_lookup(current_run, active_bom_state, row_id)


def render_replacement_lookup(current_run, active_bom_state, row_id):
    """
    Find Replacement / Check PartsBox share this exact function. Both
    prepopulate a LookupQuery from what AutoBOM already knows about the
    row (component_lookup.build_query_from_bom_row) and call the same
    search_components() the general Component Search page calls -- no
    replacement-specific search engine.
    """
    row = active_bom_state.get_row(row_id)
    sources = st.session_state.replacement_lookup_sources
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
        query.mpn = search_value
        query.keywords = search_value
        with st.spinner("Searching..."):
            st.session_state[f"replacement_results_{row_id}"] = search_components(query)

    results = st.session_state.get(f"replacement_results_{row_id}", [])
    if not results:
        st.info("No candidates yet. Adjust the query above and click Search.")
        return

    row_required_qty = row.get("required_qty")

    for index, candidate in enumerate(results):
        candidate_cols = st.columns([5, 1])
        with candidate_cols[0]:
            stock_display = candidate.get("stock") if candidate.get("stock") is not None else "Unknown"
            coverage = ""
            if row_required_qty:
                sufficient = candidate.get("stock_sufficient")
                if sufficient is True:
                    coverage = f" · ✓ covers required qty ({row_required_qty})"
                elif sufficient is False:
                    coverage = f" · ✗ short of required qty ({row_required_qty})"
            st.write(
                f"**{candidate.get('source')}** · {candidate.get('mpn')} · "
                f"{candidate.get('manufacturer') or 'unknown manufacturer'} · "
                f"stock: {stock_display} · "
                f"supplier P/N: {candidate.get('supplier_part_number') or '—'}"
                f"{coverage}"
            )
        with candidate_cols[1]:
            if st.button("Select", key=f"select_replacement_{row_id}_{index}"):
                with st.spinner("Re-sourcing replacement..."):
                    apply_replacement(active_bom_state, row_id, candidate)
                refresh_response_snapshot(current_run)
                st.session_state.selected_review_row_id = None
                st.session_state.pop(f"replacement_results_{row_id}", None)
                st.rerun()


def render_dynamic_facet_filters(results, key_prefix):
    """
    Shared by Component Search and PartsBox Inventory: builds filter
    widgets only for facets that actually have data in the current
    result set (record_filter.generate_facets), instead of a fixed list
    of often-empty filters. Categorical facets (category, package, ...)
    get an exact-match selectbox; numeric facets (voltage, tolerance,
    ...) get min/max range inputs parsed through engineering_units.
    Returns a filters dict ready for record_filter.search_and_filter().
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


def render_component_search_page():
    st.subheader("Component Search")
    st.caption("PartsBox is searched by default. Enable Mouser/DigiKey to include live supplier results.")

    search_cols = st.columns([3, 1])
    with search_cols[0]:
        search_text = st.text_input("MPN, manufacturer, or keywords", key="component_search_text")
    with search_cols[1]:
        manufacturer_filter = st.text_input("Manufacturer (optional)", key="component_search_manufacturer")

    source_cols = st.columns(3)
    with source_cols[0]:
        use_partsbox = st.checkbox("PartsBox", value=True, key="component_search_partsbox")
    with source_cols[1]:
        use_mouser = st.checkbox("Mouser", value=False, key="component_search_mouser")
    with source_cols[2]:
        use_digikey = st.checkbox("DigiKey", value=False, key="component_search_digikey")

    if st.button("Search", key="component_search_button"):
        sources = {
            source
            for source, enabled in (
                ("partsbox", use_partsbox),
                ("mouser", use_mouser),
                ("digikey", use_digikey),
            )
            if enabled
        }
        if not sources:
            # An explicitly empty source set must stay empty -- never
            # silently fall back to PartsBox just because every checkbox
            # is off.
            st.warning("Select at least one source.")
            st.session_state.lookup_results = []
        else:
            query = LookupQuery(
                mpn=search_text,
                keywords=search_text,
                manufacturer=manufacturer_filter,
                sources=frozenset(sources),
            )
            with st.spinner("Searching..."):
                st.session_state.lookup_results = search_components(query)

    results = st.session_state.lookup_results
    if not results:
        st.info("No results yet. Enter a search and click Search.")
        return

    filter_cols = st.columns(2)
    with filter_cols[0]:
        st.selectbox("Filter by source", _options(results, "source"), key="component_search_source_filter")
    with filter_cols[1]:
        st.selectbox(
            "Stock", ["All", "In Stock", "Out of Stock", "Unknown"], key="component_search_stock_filter"
        )

    dynamic_filters = render_dynamic_facet_filters(results, key_prefix="component_search")
    filters = {
        "source": st.session_state.component_search_source_filter,
        "stock": st.session_state.component_search_stock_filter,
        **dynamic_filters,
    }

    filtered = search_and_filter(results, filters=filters)
    render_lookup_results_table(filtered)


def render_lookup_results_table(results, show_stock_sufficiency=False):
    if not results:
        st.info("No results match the current filters.")
        return

    table_df = pd.DataFrame(results)
    display_columns = dict(LOOKUP_DISPLAY_COLUMNS)
    if show_stock_sufficiency and "stock_sufficient" in table_df.columns:
        display_columns = {**display_columns, "stock_sufficient": "Covers Required Qty?"}

    available_columns = [col for col in display_columns if col in table_df.columns]
    table_df = table_df[available_columns].rename(columns=display_columns)
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_partsbox_inventory_page():
    """
    Reuses component_lookup.search_components() (sources={"partsbox"},
    which now supports an empty query as "browse everything") and
    record_filter -- no second PartsBox search/filter implementation.
    Read-only: no write action in this phase has confirmed PartsBox API
    support (see the Phase 4 report), so none is offered here rather
    than inventing one.
    """
    st.subheader("PartsBox Inventory")
    st.caption(
        "PartsBox remains the system of record; this is a read-only view over it. "
        "**Confirmed** fields (Manufacturer, MPN, PartsBox part ID) are already used "
        "elsewhere in this app. **Inferred** fields (Description, Category, Package) "
        "are read defensively and may be blank if PartsBox's live schema differs. "
        "Quantity/stock is **not exposed** -- no confirmed PartsBox field for it "
        "exists in this integration."
    )

    search_cols = st.columns([3, 1])
    with search_cols[0]:
        search_text = st.text_input(
            "MPN or keywords (leave blank to browse everything)", key="inventory_search_text"
        )
    with search_cols[1]:
        manufacturer_filter = st.text_input("Manufacturer (optional)", key="inventory_manufacturer")

    if st.button("Search / Browse All", key="inventory_search_button"):
        query = LookupQuery(
            mpn=search_text,
            keywords=search_text,
            manufacturer=manufacturer_filter,
            sources=frozenset({"partsbox"}),
        )
        with st.spinner("Loading from PartsBox..."):
            st.session_state.inventory_results = search_components(query)

    results = st.session_state.inventory_results
    if results:
        dynamic_filters = render_dynamic_facet_filters(results, key_prefix="inventory")
        filtered = search_and_filter(
            results,
            query_text="",
            search_fields=[],
            filters=dynamic_filters,
        )
        st.write(f"{len(filtered)} of {len(results)} parts shown.")
        render_lookup_results_table(filtered)
    else:
        st.info("No results yet. Search, or click Browse All with an empty query.")

    st.divider()
    render_partsbox_storage_locations()


def render_partsbox_storage_locations():
    st.subheader("Storage Locations")
    st.caption(
        "The project/storage/production-tag convention (same-name project + storage, "
        "storage tagged \"production\") is unchanged from the PartsBox project lifecycle "
        "already used when running a BOM."
    )

    if st.button("Load storage locations", key="load_storage_locations_button"):
        with st.spinner("Loading from PartsBox..."):
            try:
                response = PartsBoxClient().list_storage_locations()
                st.session_state.inventory_storage_locations = response.get(
                    "data", response.get("storage", [])
                )
            except Exception as exc:
                st.error(f"Could not load storage locations: {exc}")

    storage_locations = st.session_state.inventory_storage_locations
    if storage_locations is None:
        st.info("Click 'Load storage locations' to fetch them from PartsBox.")
        return

    if not storage_locations:
        st.info("No storage locations returned.")
        return

    rows = []
    for storage in storage_locations:
        tags = storage.get("storage/tags") or storage.get("tags") or []
        rows.append(
            {
                "Name": storage.get("storage/name") or storage.get("name") or "",
                "Tags": ", ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags),
                "Production": "Yes" if storage_has_tag(storage, PRODUCTION_STORAGE_TAG) else "No",
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_purchasing_page():
    """
    Purchasing summary/status/regeneration all derive from the canonical
    ActiveBomState via workflow_runner's build_purchasing_summary()/
    regenerate_purchasing() -- no sourcing decision is recalculated here.
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
    }

    cols = st.columns(2)
    with cols[0]:
        st.markdown("#### Mouser")
        st.write(f"Status: {artifact_status_labels.get(summary['mouser']['artifact_status'], 'Unknown')}")
        st.write(f"Items: {summary['mouser']['item_count']}")
        st.write(f"Total quantity: {summary['mouser']['total_quantity']}")
        st.write(f"Cart created: {'Yes' if summary['mouser']['cart_created'] else 'No'}")
        st.write(f"CartKey: {summary['mouser']['cart_key'] or 'Not available'}")
        st.caption(
            "Sharing is manual for now: complete the Share action in Mouser directly "
            "and hand the resulting Access ID to purchasing. No need to paste it back "
            "into AutoBOM."
        )

    with cols[1]:
        st.markdown("#### DigiKey")
        st.write(f"Status: {artifact_status_labels.get(summary['digikey']['artifact_status'], 'Unknown')}")
        st.write(f"Items: {summary['digikey']['item_count']}")
        st.write(f"Total quantity: {summary['digikey']['total_quantity']}")
        st.write(f"MyList created: {'Yes' if summary['digikey']['list_created'] else 'No'}")
        st.write(f"List ID: {summary['digikey']['list_id'] or 'Not available'}")
        st.write(f"Share identifier: {summary['digikey']['share_id'] or 'Not confirmed by current API'}")

    st.divider()

    can_regenerate = summary["needs_review_count"] == 0
    if st.button("Regenerate Purchasing", disabled=not can_regenerate, type="primary"):
        with st.spinner("Regenerating purchasing artifacts from the current BOM..."):
            regenerate_purchasing(current_run, run_mouser_cart=True, run_digikey_mylist=True)
        st.rerun()

    if not can_regenerate:
        st.caption("Resolve remaining Needs Review items before regenerating purchasing.")

    st.divider()
    render_downloads(current_run)


st.set_page_config(page_title="AutoBOM", layout="wide")
init_session_state()

st.title("AutoBOM")
page = st.sidebar.radio("Navigate", ["Run BOM", "Component Search", "PartsBox Inventory", "Purchasing"])

if page == "Run BOM":
    render_run_bom_page()
elif page == "Component Search":
    render_component_search_page()
elif page == "PartsBox Inventory":
    render_partsbox_inventory_page()
else:
    render_purchasing_page()
