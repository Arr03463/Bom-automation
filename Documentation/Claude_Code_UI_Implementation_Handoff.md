# Claude Code UI Implementation Handoff

**From:** Claude Design · **For:** Claude Code · **Scope:** implement the approved design in `app.py`/`src/`, reusing verified services. This file is the required deliverable per the design brief §42-61.

Design authority: `AutoBOM_Final_UI_Design_Spec.md`. Backend authority: `AutoBOM_UI_Replacement_Integration_Audit.md`. Where the two conflict, the audit wins.

---

## 1. Executive summary

**What changes.** Presentation and page composition only: remove the sidebar/second page, embed PartsBox Inventory into the home workspace, restyle every card to the approved visual language, move Configuration upper-right and compact it, replace the plain-text Customer Reference field with the structured PRJ/INV/RND builder, and give the PartsBox write toggle its own visual treatment.

**What stays.** Every domain/service module in §14 of the audit: `ActiveBomState`, `PartsBoxInventorySnapshot`, `record_filter`, `pagination`, sourcing engine, review actions, customer reference validation/registry, inventory recommender rules, PartsBox project builder, artifact freshness, exports, MyList client. No business rule, no API contract, no side-effect boundary changes.

**What disappears from the UI.** The sidebar `st.sidebar.radio("Navigate", …)` and `render_partsbox_inventory_page()` as a destination. `render_partsbox_storage_locations()`'s separate live `storage/all` read/render. `render_inventory_selected_part_details()`'s standalone detail panel and its `inventory_selected_part` state. The plain full-width Configuration inputs (visually only — same fields, denser layout).

**What needs adaptation.** Selected Part Details needs one presentation contract instead of two near-duplicate functions (`render_selected_part_details` / `render_inventory_selected_part_details`). Configuration needs a compact two-column card. Customer Reference needs a popover shell around the existing three builders. Filters need a collapsible placement (rail vs. popover) without changing widget keys.

**What needs extraction.** A small `search_controller` seam so PartsBox and Supplier results can be computed once and rendered by whichever layout (50/50, PartsBox-only, Supplier-only) applies, instead of the current three-branch inline rendering in `render_component_search_intake()`.

**What is genuinely new (UI-only, no backend).** The Browse Inventory affordance as an explicit lazy-load trigger inside the embedded PartsBox card (today the standalone page always loads immediately; the embedded card must not). The active-filter chip strip. The PartsBox-write banner styling. None of these require a domain change.

---

## 1a. Interaction matrix

Full per-control behavior is specified in `AutoBOM_Interaction_Specification.md` (§1-15). Summary:

| UI element | Operator action | Expected UI behavior | Real AutoBOM target |
|---|---|---|---|
| Search field | Type | Debounce 350ms → local PartsBox re-filter; no API call | `search_event_input`, `get_snapshot`, `search_and_filter` |
| Search field | Press Enter | Commit text; if Mouser/DigiKey selected, fire one supplier lookup; older supplier results marked stale if draft later diverges | `search_components(LookupQuery)` |
| Search field | Clear (✕) | Reset draft; PartsBox reverts to blank-query state; supplier panel returns to idle | local state only |
| Source checkboxes | Toggle | Re-layout (50/50 / PartsBox-only / Supplier-only / warning); becomes authoritative for Upload/Add/Retry/Replacement | `_authoritative_sources()` |
| Upload | Drop/select file | Auto-process once per `file_id`; progress chip → done/error chip; merges into existing BOM or creates one | `build_run_workspace`, `run_bom_workflow`, `ActiveBomState.add_rows` |
| Filters (all) | Change value | Re-filter affected card(s) locally, reset that card to page 1, clear selection only if it no longer matches | `record_filter.search_and_filter/apply_filters`, `generate_facets` |
| Clear all | Click | Reset all filters (not query/sources) to default | local filter state |
| PartsBox Refresh | Click | Force snapshot refresh, spinner, update timestamp, re-render current view in place | `get_snapshot(force_refresh=True)` |
| Browse Inventory | Click | Load/reuse full snapshot, paginate all records, status → "Browsing" | `get_snapshot()` |
| Result table row | Click | Select row → populate Selected Part Details; persists across page/qty changes; clears on incompatible query/filter/source change | `_render_paginated_table` selection contract |
| Pagination | Prev/Next/page | Page the already-filtered set; no new fetch; selection persists | `pagination.paginate/clamp_page` |
| Quantity −/+/edit | Click/type | Adjust quantity shown next to Add to BOM; no BOM effect until Add | local widget state |
| Add to BOM | Click | New canonical row via standard sourcing decision; inline confirmation; purchasing goes stale | `start_manual_bom_workflow`, `ActiveBomState.add_row`, `apply_replacement` |
| Build quantity stepper | Change | Updates config value only; does not touch existing rows by itself | `cfg_build_quantity` |
| Apply to uploaded lines | Click | Recomputes qty/status/notes for uploaded-origin rows only | `_apply_build_quantity` → `apply_project_quantities`, `update_row` |
| Project Name / Description | Type | Live editable fields; persisted in run config; read by next Upload/write | `cfg_project_name/_description` |
| Customer Reference field → Edit | Click | Opens popover: type selector (PRJ/INV/RND), builder fields, live validity preview, Apply to all / per-line overrides, +Add code | `build_project_reference/build_rnd_reference/build_inventory_reference`, `validate_customer_reference`, `update_row` |
| Update PartsBox Project | Toggle | OFF = never writes; ON = next Upload creates/reuses project+storage and adds matched entries; snapshot invalidated after write | `run_bom_workflow(run_partsbox=True)`, `invalidate_partsbox_snapshot` |
| Working Parts List search/filters | Type/select | Local filter over canonical rows, live, no fetch | `search_and_filter`, `RESULTS_SEARCH_FIELDS` |
| Working Parts List Customer Reference cell | Click → edit | Inline edit, validates, writes that row only | `validate_customer_reference`, `update_row` |
| Needs Review queue item | Click | Loads line into detail pane; clears other line's open replacement search | `selected_review_row_id` |
| Retry Exact | Click | Re-runs exact sourcing against selected suppliers; resolves or stays in queue; purchasing stale | `retry_exact_sourcing`, `refresh_response_snapshot` |
| Find Replacement | Click | Opens supplier-mode replacement search, prefilled query, quick MPN/description chips | `build_query_from_bom_row`, `search_components` |
| Check PartsBox | Click | Opens PartsBox-mode replacement search (local snapshot filter) + "Covers qty?" column | shared snapshot + `search_and_filter` |
| Use Selected Replacement | Click | Re-sources line to candidate; closes panel; resolves review if applicable; purchasing stale | `apply_replacement`, `refresh_response_snapshot` |
| Regenerate Purchasing | Click | Only action that creates purchasing artifacts (exports + DigiKey MyList); per-artifact status updates independently | `regenerate_purchasing(run_digikey_mylist=True)` |
| Download buttons | Click | Download file as-is; disabled when stale/failed | `show_download` over `outputs[...]` |

## 2. Reuse matrix

| Design component | Current implementation | Decision | Required Claude Code action |
|---|---|---|---|
| AppHeader | `render_app_header()` | USE AS-IS | Keep; only adjust `_HEADER_CSS` sizing if needed |
| Sidebar navigation | `st.sidebar.radio(...)` | RETIRE | Delete; single-page `render_autobom_workflow_page()` becomes the whole app |
| SearchField | `search_event_input()` | USE AS-IS | Keep component untouched; restyle only via its own `_CSS` (height, radius) |
| SourceSelection / `_authoritative_sources` | `component_search_partsbox/_mouser/_digikey`, `_authoritative_sources()` | USE AS-IS | Keep keys and function; do not rename without updating every caller in the wiring map (audit §4) |
| UploadControl | `render_upload_intake()` | ADAPT | Same logic; wrap in the compact idle/processing/done visual states. No behavior change (still auto-process-once via `file_id`) |
| Filter engine | `record_filter.py` | USE AS-IS | No changes. UI only decides placement (rail vs popover) |
| Dynamic facets | `render_dynamic_facet_filters`, `_membership_facet_filters` | ADAPT | Same `generate_facets` calls; new rendering as expander/checkbox groups instead of `st.selectbox`/`st.multiselect` rows. Same filter dict shape out |
| Pagination | `pagination.py`, `_pagination_controls` | USE AS-IS | Keep `result_signature` inputs unchanged; only restyle the Prev/Next/page chips |
| PartsBox results (embedded) | Inline block in `render_component_search_intake()` | EXTRACT + ADAPT | Extract into `render_partsbox_results_card(records, snapshot, lazy_state)`; add the Browse Inventory lazy-load affordance |
| Supplier results (embedded) | Inline block in `render_component_search_intake()` | EXTRACT | Extract into `render_supplier_results_card(records, search_state)`; keep `search_components` call-site logic unchanged |
| Standalone PartsBox Inventory page | `render_partsbox_inventory_page()` | RETIRE (presentation) | Delete the page function and its `inventory_*` render helpers; its Browse behavior is absorbed into the embedded PartsBox card (item above) |
| Storage Locations sub-view | `render_partsbox_storage_locations()` | RETIRE | Delete. The snapshot already carries `storage_by_id`; this was a redundant second read per audit §5 |
| Selected Part Details (Search) | `render_selected_part_details()` | ADAPT | Becomes `render_selected_part_card(candidate)`, used by both PartsBox and Supplier selections |
| Selected Part Details (Inventory) | `render_inventory_selected_part_details()` | RETIRE | Delete; `inventory_selected_part` state removed; the one card above covers this case (browse selections use the same session key as search) |
| Add to BOM | `_add_search_result_to_working_bom()` | USE AS-IS | Keep function and its no-`st.rerun()` reasoning; only the button's visual position changes |
| Configuration | `render_configuration_section()` | ADAPT | Same widgets/keys, denser 2-column layout, moved to the upper-right card |
| Update PartsBox Project toggle | `cfg_update_partsbox_project` checkbox | ADAPT | Same key; wrap in the amber "writes to PartsBox" visual container, `st.toggle` instead of `st.checkbox` if using 1.64's toggle, same session value |
| Customer Reference | `render_customer_reference_section()` + `_render_project_pcb_reference/_render_rnd_reference/_render_inventory_reference/_render_customer_reference_overrides/_render_add_approved_code` | ADAPT | Wrap the existing radio + sub-renderers in an `st.popover`; keep every widget key and function; only container/visual chrome changes |
| Working Parts List | `render_results_workspace()` / `render_results_table()` | ADAPT | Same `ActiveBomState.rows()`/`summary_counts()`/`search_and_filter()`; swap `st.dataframe` styling for compact rows + `st.badge` count chips |
| Needs Review | `render_needs_review()`, `render_replacement_lookup()` | ADAPT | Same actions/state; move from `st.tabs`+`st.expander` per row into the two-pane queue/detail layout. Keep `selected_review_row_id`, `replacement_lookup_sources`, per-row `replacement_query_/results_/selected_` keys |
| Purchasing Handoff | `render_purchasing_handoff_section()` | ADAPT | Same `build_purchasing_summary()`/`regenerate_purchasing()`; restyle into status-pill + 3-column card |
| Inventory location recommender | `recommend_location()` | ADAPT (bounded) | Add an optional snapshot/inventory-record parameter so the UI can pass the warm snapshot instead of triggering its own `get_parts()`/`storage/all`/`project/all` (audit §8) |
| PartsBox stock/location join | `component_lookup._partsbox_part_to_result()` | RETIRE (from UI path) | Never call this path for PartsBox display; the embedded card and any code touching it must use `partsbox_inventory.get_snapshot()` |

---

## 3. Current code → new design map

- New Search → `search_event_input()` (unchanged) + new `render_intake_card()` wrapper.
- New PartsBox Results → `get_partsbox_snapshot()` + `search_and_filter()`, extracted into `render_partsbox_results_card()`.
- New Supplier Results → `search_components(LookupQuery(...))` on `.submitted`, extracted into `render_supplier_results_card()`.
- New Configuration Card → `render_configuration_section()`, restyled, same session keys (`cfg_*`).
- New Selected Part Card → merge of `render_selected_part_details()` and `render_inventory_selected_part_details()` into one `render_selected_part_card(candidate)`.
- New Working Parts List → `active_bom_state.rows()`, `summary_counts()`, `search_and_filter()` (unchanged), restyled table.
- New Needs Review → `active_bom_state.review_items()`, `retry_exact_sourcing()`, `build_query_from_bom_row()`, `apply_replacement()` (unchanged), restyled two-pane layout.
- New Purchasing Handoff → `build_purchasing_summary()`, `regenerate_purchasing()` (unchanged), restyled card.
- New Filter Rail/Popover → `generate_facets()`, `search_and_filter()`, `apply_filters()`, `parse_engineering_value()` (unchanged), two render placements sharing one `render_filter_panel()`.

---

## 4. Required extractions

**1. `search_controller.compute_results(search_state, sources, filters, manufacturer_filter)`**
- Current location: inline in `render_component_search_intake()` (≈180 lines mixing widget rendering with the PartsBox-load-gate, filter application, and 3-way layout branch).
- Current responsibility: decide whether to load the PartsBox snapshot, run `search_and_filter` for both PartsBox and supplier records, and pick which of the three layout branches to render.
- Proposed boundary: a pure function that returns `(partsbox_records, partsbox_snapshot_generation, supplier_records)` given the search/filter/source inputs. Rendering (which cards, what width split) becomes the caller's job.
- Inputs: `live_text, manufacturer_filter, use_partsbox, use_mouser, use_digikey, filters, membership_filters`.
- Outputs: the three values above, unchanged in shape from today.
- Existing dependencies: `get_partsbox_snapshot`, `peek_partsbox_snapshot`, `search_and_filter`, `st.session_state["component_search_supplier_results"]`.
- Why: today the lazy-load gate, the filtering, and the 3-branch column layout are interleaved in one function. Splitting the data computation from the layout lets the new PartsBox-only / Supplier-only / 50-50 / stacked-at-1366 layouts share one result-computation path instead of duplicating filter calls per branch.

**2. `upload_controller.process_upload(uploaded_file, config, sources)`**
- Current location: inline in `render_upload_intake()`.
- Current responsibility: build the run workspace, save the file, call `run_bom_workflow`, decide merge-vs-replace, invalidate the snapshot on a write.
- Proposed boundary: return `(current_run, messages)`; leave `st.session_state` assignment and `st.rerun()` avoidance in the caller (the caller-side comment explaining why no rerun happens must stay).
- Inputs: `uploaded_file`, `build_quantity, project_name, project_description, run_partsbox`, `authoritative_sources`.
- Outputs: updated `current_run` dict, `messages/warnings/errors` lists.
- Existing dependencies: `build_run_workspace`, `save_uploaded_file`, `run_bom_workflow`, `ActiveBomState.add_rows`, `invalidate_partsbox_snapshot`.
- Why: keeps the same one-time-per-`file_id` guard and merge behavior while letting the compact upload-status visual states (idle/processing/done) be driven by a plain return value instead of reading five different session keys mid-render.

**3. Optional snapshot input on `recommend_location()`**
- Current location: `src/inventory_location_recommender.py`.
- Current responsibility: independently calls `get_parts()`, `storage/all`, `project/all` instead of consuming `PartsBoxInventorySnapshot`.
- Proposed boundary: add `snapshot=None` parameter; when provided, derive candidates from `snapshot.parts` instead of live calls; keep the existing client path when `snapshot` is omitted (non-UI callers, tests).
- Why: the UI already has a warm snapshot from `get_partsbox_snapshot()`; passing it into `_render_inventory_reference()`'s "Get Recommendations for All Parts" removes duplicate PartsBox API traffic and guarantees the recommendation and the displayed inventory use identical data (audit §8).

Do not extract further than this. Everything else in `app.py` (widget composition, layout, state keys) can be restyled in place.

---

## 5. Required adapters / view models

| Adapter | Existing sources | UI-facing output | Business logic that must stay outside it |
|---|---|---|---|
| `PartsBoxRowAdapter` | `InventoryPart.to_dict()` | `{mpn, manufacturer, description, stock, location_summary}` for the table row, plus the full `locations` list preserved for the detail card | Net-quantity math (`net_quantities_by_storage`), classification — untouched, read from the dict as-is |
| `SupplierRowAdapter` | `LookupResult.to_dict()` from `search_components()` | `{source, mpn, manufacturer, description, stock, unit_price}` | Sourcing/matching decisions — none happen here, this is display-only |
| `SelectedPartViewModel` | Either adapter's full dict | One shape for `render_selected_part_card()`: `{kind, source_label, mpn, manufacturer, description, attributes[], partsbox_groups? , supplier_detail?}` | Grouping locations by `space_type` is pure display reshaping of already-classified data — must not re-derive classification |
| `FilterPanelViewModel` | `generate_facets()` output + current filter dict | `{stock, facet_groups[], active_chips[]}` ready for either rail or popover rendering | Filtering itself stays in `record_filter.apply_filters` |
| `PurchasingStatusViewModel` | `build_purchasing_summary()` | `{visual_status, label, pill_colors, mouser, digikey, regenerate_enabled}` | Status derivation stays in `derive_purchasing_status()`; this only maps status strings to pill presentation |

None of these adapters may recompute stock, classification, sourcing decisions, or purchasing readiness — they only reshape/rename fields the domain layer already produced.

---

## 6. Retirement list

| Item | Retire UI only? | Replace with | Underlying functionality preserved? |
|---|---|---|---|
| `st.sidebar.radio` navigation | Yes | Single continuous page | N/A — navigation was pure UI |
| `render_partsbox_inventory_page()` | Yes | Embedded `PartsBoxResultsCard` + Browse Inventory affordance | Yes — same snapshot, same filters, same pagination |
| `render_partsbox_storage_locations()` | Yes | Nothing — `storage_by_id` is already in the snapshot; no UI need for this second live read | Yes — the underlying `PartsBoxClient().list_storage_locations()` capability isn't deleted, just this redundant call-site (audit §5 explicitly flags this as removable) |
| `render_inventory_selected_part_details()` | Yes | Shared `render_selected_part_card()` | Yes |
| `inventory_selected_part` session state | Yes | `component_search_selected_part` (one selection contract) | N/A, was UI-only state |
| `inventory_storage_locations` session state | Yes | Removed with the storage-locations sub-view | N/A |
| Old full-width Configuration widgets | Visual only | Same widgets, 2-column compact card | Yes, same keys |
| Old plain Customer Reference layout | Visual only | Popover wrapper around the same builders | Yes, same keys and validators |

---

## 7. No-touch / protected systems

Confirmed by repository inspection — do not rebuild:

- `active_bom_state.ActiveBomState` and its mutation/derived-view methods.
- `partsbox_inventory.PartsBoxInventorySnapshot` / `InventoryPart` / cache lifecycle (`get_snapshot`, `refresh`, `invalidate`, `peek_snapshot`).
- `partsbox_inventory.net_quantities_by_storage()`.
- `storage_space_classifier` + `config/storage_space_rules.json`.
- `record_filter.py` (`search_and_filter`, `apply_filters`, `generate_facets`) and `engineering_units.py`.
- `pagination.py` (`paginate`, `clamp_page`, `result_signature`, `DEFAULT_PAGE_SIZE`).
- `search_events.search_event_input()` (the CCv2 debounce/Enter component) — restyle its CSS only.
- `component_lookup.search_components()` / `LookupQuery` and the Mouser/DigiKey clients.
- `sourcing_engine.py`, `review_actions.py` (`retry_exact_sourcing`, `apply_replacement`, `build_query_from_bom_row`).
- `customer_reference.py` (validation, builders) and `customer_reference_registry.py` + its JSON config.
- `inventory_location_recommender.recommend_location()` (only the bounded snapshot-parameter addition from §4 applies).
- `partsbox_project_builder.py` (project/storage creation, entry sync).
- `workflow_runner.py` (`run_bom_workflow`, `refresh_response_snapshot`, `derive_purchasing_status`, `build_purchasing_summary`, `regenerate_purchasing`).
- `mouser_export.py`, `digikey_list_export.py`, `digikey_mylists_client.py`.
- `run_workspace.py`, `run_retention.py`, `token_store.py`, all of `deploy/`.

---

## 8. State migration

**Remains canonical (do not rename without updating every reader):** `current_run` and its `_active_bom_state`; `component_search_partsbox/_mouser/_digikey`; `cfg_build_quantity/_project_name/_project_description/_update_partsbox_project`; `cref_*`; `upload_intake_processed_file_id`.

**Can be renamed safely (UI-only, no external readers besides `app.py` itself):** all `<prefix>_page_sig`/`_page_num` pagination keys; `component_search_facet_*`/`_range_*`/`_membership_*`; `results_filter_*`, `results_search`.

**Tied only to the old separate-page presentation — remove:** `inventory_selected_part`, `inventory_storage_locations`, `inventory_search_text`, `inventory_manufacturer`, `inventory_facet_*`/`_membership_*`/`_page_*`, `inventory_refresh_button`'s associated pattern (the embedded card gets its own single refresh action tied to `component_search_*`).

**Should move behind a clean controller:** the PartsBox-load gate and filter/branch logic currently inline in `render_component_search_intake()` — see `search_controller` in §4.

**Duplicate state to remove:** the two independent selected-part keys (`component_search_selected_part` vs `inventory_selected_part`) collapse into one, since there is only one embedded PartsBox result surface now.

---

## 9. Side-effect map

| Action | Read-only | Local state | Canonical BOM mutation | PartsBox write | Supplier API lookup | Purchasing artifact creation |
|---|---|---|---|---|---|---|
| Typing / PartsBox filter | ✓ (snapshot read on first char) | ✓ | | | | |
| Press Enter | | | | | ✓ | |
| Browse Inventory | ✓ | ✓ | | | | |
| Filter / page / select row | ✓ | ✓ | | | | |
| Add to BOM | | | ✓ | | possibly (via `apply_replacement`) | |
| Upload | | | ✓ | ✓ if toggle on | possibly | |
| Apply Build Quantity | | | ✓ | | | |
| Customer Reference apply/override | | | ✓ | | | |
| Get INV recommendations | ✓ | ✓ | | | | |
| Add approved project/PCB code | | | | (writes local registry JSON, not PartsBox) | | |
| Retry Exact | | | ✓ | | ✓ | |
| Find Replacement / Check PartsBox search | ✓ | ✓ | | | ✓ (suppliers) / read (PartsBox) | |
| Use Selected Replacement | | | ✓ | | possibly | |
| Download | ✓ | | | | | |
| Regenerate Purchasing | | | | | | ✓ (exports + DigiKey MyList) |

This table must not change as a result of the visual redesign. Any PR that touches these call sites should diff against this table.

---

## 10. Implementation order

1. Extract `search_controller.compute_results()` and `upload_controller.process_upload()` (§4); add the optional snapshot parameter to `recommend_location()`.
2. Remove `st.sidebar.radio`, `render_partsbox_inventory_page()`, `render_partsbox_storage_locations()`, and their session-state keys.
3. Build the new page shell: header, banner area, `rail | main` columns, width-bucket probe.
4. Wire Intake Card (search + upload + source selection) using the extracted controller.
5. Wire Filter Rail/Popover from the shared `render_filter_panel()`.
6. Wire the two Discovery Results cards with the reactive layout (50/50, PartsBox-only, Supplier-only).
7. Wire the unified Selected Part Card.
8. Wire Configuration + Customer Reference popover.
9. Wire Working Parts List.
10. Wire Needs Review (two-pane) including Replacement Search.
11. Wire Purchasing Handoff.
12. Apply the token CSS (§ of the design spec) scoped to `.st-key-ab-*`.
13. Responsive pass: verify 1920/1440/1366, confirm the rail collapses correctly below 1400 px main width.
14. Run the full existing test suite (509 tests) — none should need behavior changes; only `tests/test_app_navigation.py` (sidebar) and any test asserting the old page structure should need updating to match the new single-page shell.
15. Manual screenshot comparison against the 22 states in `AutoBOM Workspace.dc.html`.

---

## 11. Visual acceptance criteria

- [ ] Search dominates the upper workspace; Upload is compact and secondary.
- [ ] Filters are inline at desktop width; a popover below ~1400 px main width, same content.
- [ ] Configuration is upper-right, compact (no full-width single-value inputs).
- [ ] PartsBox and Supplier tables align in height and header style.
- [ ] Layout reacts correctly to source selection (50/50, PartsBox-only, Supplier-only, neither → warning).
- [ ] Selected Part appears directly below results, hidden entirely (not blank) when nothing is selected.
- [ ] A PartsBox part with multiple locations shows every one, grouped by storage space — never collapsed to one location.
- [ ] Working Parts List, Needs Review, and Purchasing are the same continuous page, not separate tabs/pages.
- [ ] Needs Review renders only when review count > 0.
- [ ] No section reserves visible height when it has nothing to show.
- [ ] Badges/pills are subtle (11–12px, soft backgrounds), never large or saturated except amber (review/stale/write) and red (error).
- [ ] 1920×1080 resembles the approved mockup; 1440×900 and 1366×768 remain fully usable with no overlap or clipped controls.
- [ ] The app never resembles default stacked Streamlit (no giant headers, no un-styled `st.subheader` stacks with full-width single-column inputs).

## 12. Functional acceptance criteria

- [ ] PartsBox search is live/debounced; no PartsBox API call fires on every keystroke (only the first snapshot load, then local filtering).
- [ ] Mouser/DigiKey are queried only on Enter, never from typing, filtering, or pagination.
- [ ] The three source checkboxes remain authoritative for Search, Upload, Add to BOM, Retry Exact, and Replacement search alike.
- [ ] A file is processed exactly once per `file_id`; re-render never reprocesses it.
- [ ] Search and Upload write into the same canonical `ActiveBomState`; nothing forks into a second BOM.
- [ ] Add to BOM never creates a purchasing artifact.
- [ ] Multi-location PartsBox parts display correctly (never one-location-per-part).
- [ ] Customer Reference supports and validates all three registry formats (PRJ/INV/RND) and per-row overrides.
- [ ] `Update PartsBox Project` triggers a real write only on upload processing when enabled, and this is visually explicit (never confused with the PartsBox search-source checkbox).
- [ ] Needs Review actions (Retry Exact, Find Replacement, Check PartsBox, Use Selected Replacement) behave exactly as before.
- [ ] Purchasing artifacts go stale after any canonical BOM mutation and only become current again after an explicit Regenerate Purchasing.
- [ ] Mouser output remains a manual-upload export; DigiKey output only ever shows identifiers the API actually returned; AutoBOM never checks out, pays, or submits an order.
