# AutoBOM Phase 3 Implementation Report

**Scope:** Persistent Results Workspace, results search/filtering, shared component lookup foundation, Needs Review workflow foundation, replacement lookup entry point, Streamlit session-state continuity.
**Explicitly not built:** full PartsBox Inventory CRUD, unsupported PartsBox saved-filter calls, Mouser share automation, final purchasing hand-off polish, DigiKey durable cloud persistence (already gated in the prior phase's document).

## 1. Files changed

**New:**
- `src/component_lookup.py` — shared `LookupQuery`/`LookupResult`/`search_components()`/`build_query_from_bom_row()`
- `src/record_filter.py` — shared `text_search()`/`apply_filters()`/`search_and_filter()`
- `src/review_actions.py` — `retry_exact_sourcing()`, `apply_replacement()`
- `tests/test_component_lookup.py`, `tests/test_record_filter.py`, `tests/test_review_actions.py`, `tests/test_app_smoke.py`

**Modified:**
- `app.py` — rewritten around session-state continuity; adds Results Workspace and Component Search pages
- `src/active_bom_state.py` — extended with `source`/`result_status`/`review_reason` derivation and `summary_counts()`
- `src/partsbox_project_builder.py` — `build_project_entries()` now writes per-row PartsBox match info back onto the canonical DataFrame
- `src/workflow_runner.py` — response now carries `_active_bom_state` (live object) and `results_summary`
- `tests/test_active_bom_state.py`, `tests/test_workflow_runner_contract.py` — new coverage for the above

## 2. Streamlit session-state design

`app.py`'s `init_session_state()` sets defaults for `current_run`, `selected_review_row_id`, `replacement_lookup_sources`, `lookup_results`. `current_run` is the **entire dict returned by `run_bom_workflow()`**, including `current_run["_active_bom_state"]` — the live `ActiveBomState` object, not a re-derived copy.

- A run button click replaces `st.session_state.current_run` outright — one canonical run per session, never two held side by side.
- Everything that renders after that (`render_run_messages`, `render_downloads`, `render_results_workspace`) reads from `st.session_state.current_run` **unconditionally on every script rerun**, not only inside the button's `if` branch. This is the specific fix for the review's Phase-1/2 finding that a Streamlit rerun could drop the results/downloads.
- Filter/search widgets use `key=` (e.g. `results_search`, `results_filter_source`) so Streamlit's own widget-state mechanism persists their values across reruns — no separate filter-state dict was built.
- `selected_review_row_id` tracks which Needs Review row currently has its Find Replacement/Check PartsBox sub-panel open.
- **Session isolation** is Streamlit's own guarantee: each browser session gets its own server-side `session_state` dict. No code was needed to enforce "one session can't see another's state" — it's inherent to the framework, not something this app has to implement.
- `ActiveBomState` remains the only canonical BOM representation; session state holds a *reference* to it, never a second dict/list treated as authoritative. Business logic (session-state or otherwise) does not live in `app.py` — every mutation goes through `active_bom_state`, `review_actions`, or `component_lookup` in `src/`.

## 3. Results Workspace architecture

`render_results_workspace(current_run)` in `app.py`:
1. Pulls `active_bom_state = current_run["_active_bom_state"]`.
2. Renders 5 metrics from `active_bom_state.summary_counts()` — Total Parts / PartsBox / Mouser / DigiKey / Needs Review. The UI never recomputes these; `summary_counts()` (in `active_bom_state.py`) is the one place they're derived.
3. Renders a search box and Source/Status/Manufacturer/Stock filter dropdowns, populated from the actual data (`_options()` pulls distinct values from `active_bom_state.rows()` — no hardcoded/fake option lists).
4. Two tabs, `All Results` and `Needs Review (N)`: both call `record_filter.search_and_filter()` against, respectively, `active_bom_state.rows()` and `active_bom_state.review_items()` — the same filter function, different input.
5. `render_results_table()` maps real BOM columns to display names (Manufacturer Part Number, Manufacturer, Description, Designators, Quantity Required, Source, Supplier Part Number, Status, Review Reason) — only columns that actually exist on the rows are shown; nothing is fabricated.

## 4. Source/Status model

Both are computed once, in one place (`active_bom_state.py`'s `_derive_source()`/`_derive_result_status()`), and injected into every record `to_records()` produces — so `rows()`, `review_items()`, and `get_row()` all agree.

- **Source**: `Mouser`/`DigiKey` when `selected_supplier` says so; `PartsBox` when `partsbox_match_status == "matched"`; otherwise `None`.
- **Status** (`result_status`, kept as a separate field from the raw `status` column bom_cleaner already uses): `Error` (legacy `supplier_match_status == "error"` path), `Needs Review` (via `_needs_review()`, see below), `Ready` (sourced by Mouser/DigiKey, or matched in PartsBox), `Not Found` (a sourcing/PartsBox step ran and found nothing), else `Ready`/`Needs Review` based on the raw cleaning status.
- `_needs_review()` reuses `main.py`'s existing `REVIEW_STATUSES`/`SUPPLIER_REVIEW_STATUSES`/`SOURCING_REVIEW_STATUSES` sets — the exact same criteria `build_review_items()` uses — so a row's `result_status == "Needs Review"` and its presence in `review_items()` can never disagree.
- The raw `status`, `sourcing_status`, `selected_supplier`, `supplier_match_status` columns are untouched on the row — preserved for debugging exactly as the original spec required.

**Real gap closed to make this possible:** `clean_bom` previously carried no per-row PartsBox match info at all (only an aggregate `unmatched_rows` list existed). `build_project_entries()` now writes `partsbox_match_status`/`partsbox_part_id` back onto the DataFrame by row index while it already iterates for entry-building — no new PartsBox call, no new loop, one additional side effect on an existing pass.

## 5. Shared search/filter architecture

`src/record_filter.py` is intentionally generic — it knows nothing about BOM rows or lookup results, only "list of dicts, some fields to search, a filters dict." `text_search()` does case-insensitive substring search across named fields; `apply_filters()` does case-insensitive exact match per field, with `"All"`/empty treated as "no filter," plus a `stock` special case (`"In Stock"`/`"Out of Stock"` against a numeric threshold rather than string equality). `search_and_filter()` composes both.

This is the **one** filtering implementation used by:
- Results Workspace (`app.py`, over `active_bom_state.rows()`/`review_items()`)
- Component Search (`app.py`, over `component_lookup.search_components()` results)

Both callers pass different field lists but the same functions — no page has its own filter logic.

## 6. Component Lookup architecture

`src/component_lookup.py`:
- `LookupQuery` — `mpn`, `manufacturer`, `keywords`, plus category/package/mounting/dielectric/tolerance/voltage/current/power/value fields and an open `characteristics` dict, `sources: frozenset`, `required_qty`. Only `mpn`/`manufacturer`/`keywords` are actually populated/used by this phase's searches — the rest exist so a future BOM schema extension (parsed capacitor/resistor specs) or a richer parametric UI doesn't require a new query model.
- `LookupResult` — `source`, `manufacturer`, `mpn`, `description`, `category`, `package`, `stock`, `supplier_part_number`, `unit_price`, `lifecycle_status`, `characteristics` (dict), `raw` (original payload, always preserved). `.to_dict()` for transport/filtering.
- `search_components(query, partsbox_client=None, mouser_client=None, digikey_client=None)` — for each source in `query.sources`, calls the corresponding existing client and adapts its result into `LookupResult`. Returns a flat `list[dict]`, ready for `record_filter.search_and_filter()`.
- `build_query_from_bom_row(row, sources=None)` — the one prepopulation function for both Find Replacement (default `sources={"mouser", "digikey"}`) and Check PartsBox (call again with `sources={"partsbox"}`). Only reads fields that exist on the row (`mpn`, `manufacturer`, `description`, `required_qty`); never invents a specification.

**Reuse, not reimplementation:**
- PartsBox: `client.get_parts()` (existing `list_parts()`/caching) filtered in-process by substring/manufacturer-alias match; `manufacturer_aliases.manufacturers_equivalent()` reused for fuzzy matching (not a second normalization scheme).
- Mouser/DigiKey: `client.search_candidates(term)` — the exact same method `sourcing_engine`'s per-row lookups already call, returning the same `SupplierResult` objects, adapted into `LookupResult` by a small function. No new HTTP calls, no new client classes.

## 7. Supplier-source toggles

`LookupQuery.sources` is a `frozenset`; default `{"partsbox"}`. `search_components()` checks membership per source and only calls that source's adapter — there is no branching combined-search code path. `test_all_sources_enabled_equals_union_of_each_alone` proves this directly: enabling all three sources together returns exactly the concatenation of what each source returns alone, so toggles compose rather than diverging into a different implementation. In `app.py`, three checkboxes (PartsBox default-checked, Mouser/DigiKey default-unchecked) build the `sources` set passed into one `LookupQuery`.

## 8. Needs Review implementation

`render_needs_review(active_bom_state, review_rows)` in `app.py` renders one `st.expander` per row from `active_bom_state.review_items()` (already filtered/searched via the shared layer) — a **view**, not a stored dataset; nothing needing review is cached anywhere except by re-deriving from `active_bom_state` on every render. Each expander shows designators, current status, and `review_reason`, then three actions in the required order:

1. **Retry Exact Part** → `review_actions.retry_exact_sourcing()`.
2. **Find Replacement** → opens the shared lookup sub-panel with `sources={"mouser", "digikey"}`.
3. **Check PartsBox** → opens the same sub-panel with `sources={"partsbox"}`.

PartsBox is never the automatic first fallback — it only appears when the operator explicitly clicks Check PartsBox, exactly matching the required recovery order.

## 9. Replacement lookup implementation

`render_replacement_lookup(active_bom_state, row_id)` is the single function both Find Replacement and Check PartsBox call (selected via `st.session_state.replacement_lookup_sources`). It builds a `LookupQuery` via `component_lookup.build_query_from_bom_row(row, sources=...)`, shows the prefilled MPN/keywords in an editable text input (loosen/tighten), and on "Search" calls `component_lookup.search_components(query)` — the identical function the Component Search page calls. Results render with a per-candidate "Select" button.

## 10. Replacement selection → canonical state

Clicking "Select" calls `review_actions.apply_replacement(active_bom_state, row_id, candidate)`, which calls `active_bom_state.update_row()` — the one shared mutation seam, not a UI dictionary or a detached table. It:
- Preserves `original_mpn`/`original_manufacturer` for traceability (only set once, on first replacement, so a second replacement doesn't overwrite the true original).
- For a Mouser/DigiKey candidate: sets `mpn`, `manufacturer`, `selected_supplier`, `supplier_part_number`, `unit_price`, `mouser_stock`/`digikey_stock`, `sourcing_status` (`sourced_mouser`/`sourced_digikey`), `status = "clean"`, and a traceability note.
- For a PartsBox candidate: sets `partsbox_match_status = "matched"`, `partsbox_part_id`, and a note flagging that external availability still needs confirming via Retry.

Because `result_status`/`source` are derived fresh from these same columns on every `rows()`/`review_items()` call, the row **automatically** leaves Needs Review the moment the state changes — no separate "regenerate review" step was written or is needed.

## 11. Implemented vs. scaffolded for replacement re-sourcing

**Implemented, not scaffolded:** the row genuinely re-enters the existing purchasing pipeline. `tests/test_review_actions.py::test_mouser_replacement_updates_state_and_reenters_cart_pipeline` and `..._digikey_replacement_reenters_mylists_pipeline` prove this directly — after `apply_replacement()`, the **unmodified** `mouser_cart_client.build_mouser_cart_items()` / `digikey_mylists_client.build_digikey_mylists_parts()` (which filter purely on `selected_supplier`/`sourcing_status`) pick the replaced row up correctly, with no changes to those functions.

**Not implemented, and correctly not implemented in this phase:** the app does not automatically re-invoke `create_mouser_cart_from_bom()`/`create_digikey_mylist_from_bom()` (live cart/MyList API calls) as a side effect of clicking "Select" in the Needs Review UI. That would be purchasing-hand-off polish, explicitly out of scope for this phase (§16). The operator re-runs those existing steps (already wired into `run_bom_workflow`) separately, and they will pick up the replaced row correctly, per the tests above.

`retry_exact_sourcing()` is fully implemented (not scaffolded): it calls the real `MouserClient.find_best_match_for_row()`/`DigiKeyClient.find_best_match_for_row()` and the real `sourcing_engine.decide_no_split_supplier()` for exactly one row, then writes through `update_row()`.

## 12. Tests added and results

37 new tests across 4 new files plus additions to 2 existing files:
- `test_record_filter.py` (16) — text search, exact-match filters, `"All"` sentinel, combined filters, in-stock/out-of-stock.
- `test_component_lookup.py` (14) — PartsBox-only, Mouser-enabled, DigiKey-enabled, all-sources-equals-union, manufacturer-alias filtering (both directions), empty-query no-op, raw payload preservation, `build_query_from_bom_row` prepopulation/defaults/no-fabrication.
- `test_review_actions.py` (9) — successful retry, stale-field clearing on failed retry, exception-not-raised on lookup failure, unknown row_id, Mouser/DigiKey/PartsBox replacement application, cart/MyList pipeline re-entry, review-status regeneration.
- `test_active_bom_state.py` (+7) — source/status distinctness, PartsBox-matched-is-ready, PartsBox-unmatched-is-not-found, review-reason population, summary-counts correctness and update-reflection.
- `test_workflow_runner_contract.py` (+3) — live `_active_bom_state` exposure, `results_summary` agreement, JSON-safety of the on-disk run summary.
- `test_app_smoke.py` (6, new) — real `app.py` execution via `streamlit.testing.v1.AppTest`: page load, page navigation, injected-run rendering, Needs Review buttons rendering, Find Replacement sub-UI rendering, and a **full replacement-selection flow through the actual UI** ending in an assertion against the live `ActiveBomState`. Deliberately never clicks Retry/Search, since this environment's `.env` has `SUPPLIER_DRY_RUN=false` and PartsBox reads are never dry-run-gated in this codebase — clicking either would make a real vendor API call. Verified manually (ad hoc, not committed) that clicking through to a live search, and to Retry Exact Part, render without exceptions.

```
python -m unittest discover -s tests -v
Ran 138 tests in 3.748s
OK
```
(101 at the start of this phase → 138; all prior tests pass unmodified.)
```
python -m py_compile app.py src/*.py tests/*.py
```
passes clean.

## 13. Existing capabilities reused

`PartsBoxClient.get_parts()`/`find_part_by_mpn_and_manufacturer()`, `MouserClient.search_candidates()`/`find_best_match_for_row()`, `DigiKeyClient.search_candidates()`/`find_best_match_for_row()`, `sourcing_engine.decide_no_split_supplier()`, `manufacturer_aliases.manufacturers_equivalent()`, `main.build_review_items()` (via `main.REVIEW_STATUSES` etc.), `mouser_cart_client.build_mouser_cart_items()`, `digikey_mylists_client.build_digikey_mylists_parts()`, `run_workspace`, `workflow_runner.run_bom_workflow()`, `ActiveBomState` itself (extended, not replaced). No parallel sourcing engine, PartsBox client, or supplier client was created.

## 14. Remaining external API limitations (unchanged from prior phases)

Mouser Cart API response shape, DigiKey MyLists share identifier, PartsBox `project/get-entries` envelope and tag representation, and PartsBox stock/quantity field (used defensively as `None` in `component_lookup._partsbox_part_to_result` — no confirmed field name exists) remain unverified against live APIs. `Documentation/partsbox api rules.pdf` still could not be parsed in this environment.

## 15. Remaining release blockers

- DigiKey durable token persistence — already gated in `Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md`; unchanged by this phase.
- Exported `cleaned_bom.csv`/`.xlsx` now include two additional columns (`partsbox_match_status`, `partsbox_part_id`) when PartsBox runs — consistent with this pipeline's existing pattern of appending derived columns over time, but worth a explicit acknowledgment before team release if any downstream process consumes these files positionally rather than by column name.
- No PartsBox Inventory page, no automated re-triggering of cart/MyList creation after a replacement, no parametric characteristic filters beyond what real data currently supports (all explicitly deferred per this phase's scope boundary).
- Everything listed as deferred in the prior phase's report (`runs/` retention, `FileTokenStore` temp-file collision, raw vendor payloads in `run_summary.json`) is unchanged.

## 16. Recommended next phase

PartsBox Inventory view, built on the same `component_lookup`/`record_filter` layers this phase established (per the original spec's Phase 6), followed by purchasing hand-off polish (surfacing CartKey/MyList share identifiers in the UI, and deciding whether/how a selected replacement should re-trigger cart/MyList creation).
