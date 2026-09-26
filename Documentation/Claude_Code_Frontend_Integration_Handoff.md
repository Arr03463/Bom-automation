# Claude Code Frontend Integration Handoff

**From:** Claude Design · **For:** Claude Code · **Artifact:** `frontend/AutoBOM Frontend.dc.html` + 9 child components + `frontend/sample_fixtures.js`

This is the actual front-end UI layer for AutoBOM — not screenshots. Every component listed below is a real, rendering, interactive piece with a defined props-in/events-out contract. Connect it to the real AutoBOM backend; do not reconstruct it from the visual design spec or the mockup screenshots.

---

## 0. What this package is and isn't

**Is:** a real component tree (10 files) that renders, takes real input (`<input>`, `<select>`, `<button>`, `<input type=file>`, `<input type=checkbox/radio>`), and holds real local UI state for interaction (which row is selected, which popover is open, what's typed). The root component (`AutoBOM Frontend.dc.html`) currently plays the role Claude Code's Streamlit page will play: it owns state and wires child components together, but every place it reads or writes "data" is clearly reading `window.AUTOBOM_SAMPLE` (from `sample_fixtures.js`) or synthesizing a plausible result locally (e.g. simulating an upload finishing after 900ms, simulating "Retry Exact" always succeeding).

**Isn't:** a backend. No PartsBox, Mouser, DigiKey, or AutoBOM service is called anywhere in this package. Stock numbers, sourcing decisions, Customer Reference validation, and purchasing status are all locally faked in the root component's demo logic — clearly separable from the presentational children, which have no knowledge of `AUTOBOM_SAMPLE` at all (they only see whatever props their parent passes).

**How to use it:** keep every child component file (`frontend/AppHeader.dc.html`, `FilterRail.dc.html`, `IntakeCard.dc.html`, `ConfigurationCard.dc.html`, `CustomerReferenceEditor.dc.html`, `DiscoveryResults.dc.html`, `SelectedPartCard.dc.html`, `WorkingPartsList.dc.html`, `NeedsReview.dc.html`, `PurchasingHandoff.dc.html`) as the UI structure. Reimplement the *root's* state/effects in Streamlit, replacing every demo behavior with the real service call named in §2 below, and delete `sample_fixtures.js` once real data flows in.

---

## 1. Component tree (as built)

```
AutoBOM Frontend (root — owns state, demo data, event handlers)
├─ AppHeader                          title, subtitle, ownership marks
├─ FilterRail (×2 mounts: inline rail / compact popover)
│   stock radio + generic facet groups (categorical/membership/range)
├─ IntakeCard
│   real <input> search box, real checkboxes (sources), real <input type=file> upload
├─ ConfigurationCard
│   real numeric/text inputs, write toggle (real <button role=switch>)
│   └─ CustomerReferenceEditor (popover, mounted conditionally)
│       segmented type selector, registry selects, live preview, per-line INV recommendations
├─ DiscoveryResults
│   ├─ PartsBox results (real radio-selectable rows, real Prev/Next)
│   └─ Supplier results (same pattern)
├─ SelectedPartCard             hidden entirely when nothing selected
├─ WorkingPartsList             real inline-editable Customer Reference cell
├─ NeedsReview                  queue + detail + replacement search (reuses row-select pattern)
└─ PurchasingHandoff            status pill, per-supplier panel, Regenerate button
```

Every child is a standalone `.dc.html` file with its own `data-props` contract (visible in the editor's Tweaks panel metadata) — this doubles as machine-readable documentation of every input/event each component expects.

---

## 2. Frontend Component → Existing AutoBOM Target

| Frontend Component | Required Data (props) | Events/Actions (emitted) | Existing AutoBOM Target | Integration Gap |
|---|---|---|---|---|
| **AppHeader** | `title, subtitle, showMarks` | none | Static; matches `render_app_header()` | NONE — direct |
| **FilterRail** | `stockValue, facetGroups[], activeCount` | `onStockChange, onFacetToggle, onRangeChange, onClearAll` | `record_filter.generate_facets()` output reshaped 1:1 into `facetGroups`; `apply_filters()` consumes the selections back | NONE — direct (facetGroups is the same shape `generate_facets` already returns, keyed differently) |
| **IntakeCard** — search | `query, typing, sources{}` | `onQueryChange, onSubmit` | `search_event_input()` (debounce/Enter), `get_partsbox_snapshot()`, `search_and_filter()`, `search_components()` | THIN ADAPTER — swap the fake local-array filtering in the root demo for real calls; the search component itself (`search_event_input`) already produces exactly `{value, submitted}`, which maps directly onto `query`/`onSubmit` |
| **IntakeCard** — upload | `upload{state,fileName,message}` | `onFileSelected(file)` | `build_run_workspace`, `save_uploaded_file`, `run_bom_workflow`, `ActiveBomState.add_rows` | THIN ADAPTER — `onFileSelected` receives a real `File` object; call the existing upload pipeline synchronously (or via Streamlit's natural rerun) instead of the demo's `setTimeout` |
| **IntakeCard** — sources | `sources{partsbox,mouser,digikey}` | `onSourceToggle(key)` | `component_search_partsbox/_mouser/_digikey`, `_authoritative_sources()` | NONE — direct, same three booleans |
| **IntakeCard** — filter chips / refresh | `activeChips[], snapshotStatus{}` | `onClearChip, onRefresh` | filter session keys; `get_snapshot(force_refresh=True)` | NONE — direct |
| **ConfigurationCard** | `buildQuantity, projectName, projectDescription, customerReferenceSummary{}, updatePartsBoxProject` | `onBuildQuantityChange, onApplyBuildQuantity, onProjectNameChange, onProjectDescriptionChange, onEditCustomerReference, onToggleUpdatePartsBoxProject` | `cfg_build_quantity/_project_name/_project_description/_update_partsbox_project`; `_apply_build_quantity()` | NONE — direct, same fields |
| **CustomerReferenceEditor** | `type, registry{}, prj{}, rnd{}, recommendations, preview{}` | `onTypeChange, onPrjProjectChange, onPrjPcbChange, onRndProjectChange, onRndOwnerChange, onGetRecommendations, onSaveRowLocation, onApplyAll, onAddCode, onClose` | `customer_reference_registry.py` (`get_projects/get_pcb_codes/add_project/add_pcb_code`), `build_project_reference/build_rnd_reference/build_inventory_reference`, `validate_customer_reference`, `recommend_location()`, `ActiveBomState.update_row` | THIN ADAPTER — `preview` is exactly `validate_customer_reference()`'s return shape renamed; `recommendations` is `recommend_location()`'s return list reshaped per row |
| **DiscoveryResults** — PartsBox | `partsbox{state,rows[],count,page,totalPages,selectedId}` | `onPartsboxRowSelect, onPartsboxPageChange, onBrowseInventory` | `PartsBoxInventorySnapshot`/`InventoryPart.to_dict()`, `pagination.paginate/clamp_page` | THIN ADAPTER — `rows[]` is `InventoryPart.to_dict()` records reshaped to `{id,mpn,manufacturer,description,stock,locationSummary}`; `id` should be `part_id`. **Fixed page size (14/page today, tune per §5) and a fixed table-body height regardless of result count are load-bearing** — see §5 |
| **DiscoveryResults** — Supplier | `suppliers{state,rows[],count,page,totalPages,selectedId,errorText}` | `onSupplierRowSelect, onSupplierPageChange` | `LookupResult.to_dict()` from `search_components()` | THIN ADAPTER — same reshape, `id` should be a stable `source+mpn` composite. Same fixed-height/paginated contract as PartsBox, and the two cards share `align-items:stretch` so they're always equal height |
| **ComponentCharacteristics** (new) | `available[]: {field,label,values:[{value,count}]}, active: string[], values: Record<field,value>` | `onAddCharacteristic, onRemoveCharacteristic, onValueChange` | `record_filter.generate_facets()` over engineering/parametric fields (resistance, tolerance, package, voltage, dielectric, …) + `apply_filters()`/`parse_engineering_value()` for the selected values | NONE — direct. This is the **same filter engine** as Basic Filters, just a second UI surface over parametric fields instead of categorical/location fields. `available` must only ever list fields with at least one non-empty value in the current (pre-characteristic) result set — never a fixed engineering-parameter list |
| **SelectedPartCard** | `selected{kind,sourceLabel,mpn,manufacturer,description,attributes[],partsboxGroups?,supplierDetail?}, qty` | `onQtyChange, onAdd` | Selected-record session state; `InventoryPart.locations` grouped by `space_type`; `start_manual_bom_workflow/ActiveBomState.add_row/apply_replacement` | THIN ADAPTER (grouping-by-space_type reshape) + DIRECT (Add to BOM call) |
| **WorkingPartsList** | `rows[], counts[], searchValue, sourceFilter, statusFilter, page, totalPages` | `onSearchChange, onSourceFilterChange, onStatusFilterChange, onCustomerReferenceEdit(rowId,value), onPageChange` | `ActiveBomState.rows()`, `summary_counts()`, `search_and_filter(RESULTS_SEARCH_FIELDS)`, `update_row`, `pagination.paginate/clamp_page` | THIN ADAPTER — presentation-only pagination in front of the canonical rows (see §13.4). `rows[]` fields otherwise match `ActiveBomState` row dict keys already |
| **NeedsReview** | `items[], activeItem, replacement{mode,query,rows,selectedId}` | `onSelectItem, onRetryExact, onFindReplacement, onCheckPartsBox, onReplacementQueryChange, onReplacementSearch, onReplacementRowSelect, onUseSelectedReplacement` | `ActiveBomState.review_items()`, `retry_exact_sourcing`, `build_query_from_bom_row`, `search_components`/snapshot filter, `apply_replacement` | NONE — direct, same action set as today's `render_needs_review`/`render_replacement_lookup` |
| **PurchasingHandoff** | `status, label, sub, mouser{}, digikey{}, canRegenerate, regenerating, otherOutputs[]` | `onRegenerate, onDownload(key)` | `build_purchasing_summary()`, `derive_purchasing_status()`, `regenerate_purchasing()`, `show_download` | THIN ADAPTER — `status`/`label` is `derive_purchasing_status()`'s string mapped through the 5-entry pill-color table already in `PurchasingHandoff.dc.html`'s logic; everything else is a direct field read |

**No row in this table is BACKEND CHANGE REQUIRED.** Every frontend need is satisfiable by an existing function, with at most a thin reshape (renaming/regrouping fields the domain layer already returns) — consistent with `Claude_Code_UI_Implementation_Handoff.md` §0–§1b, which this table specializes down to the actual component boundaries now that they exist as real files.

---

## 3. Old UI retirement (unchanged from the prior handoff, restated against the real components)

| Old UI | Superseded by | Underlying functionality |
|---|---|---|
| `st.sidebar.radio` navigation | Single continuous page hosting all components above | N/A — was pure navigation |
| `render_partsbox_inventory_page()` | `DiscoveryResults`' PartsBox side + its `onBrowseInventory` | `PartsBoxInventorySnapshot` unchanged |
| `render_partsbox_storage_locations()` | Nothing — `storage_by_id` is already in the snapshot | `PartsBoxClient.list_storage_locations()` capability preserved, just this call-site removed |
| `render_selected_part_details()` + `render_inventory_selected_part_details()` | `SelectedPartCard` (one component, two `kind` branches) | Same data, one presentation path |
| `inventory_selected_part` / `inventory_storage_locations` state | Root-level `selectedPbId`/`selectedSupId` equivalent in the real Streamlit state | N/A — UI-only state |
| Old full-width Configuration inputs | `ConfigurationCard` | Same `cfg_*` keys |
| Old plain Customer Reference section | `CustomerReferenceEditor` popover | Same builders/validators |

---

## 4. Protected systems — unchanged

Same list as `Claude_Code_UI_Implementation_Handoff.md` §7: `ActiveBomState`, `PartsBoxInventorySnapshot`/`InventoryPart`, `net_quantities_by_storage`, `storage_space_classifier`, `record_filter`, `pagination`, `search_events.search_event_input()`, `component_lookup.search_components()`, `sourcing_engine`, `review_actions`, `customer_reference*`, `inventory_location_recommender`, `partsbox_project_builder`, `workflow_runner`, export/MyList modules. This frontend package consumes them through the reshapes in §2 — it never reimplements any of their logic.

---

## 5. Wiring the real thing: practical notes

- **The root component is a Streamlit stand-in.** Its `state = {...}` and the giant `renderVals()` at the bottom of `AutoBOM Frontend.dc.html` is exactly the shape of the `st.session_state` reads/writes and the render-time computed values `app.py` needs per rerun. Read it as pseudocode for the real page's data flow, not as code to port verbatim (there is no `st.session_state`, `st.rerun()`, or widget-key model in a DC — Streamlit's rerun-per-interaction model replaces this component's `setState` calls one-for-one).
- **Working Parts List height is fixed, independent of BOM size.** `WorkingPartsList` paginates its own `rows[]` prop internally at `DEFAULT_WORKING_LIST_PAGE_SIZE = 10` (a local constant in the component today — Claude Code should back it with `pagination.paginate()`/`clamp_page()`, the same shared helper the PartsBox/Supplier/Replacement tables already use, rather than a second pagination engine). Order of operations, same as every other table in this app: canonical rows → `search_and_filter()` (search text, then Source, then Status) → `paginate()` → render only the current page. Any filter/search change resets to page 1. Pagination never mutates `ActiveBomState` — it is presentation only, same list underneath every page. Discovery tables stay at 20/page (they're what the operator is actively browsing); the Working List is 10/page so Needs Review and Purchasing Handoff stay within roughly one scroll of it regardless of BOM size — a 5-line BOM and a 500-line BOM produce the same card height, and the pagination bar itself hides (showing just a line count) whenever everything already fits on one page.
- **Discovery Results (PartsBox/Supplier) height is ALSO fixed, independent of result count — same principle, tighter page size.** A 5-result search and a 3,448-part Browse Inventory must render the same card height. `DiscoveryResults` fixes each table body to `PAGE_SIZE * ROW_HEIGHT` (14 rows × 32px today — tune the row count during implementation, target 12–15 per the correction brief, backed by real `pagination.paginate()`/`clamp_page()` rather than the local constant the demo uses) and slices to the current page *before* rendering — the root component must compute `pbFiltered`/`supFiltered` (full filtered set, after Basic Filters + Component Characteristics + search) first, then slice that array to the current page, and pass only the current page's rows down; never pass the full filtered array to the results card. Any filter, search, source-toggle, or characteristic change resets both `pbPage` and `supPage` to 1. PartsBox and Supplier cards share `align-items:stretch` in their row so they are always equal height regardless of which has more results.
- **Component Characteristics is a second UI surface over the same shared filter engine, not a new one.** It lives directly under the Search/Upload/Source row (never in the left rail), defaults collapsed (showing only active-filter chips), and its available fields are computed exactly like Basic Filters' facets: only parametric fields (resistance, tolerance, package, voltage, dielectric, etc.) that have at least one non-empty value in the *current* result set are offered — never a fixed engineering-parameter list, and never invented for a dataset that doesn't have it. Selecting a value narrows the same `pbFiltered`/`supFiltered` pipeline Basic Filters narrows; there is exactly one filtered-result computation, with two UI entry points into it.
- **Left Filter Rail stays bounded regardless of dataset size.** Any membership list (Location, Manufacturer, Project, …) longer than ~8 values shows the top 8 by count plus a search box and a "Show N more" expand — never a full unbounded checkbox list. This is what keeps the rail's height tracking the Discovery Results row instead of growing without limit as more location/manufacturer values appear in the data.
- **Sample data isolation:** every read of fake data goes through `window.AUTOBOM_SAMPLE` (from `frontend/sample_fixtures.js`) or a demo-only `setTimeout`. Search the root file for `F.` (the local alias for `AUTOBOM_SAMPLE`) to find every point that needs a real data source; there are no other places data is fabricated.
- **Real behaviors already correctly modeled** (keep this behavior, just swap the data source): PartsBox typing filters locally and does not "call" anything until a query exists; Supplier results only populate on Enter (`onSubmit`), never from typing; unchecking a source clears the corresponding selection; Add to BOM shows an inline confirmation and marks purchasing "stale"; Regenerate is blocked while any review item exists; the Customer Reference preview is invalid (and Apply disabled) until required fields are filled.
- **Component boundaries are intentionally coarser than one-control-per-file** (e.g. `IntakeCard` bundles Search+Upload+Sources, `DiscoveryResults` bundles both result tables) because those pieces render together as one card in the approved visual design and share layout/react-to-each-other — splitting further would not simplify the Streamlit wiring and was avoided per the project's "high bar for splitting" default.

---

## 6. Responsive behavior (already wired, not just described)

The viewport switcher in the review toolbar at the top of `AutoBOM Frontend.dc.html` actually re-renders the composed layout at 1920/1440/1366 CSS px (via a measured scale-to-fit wrapper, same technique used in the earlier mockup). At 1366, `FilterRail` unmounts from the inline rail position and mounts instead inside a popover triggered by `IntakeCard`'s `Filters (n)` button (`compact`/`onOpenFilters` props) — this is a real conditional mount, not a screenshot of two states.
