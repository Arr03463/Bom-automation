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
from record_filter import search_and_filter  # noqa: E402
from review_actions import apply_replacement, retry_exact_sourcing  # noqa: E402
from run_workspace import build_run_workspace, save_uploaded_file  # noqa: E402
from workflow_runner import refresh_response_snapshot, run_bom_workflow  # noqa: E402


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


def show_download(label, file_path):
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

    if current_run.get("stale_after_mutation"):
        st.warning(
            "A Needs Review action changed the BOM since these files were generated. "
            "Downloads, purchasing carts/lists, and the run summary below reflect the "
            "BOM *before* that change. Re-run BOM Automation to regenerate them from "
            "the current state."
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

    for key, label in download_labels.items():
        show_download(label, outputs.get(key))


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

    for index, candidate in enumerate(results):
        candidate_cols = st.columns([5, 1])
        with candidate_cols[0]:
            st.write(
                f"**{candidate.get('source')}** · {candidate.get('mpn')} · "
                f"{candidate.get('manufacturer') or 'unknown manufacturer'} · "
                f"stock: {candidate.get('stock') if candidate.get('stock') is not None else 'Unknown'} · "
                f"supplier P/N: {candidate.get('supplier_part_number') or '—'}"
            )
        with candidate_cols[1]:
            if st.button("Select", key=f"select_replacement_{row_id}_{index}"):
                with st.spinner("Re-sourcing replacement..."):
                    apply_replacement(active_bom_state, row_id, candidate)
                refresh_response_snapshot(current_run)
                st.session_state.selected_review_row_id = None
                st.session_state.pop(f"replacement_results_{row_id}", None)
                st.rerun()


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

    filtered = search_and_filter(
        results,
        filters={
            "source": st.session_state.component_search_source_filter,
            "stock": st.session_state.component_search_stock_filter,
        },
    )
    render_lookup_results_table(filtered)


def render_lookup_results_table(results):
    if not results:
        st.info("No results match the current filters.")
        return

    table_df = pd.DataFrame(results)
    available_columns = [col for col in LOOKUP_DISPLAY_COLUMNS if col in table_df.columns]
    table_df = table_df[available_columns].rename(columns=LOOKUP_DISPLAY_COLUMNS)
    st.dataframe(table_df, width="stretch", hide_index=True)


st.set_page_config(page_title="AutoBOM", layout="wide")
init_session_state()

st.title("AutoBOM")
page = st.sidebar.radio("Navigate", ["Run BOM", "Component Search"])

if page == "Run BOM":
    render_run_bom_page()
else:
    render_component_search_page()
