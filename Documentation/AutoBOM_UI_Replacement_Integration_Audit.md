# AutoBOM UI Replacement Integration Audit

**Audit date:** 2026-09-25  
**Repository baseline:** `bd88be0`  
**Scope:** Current repository architecture and UI integration. Audit only; no application code was changed.

## 1. Executive verdict

AutoBOM can now be treated as an **existing functional system with a replaceable/recomposable Streamlit presentation layer**. The application does not need to be rebuilt.

The shared PartsBox snapshot, multi-location inventory model, signed-ledger aggregation, storage-space classifier, filter engine, pagination helper, live-versus-Enter search event, authoritative supplier selection, canonical BOM state, review mutations, artifact freshness, and purchasing boundary are implemented and tested.

Claude Design can design the final home workspace now. The design must use the data and action contracts in this report and must not invent unsupported fields or side effects.

Two technical limitations should remain visible in the handoff:

1. The location recommender shares the canonical ledger and classification functions but still performs its own PartsBox reads and join instead of consuming `PartsBoxInventorySnapshot` directly. This is a small implementation cleanup, not a missing UI capability.
2. Project classification is confirmed. Every non-project location currently defaults to Development because no live Mechanical/Other tagging convention has been configured. The data model supports Mechanical and Other, but the current classifications must not be presented as independently verified taxonomy.

**Primary decision:** proceed directly to Claude Design, then have Claude Code wire the approved design to the existing services. Perform the two bounded cleanups above during the UI implementation when the affected seams are touched; they do not justify delaying visual design.

## 2. Current architecture summary

```text
Streamlit presentation and workflow glue (app.py)
    |
    +-- search event adapter ---------------- src/search_events.py
    +-- shared search/result model ---------- src/component_lookup.py
    +-- complete PartsBox snapshot ---------- src/partsbox_inventory.py
    +-- storage classification -------------- src/storage_space_classifier.py
    +-- shared filters/units ---------------- src/record_filter.py / engineering_units.py
    +-- shared pagination ------------------- src/pagination.py
    +-- canonical Working Parts List -------- src/active_bom_state.py
    +-- sourcing decisions ------------------ src/sourcing_engine.py
    +-- review mutation seams --------------- src/review_actions.py
    +-- customer-reference rules ------------ src/customer_reference*.py
    +-- inventory recommendation ------------ src/inventory_location_recommender.py
    +-- workflow/artifacts/purchasing -------- src/workflow_runner.py
    +-- PartsBox writes ---------------------- src/partsbox_project_builder.py
    +-- exports/MyList adapters -------------- dedicated generator/client modules
```

The 509-test suite passes on the audited baseline. Streamlit is pinned to 1.64.0, and the custom event adapter uses its Custom Components v2 interface.

## 3. UI/backend boundary

### Domain and service layer that already exists

- Component query/result structures and supplier adapters.
- Complete cached PartsBox inventory snapshot.
- Per-part zero-or-more current locations.
- Per-location stock quantities and total stock.
- Project/location classification and configurable future spaces.
- Shared filtering, facet values, unit parsing, and pagination slicing.
- One canonical mutable BOM through `ActiveBomState`.
- One sourcing decision engine.
- Review/replacement mutation functions.
- Customer Reference construction and validation.
- Inventory location recommendation.
- PartsBox project/storage and entry writes.
- Artifact freshness and purchasing readiness.
- Mouser and DigiKey export generation.
- DigiKey MyList generation at the purchasing boundary.

### Presentation and workflow glue still in `app.py`

- Section ordering and navigation.
- Search source checkboxes and search event orchestration.
- PartsBox/supplier column selection.
- Filter widget construction.
- Page-number widget state.
- Selected-row persistence and detail rendering.
- Automatic upload triggering and merge orchestration.
- Calls from UI actions into domain mutation functions.
- Configuration and Customer Reference widget composition.
- Results, Needs Review, and Purchasing presentation.

`app.py` is not pure presentation. It contains important orchestration, but the underlying decisions and mutations are largely extracted. A UI replacement may substantially reorganize it if the orchestration contracts below are preserved or moved into small controllers during implementation.

## 4. UI wiring map

| New UI element | Existing function/service to call or preserve |
|---|---|
| Search bar | `search_events.search_event_input()` |
| Live PartsBox results | `partsbox_inventory.get_snapshot()` then `record_filter.search_and_filter()` over `InventoryPart.to_dict()` records |
| Mouser/DigiKey results | `component_lookup.search_components(LookupQuery(...sources...))`, only from the Enter `submitted` event |
| Source selectors | Existing `component_search_partsbox/mouser/digikey` state and `_authoritative_sources()` semantics; supplier selection must flow into upload/add/retry/replacement |
| Shared filters | `record_filter.generate_facets()`, `search_and_filter()`, `apply_filters()`, and `engineering_units.parse_engineering_value()` |
| Pagination | `pagination.paginate()`, `result_signature()`, `clamp_page()`, and `DEFAULT_PAGE_SIZE` |
| PartsBox results table | Enriched `InventoryPart.to_dict()` records from the shared snapshot |
| Supplier results table | Normalized lookup-result dictionaries returned by `search_components()` |
| Selected Part Details | Selected normalized record held in session state; location list is already embedded for PartsBox records |
| Add to BOM | `start_manual_bom_workflow()` when needed, `ActiveBomState.add_row()`, `review_actions.apply_replacement()`, then `refresh_response_snapshot()` |
| Upload control | `build_run_workspace()`, `save_uploaded_file()`, `run_bom_workflow()`, then `ActiveBomState.add_rows()` for merge |
| Configuration card | Existing `cfg_*` values; `run_bom_workflow()` inputs and `_apply_build_quantity()` |
| Customer Reference | `customer_reference` builders/validator, registry functions, and `ActiveBomState.update_row()` |
| Working Parts List | `ActiveBomState.rows()`, `summary_counts()`, and `update_row()` |
| Needs Review | `ActiveBomState.review_items()`, `retry_exact_sourcing()`, `build_query_from_bom_row()`, `apply_replacement()` |
| Inventory recommendation | `inventory_location_recommender.recommend_location()` |
| PartsBox project update | `run_bom_workflow(run_partsbox=True)` which calls `create_partsbox_project_and_storage()` and `add_bom_entries_to_project()` |
| Artifact freshness | `refresh_response_snapshot()`, `artifact_status`, and `derive_purchasing_status()` |
| Mouser handoff | Existing `mouser_export_csv` generated by `export_mouser_list()` |
| DigiKey handoff | `regenerate_purchasing(...run_digikey_mylist=True)` and existing MyList result fields |
| Purchasing panel | `build_purchasing_summary()` and the explicit `regenerate_purchasing()` action |

## 5. PartsBox inventory embedding assessment

The separate top-level PartsBox Inventory page can be removed without removing inventory capability.

The current main Search already uses the complete shared snapshot after the first nonblank PartsBox query, filters locally, paginates results, shows total stock, and stores the full current-location list on each selected record. The separate page uses the same snapshot and filter/pagination machinery. Its unique presentation can be recomposed into the home workspace.

Recommended embedded behavior:

```text
blank search + PartsBox selected
    -> expose a deliberate Browse Inventory affordance or the first inventory page

typed search
    -> local filtering over the cached complete snapshot

selected PartsBox row
    -> show total stock and all current locations grouped by storage space
```

Opening the ordinary AutoBOM home page should still avoid an unconditional full PartsBox fetch. A blank embedded inventory panel can show **Browse PartsBox inventory** until requested, or can load only when the operator expands/enters that panel. The design may choose the presentation, but it must preserve lazy loading.

The existing `render_partsbox_storage_locations()` performs a separate live `storage/all` request and stores another location list. That view is redundant once inventory is embedded because the snapshot already contains `storage_by_id`. Do not carry this second read path into the new UI.

## 6. PartsBox location/storage audit

The implemented domain shape matches the intended model:

```text
InventoryPart
    locations[]
        storage_id
        name
        quantity
        space_type
        optional project_name
```

A part is never collapsed to one storage space. `InventoryPart` exposes Development, Project, Mechanical, and Other location subsets plus distinct projects. `to_dict()` emits list-valued `location`, `storage_space`, and `project` fields for shared membership filtering.

Project classification uses the confirmed convention:

- storage name matches a PartsBox project name; and
- storage has the `production` tag.

Mechanical and Development tag lists are configurable in `config/storage_space_rules.json`. Adding a future space type requires a classifier/configuration extension, not changes to search or filter architecture.

### Current classification limitation

`default_classification` is `Development`, and both configured tag lists are empty. Therefore every location that is not a confirmed project is currently labeled Development. This matches the stated assumption that general component locations are the norm, but it does not independently prove that every unmatched location is electronic Development storage.

Claude Design may show the Storage Space field and design future Mechanical/Other choices. It should treat those future categories as extensibility, not imply that the current PartsBox account already has reliable Mechanical/Other membership.

## 7. Stock-ledger assessment

There is one shared quantity implementation: `partsbox_inventory.net_quantities_by_storage()`.

It:

1. accepts the raw signed `part/stock` ledger;
2. sums numeric transactions by `stock/storage-id`;
3. keeps only positive net balances;
4. feeds snapshot locations and total quantity;
5. is imported by the inventory recommender.

`InventoryPart.total_quantity` is the sum of the positive current-location quantities. Inventory display and location filters use the enriched snapshot. Historical zero/negative locations are excluded.

The supplied CSV independently supported this interpretation: all 3,242 located rows had location quantities equal to exported total Stock, and all 88 zero-stock rows lacked a current location.

One old plain PartsBox adapter remains in `component_lookup._partsbox_part_to_result()` and reports PartsBox stock as unknown because it does not join storage data. Active Main Search and Check PartsBox use the enriched snapshot, so the final UI must use the snapshot path for PartsBox inventory records. Do not wire the new inventory presentation to the old plain adapter.

## 8. Inventory recommendation assessment

The `INV-<LOCATION>` recommender now satisfies the Development-first rule.

- Exact-part recommendations first restrict candidates to classified Development locations.
- If several Development locations exist, it shows the one with most stock at reduced confidence.
- Project/Mechanical/Other-only evidence cannot become a high-confidence general inventory recommendation.
- Similar-part recommendations count Development locations separately and do not let project stock win.
- The returned recommendation remains advisory; the operator accepts or overrides it before `customer_reference` is updated.

Example behavior is correct:

```text
Development C1 = 10
Project Army = 100
-> recommend C1
```

### Bounded cleanup

The recommender imports the shared netting and classifier but independently calls `get_parts()`, `storage/all`, and `project/all`. It does not consume `PartsBoxInventorySnapshot`, despite comments in `app.py` describing it as a snapshot consumer.

During UI implementation, add an optional snapshot/inventory-record input to `recommend_location()` and make the UI pass the warm snapshot. Preserve the existing client path for non-UI callers if useful. This removes duplicate API traffic and ensures recommendation and display use the identical snapshot generation. It does not change the data shown to Claude Design.

## 9. Filter readiness

One shared engine in `record_filter.py` supports:

- text search;
- exact categorical filters;
- stock state;
- engineering-unit ranges;
- list-valued membership filters;
- dynamic facet generation.

Main Search, PartsBox Inventory, and Needs Review all reuse it. Pagination occurs after filtering.

Reliable current fields include:

- Manufacturer when populated;
- Source for mixed results;
- Stock and total PartsBox quantity;
- Storage Space;
- Location;
- Project;
- Category, package, lifecycle, and parametric values only when populated.

The observed PartsBox API did not populate category/package for this account. Claude Design should not reserve prominent permanent controls for empty fields. Filters should remain expandable and data-driven.

The current facet UI functions remain in `app.py`. Claude Code may freely replace their visual arrangement while retaining `record_filter` semantics.

## 10. Session-state contract

### Canonical/domain state

- `current_run`
  - `_active_bom_state`: canonical `ActiveBomState`;
  - `run`, `messages`, `warnings`, `errors`, `results_summary`;
  - `outputs`, `artifact_status`, `stale_after_mutation`;
  - `purchasing`, `_purchasing_raw`, `purchasing_regeneration_errors`;
  - `purchasing_regenerated_at_least_once`.

This object must survive visual reruns and section reordering.

### Source-selection state

- `component_search_partsbox`
- `component_search_mouser`
- `component_search_digikey`

Mouser/DigiKey values are read by `_authoritative_sources()` for Search, Upload, Add, Retry, and replacement re-sourcing. Preserve this single authority even if the keys are renamed.

### Search draft and committed-query state

- `component_search_event`: Custom Components v2 state/trigger container;
- `component_search_text`: latest debounced draft;
- `component_search_last_submitted`: supplier query and selected suppliers used on the last Enter;
- `component_search_manufacturer`.

### Search result state

- `component_search_supplier_results`: last committed external results;
- PartsBox results are derived from the process-wide snapshot on each relevant rerun rather than stored as a second session catalog.

### Filter state

- `component_search_stock_filter`;
- `component_search_facet_<field>`;
- `component_search_range_min_<field>` / `_max_<field>`;
- `component_search_membership_<field>`;
- corresponding `inventory_*` and replacement prefixes;
- Results workspace: `results_search`, `results_filter_source`, `results_filter_status`, `results_filter_manufacturer`, `results_filter_stock`.

### Pagination state

Each context uses `<prefix>_page_sig` and `<prefix>_page_num`, plus its previous/next/table widget keys. Result-defining changes reset the signature/page; selection and quantity do not.

### Selected-record state

- `component_search_selected_part`;
- `inventory_selected_part` on the soon-to-be-removed separate page;
- per-replacement selected table state is scoped by `row_id`.

The embedded final UI should use one clear selected PartsBox/search record contract and remove stale separate-page selection state.

### Upload state

- `upload_intake_file` widget state;
- `upload_intake_processed_file_id` duplicate-processing guard.

The current upload workflow runs once per `UploadedFile.file_id`. Preserve that guard or replace it with an equivalent fingerprint/state machine.

### Configuration state

- `cfg_build_quantity`;
- `cfg_project_name`;
- `cfg_project_description`;
- `cfg_update_partsbox_project`.

`cfg_update_partsbox_project` controls a real PartsBox write during automatic upload processing. The replacement UI must make this consequence obvious.

### Customer Reference state

- `cref_reference_type`;
- `cref_project`, `cref_pcbs`, `cref_rnd_project`, `cref_owner`;
- per-row `cref_inv_location_<row_id>` and `cref_override_<row_id>` values;
- recommendation dictionaries and registry-add fields under the `cref_*` prefix;
- canonical saved values live in `ActiveBomState.dataframe.customer_reference`.

Widget keys may change. Canonical row values, validation, and registry behavior must remain.

### Review state

- `selected_review_row_id`;
- `replacement_lookup_sources`;
- `replacement_query_<row_id>`;
- `replacement_results_<row_id>`;
- replacement facet, membership, selection, and pagination keys scoped by row ID.

### Purchasing/artifact state

Purchasing truth is stored in `current_run`, not in visual widget state. Preserve `artifact_status`, outputs, raw vendor results, errors, and the regeneration marker. A redesign must never derive readiness from button appearance or page position.

## 11. Side-effect boundaries

### No purchasing side effects

The following remain read-only with respect to carts/MyLists:

- typing or submitting Search;
- PartsBox browsing;
- supplier discovery;
- filtering, pagination, sorting, and selection;
- upload/import and normal BOM sourcing;
- Add to BOM;
- Retry/Find Replacement;
- Customer Reference changes.

Search and sourcing may call vendor lookup APIs. They do not create purchasing artifacts.

### PartsBox read boundary

`partsbox_inventory.get_snapshot()` calls `part/all`, `storage/all`, and `project/all`. Browsing, filtering, selecting, and refreshing this data perform reads only.

### PartsBox write boundary

`run_bom_workflow(run_partsbox=True)` calls:

- `create_partsbox_project_and_storage()`;
- `add_bom_entries_to_project()`.

The UI control is **Update PartsBox Project**. Current automatic upload processing executes this write when the option is enabled and a usable project name exists. Because the option currently defaults to true, Claude Design must present it prominently beside project/upload configuration and explain that it writes to PartsBox. It must not look like an inventory-search source toggle.

### Purchasing-artifact boundary

Only the **Regenerate Purchasing** handler calls `regenerate_purchasing(current_run, run_digikey_mylist=True)`. That function refreshes exports and may create a DigiKey MyList. Mouser's normal output is a downloadable export for manual upload; AutoBOM does not create a normal-flow Mouser cart.

## 12. `app.py` coupling

`app.py` is approximately 1,700 lines and mixes presentation with workflow orchestration. Business rules are mostly outside it, but these behaviors cannot be discarded with the old layout:

- Enter-only supplier calls versus debounced PartsBox filtering;
- lazy snapshot load;
- source-dependent result splitting;
- page reset signatures;
- selected-record persistence;
- one-time automatic upload processing;
- merging uploaded rows into existing canonical state;
- passing authoritative suppliers to Add/Retry/Replacement;
- snapshot invalidation after PartsBox writes;
- snapshot refresh after canonical BOM mutations;
- artifact staleness after BOM changes;
- explicit regeneration boundary.

### Minimum extraction during UI implementation

Extract only where it makes the approved UI safer to wire:

1. A search controller/service function that accepts the search event, selected sources, manufacturer, and existing supplier result state, returning PartsBox and supplier result sets without rendering widgets.
2. An upload orchestration function that processes/merges one uploaded file and returns the updated `current_run` plus messages.
3. Optional snapshot input for `recommend_location()`.

Do not delay Claude Design for these extractions. Their input/output contracts are already clear and do not alter the available user experience.

## 13. UI Replacement Safe Zone

Claude Code may freely replace or recompose:

- sidebar navigation, including removing the PartsBox Inventory destination;
- page and section order;
- columns, cards, containers, expanders, spacing, theme, and CSS;
- search and Upload positioning;
- source-selector presentation;
- filter controls and collapsed filter layout;
- result tables, column order, labels, and responsive layouts;
- selected-part detail presentation;
- embedded PartsBox inventory browsing;
- Working Parts List presentation;
- Configuration card layout;
- Customer Reference presentation;
- Needs Review presentation;
- Purchasing status and output presentation;
- messages, warnings, empty states, and loading indicators.

Visual replacements must continue to call the mapped services and preserve state/side-effect contracts.

## 14. Do Not Rebuild

The UI implementation should call and reuse these working subsystems:

- `ActiveBomState` and its mutation/derived-view seams;
- `LookupQuery`, normalized results, and supplier lookup adapters;
- `PartsBoxInventorySnapshot`, `InventoryPart`, and cache lifecycle;
- `net_quantities_by_storage()`;
- storage-space classifier and configuration;
- `record_filter` and `engineering_units`;
- pure pagination helpers;
- search event adapter;
- supplier clients and sourcing engine;
- review actions;
- Customer Reference validation and registry;
- inventory location recommender rules;
- PartsBox lifecycle/project builder;
- artifact freshness and purchasing summary;
- Mouser export, DigiKey export, and DigiKey MyList client;
- run workspaces, retention, token storage, and deployment infrastructure.

Do not create a second BOM model, inventory cache, filter engine, location classifier, pagination system, replacement search engine, purchasing state machine, or export pipeline.

## 15. Information Claude Design needs

### Available data

- PartsBox: stable part ID, MPN/name, manufacturer, description, optional category/package/characteristics, total current quantity, all positive current locations, per-location quantity, storage-space type, and project association.
- Supplier results: source, manufacturer, MPN, supplier part number, stock, unit price, category when returned, and raw adapter data.
- Working BOM: canonical normalized row fields, source/status, quantities, designators, customer reference, review reason, sourcing details, and artifact state.

### Available interactions

- Live debounced PartsBox search.
- Enter-triggered Mouser/DigiKey search.
- Source selection.
- Dynamic filters and membership facets.
- Twenty-row pagination.
- Single-row selection and details.
- Add selected part with quantity.
- Automatic CSV/XLSX import into the same BOM.
- Build quantity and project configuration.
- Customer Reference assignment and overrides.
- Retry exact sourcing and select replacements.
- Read-only inventory recommendations with operator override.
- Downloads and explicit purchasing regeneration.

### Source-dependent layout

- PartsBox only: inventory results full width.
- Suppliers only: combined supplier results full width.
- PartsBox plus suppliers: approximately 50/50.
- Supplier results can be one combined table with Source labels.

### Streamlit constraints

- The custom search field is the established way to distinguish debounced changes from Enter.
- Widget keys/session state must remain stable across reruns.
- Conditionally omitted widgets can lose widget-owned state; canonical values should remain in explicit session/domain state.
- Selecting dataframe rows causes reruns.
- The complete PartsBox snapshot is process-wide; UI state remains per session.
- Only the current page of results should render.

### Do not visually imply

- that every PartsBox record has Category, Package, or parametric fields;
- that Mechanical/Other classifications are currently populated or independently verified;
- that a part has only one location;
- that project stock is the preferred general inventory location;
- that PartsBox browsing moves or writes stock;
- that Add to BOM creates an order/cart/MyList;
- that Mouser has an automated normal-flow cart/share handoff;
- that DigiKey provides a separate confirmed share link when the API does not;
- that stale artifacts match the current BOM;
- that an inventory recommendation is an automatic placement decision;
- that the dated CSV is the full PartsBox inventory.

## 16. Pre-design implementation requirements

No implementation is required before Claude Design.

The design can safely target the normalized snapshot record, multi-location detail model, shared filters, selection actions, canonical Working Parts List, review actions, and purchasing summary already present.

The following are implementation notes for Claude Code, not blockers for Claude Design:

- make the recommender consume the warm snapshot;
- remove the redundant standalone storage-list API read;
- optionally extract search and upload orchestration from `app.py` while wiring the new layout;
- consolidate separate-page inventory selection state into the embedded workspace;
- keep Mechanical/Other display conditional on actual classified data.

## 17. Exact recommended next sequence

```text
Codex audit
    -> Claude Design presentation/UX design
    -> Claude Code UI replacement and bounded controller cleanup
    -> focused Codex verification of wiring, side effects, and state
    -> operator acceptance test
```

Claude Design should receive this audit as its backend contract. Claude Code should implement the approved composition around existing services and perform the bounded recommender/controller cleanup only where necessary to wire it safely.

## 18. Risks

| Risk | Required control |
|---|---|
| Replacing `app.py` drops orchestration hidden among render functions | Use the wiring map and preserve/extract each listed controller behavior. |
| Embedded blank inventory triggers a full API read on every home load | Keep the current lazy-load gate or an explicit Browse affordance. |
| Recommender duplicates PartsBox reads | Pass the cached snapshot during UI implementation. |
| Non-project locations are over-described as verified Development | Explain current default classification and render only populated spaces. |
| Automatic upload repeats after visual reruns | Preserve the processed-file ID/fingerprint guard. |
| Upload silently writes PartsBox because the option is visually buried | Make **Update PartsBox Project** explicit and adjacent to project/import configuration. |
| Source checkboxes become visual-only | Continue passing selected suppliers into Upload, Add, Retry, and Replacement. |
| Filters or pagination call suppliers again | External searches must remain tied only to the Enter submit event. |
| Selected records survive after incompatible result changes | Clear or validate selections when source/query identity changes. |
| Snapshot refresh races under several users | Keep one process; add refresh coalescing if real concurrent use demonstrates duplicate fetches. |
| New cards recreate hundreds of widgets | Retain paginated tables and one action/detail panel. |
| Design implies unsupported vendor handoff | Preserve Mouser manual export and DigiKey's actual returned identifiers only. |
| Purchasing artifacts become stale after mutations | Every canonical mutation must still call `refresh_response_snapshot()`. |

## Primary verdict

**UI REPLACEMENT CAN PROCEED DIRECTLY TO DESIGN**

**Recommended next step:** give Claude Design this audit and ask it to design the single embedded AutoBOM home workspace using the UI wiring map and state/side-effect contracts above. After design approval, have Claude Code replace the presentation while reusing the verified services and performing only the bounded recommender/search/upload controller cleanup identified here.
