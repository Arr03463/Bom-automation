# AutoBOM Search, Filter, and Inventory Architecture Audit

**Audit date:** 2026-09-25  
**Repository baseline:** `d1877fd`  
**Scope:** Architecture and UI audit only. No application behavior was implemented or changed.

## Executive conclusion

The current repository already contains the correct core seams for one AutoBOM system:

- `LookupQuery`, `LookupResult`, and `search_components()` provide one component discovery model.
- `record_filter` and `engineering_units` provide shared text, categorical, stock, and numeric-range filtering.
- `ActiveBomState` is the one canonical Working Parts List.
- Search additions, uploaded rows, and Needs Review replacements already converge on that state.
- `PartsBoxClient` is the shared PartsBox API boundary.
- PartsBox stock-ledger netting already excludes zero and negative balances correctly.

The requested behavior should extend those seams. It should not introduce page-specific search or filter engines.

Four architecture preconditions should be completed as part of the implementation pass:

1. Add one shared, cached PartsBox inventory snapshot that joins parts, current positive stock by location, storage metadata, and project conventions.
2. Upgrade the pinned Streamlit version from 1.62.0 to a tested release that supports native debounced live text input (Streamlit 1.64.0 at the time of this audit), then run the complete regression suite.
3. Add one minimal Enter-event adapter and shared search interaction controller that separate the live PartsBox query from the Enter-committed supplier query.
4. Make the selected source configuration authoritative for search additions, uploads, and later re-sourcing. The current UI claims this, but the code does not fully honor it.

**Verdict: READY WITH PRECONDITIONS.** The existing architecture does not require replacement. The preconditions are bounded extensions to shared services and state.

## Verification performed

- Traced `app.py`, component lookup, record filtering, engineering-unit parsing, PartsBox access, canonical BOM state, sourcing, review actions, inventory recommendations, purchasing boundaries, and related tests.
- Ran `python -m unittest discover -s tests -q`: **433 tests passed**.
- Confirmed the application is pinned to Streamlit **1.62.0**.
- Confirmed there is no current pagination helper or pagination state.
- Confirmed the PartsBox account observations recorded in code: approximately 3,450 parts, approximately 1,888 storage records, no populated `part/category` or `part/package` values in the observed `part/all` response, and `part/stock` represented as a signed per-storage ledger.
- Analyzed the operator-supplied `partsbox-parts.csv` export dated 2026-08-19 as an additional real-data snapshot. Detailed results appear below.
- Did not call PartsBox, Mouser, or DigiKey during this audit.

## Evidence from the supplied PartsBox export

The supplied CSV is a **dated, incomplete export snapshot**, not the full current PartsBox inventory and not a replacement runtime data source. The operator has confirmed that PartsBox contains more parts than this spreadsheet. It has four columns: `Part`, `Description`, `Stock`, and `Where is it?`.

### Measured dataset characteristics

| Measurement | Result |
|---|---:|
| Part rows | 3,330 |
| Rows with a description | 3,287 |
| Rows with current location text | 3,242 |
| Zero-stock rows | 88 |
| Rows held in multiple locations | 290 |
| Maximum current locations for one part | 9 |
| Distinct parsed location names | 821 |
| Duplicate `Part` display values | 5 |
| Non-numeric Stock values | 0 |
| Unparseable nonempty location strings | 0 |
| Rows where location quantities did not sum to Stock | 0 |

All 88 zero-stock rows are the rows without a current location string. Across all 3,242 located parts, the quantities in `Where is it?` sum exactly to the exported `Stock` value. This independently supports the current code's signed-ledger interpretation and the rule that zero/negative net locations are historical rather than present physical locations.

The CSV and the later code-recorded live API observation have different counts: 3,330 exported rows on 2026-08-19 versus approximately 3,450 API parts observed on 2026-09-24. The operator has also explicitly confirmed that the spreadsheet is not complete. The figures in this section describe only the supplied file; they must never be presented as the current PartsBox inventory count. The runtime UI must obtain the exact current count from the complete accessible `part/all` dataset. This reinforces the need for a TTL cache and visible snapshot timestamp rather than a bundled static catalog.

### What the export proves about the model

1. **Multiple location membership is real, not hypothetical.** At least 290 parts occupy multiple locations, including combinations of general bins and named projects. A single `Part.storage_space` or `Part.location` field would lose current inventory relationships.
2. **Project and Development stock coexist.** Examples contain a general location such as `C1 - (...)` plus several project-named locations. Inventory display and recommendations must classify each location independently.
3. **The total-stock calculation is testable.** The export provides a useful acceptance oracle: the sum of positive current per-location quantities must equal the displayed total for every exported row.
4. **Location options are too numerous for a permanent dropdown.** There are 821 distinct names. Location filtering must be searchable, dynamically narrowed, and kept inside the collapsed Filters area.
5. **Display names are not guaranteed unique part identities.** Five `Part` values are duplicated. Runtime joins and table selection must use the stable PartsBox `part/id`, never MPN/display text alone.
6. **Description search has high value.** Descriptions are present for 98.7% of rows. The export contains many human-readable package, voltage, tolerance, resistance, and capacitance expressions.

### What the export does not provide

The CSV has no stable part ID, manufacturer column, storage IDs, project IDs, storage tags, or raw stock transactions. It is also known to omit parts. It must not become AutoBOM's authoritative runtime catalog, determine the total Inventory count, or be used to infer project membership by string alone. Runtime Inventory still needs the complete accessible `part/all` response, `storage/all`, and the project/storage relationship.

The rich descriptions can support ordinary text search immediately. They should not silently become authoritative Category, Package, Voltage, or Tolerance facets through ad hoc regular expressions. If description-derived structured fields are added later, they should be produced once by a tested normalizer, retain provenance such as `derived_from_description`, and remain distinguishable from source-confirmed attributes.

## Current flow trace

### Manual component search

```text
app.render_component_search_intake
    -> Search button
    -> LookupQuery(selected PartsBox/Mouser/DigiKey sources)
    -> component_lookup.search_components
         -> PartsBoxClient.get_parts + local substring match
         -> MouserClient.search_candidates
         -> DigiKeyClient.search_candidates
    -> normalized LookupResult dictionaries
    -> record_filter facets and filters
    -> one set of quantity + Add to BOM widgets per result
    -> _add_search_result_to_working_bom
    -> ActiveBomState.add_row
    -> review_actions.apply_replacement
    -> sourcing_engine.source_row
    -> ActiveBomState.update_row
```

The normalized lookup and canonical mutation seams are reusable. The current trigger and renderer are the main problems: all selected sources execute together behind a Search button, and every result creates multiple Streamlit widgets.

### Upload

```text
st.file_uploader
    -> Process Upload button
    -> build_run_workspace + save_uploaded_file
    -> workflow_runner.run_bom_workflow
         -> parse/clean quantities
         -> optional Mouser/DigiKey sourcing
         -> optional PartsBox project/storage writes
         -> exports
    -> new ActiveBomState
    -> replace current_run, or ActiveBomState.add_rows into existing run
```

Upload and Search already feed one `ActiveBomState`. That should be preserved. The separate Process Upload button is unnecessary, but removing it requires an explicit upload state machine to avoid processing the same `UploadedFile` again on every rerun.

### PartsBox search

`search_components()` creates a `PartsBoxClient` unless one is injected. `PartsBoxClient.get_parts()` caches `part/all` only on that client instance. Because ordinary searches create a new client, the cache does not survive later searches or Streamlit reruns. Each fresh PartsBox search can therefore fetch the whole catalog again.

After fetch, `_search_partsbox()` scans the in-memory list and performs a case-insensitive substring match over MPN, manufacturer, and description. A catalog of roughly 3,450 records is small enough for local filtering; repeated network fetches are the actual risk.

### Mouser and DigiKey search

`component_lookup` calls each client's `search_candidates()` directly. These discovery calls do not use `SupplierLookupCache`; that persistent cache is used by `sourcing_engine`, not the general lookup path. Current supplier search therefore performs external calls whenever the Search button is pressed.

The clients return `SupplierResult` objects which are converted to `LookupResult`. Supplier descriptions and many parametric fields are sparse in the current adapter output, so filters must appear only when real values exist.

### Working Parts List

`st.session_state.current_run["_active_bom_state"]` holds the canonical `ActiveBomState`. Search uses `add_row()` followed by `apply_replacement()`. Upload uses `run_bom_workflow()` and merges with `add_rows()` when a Working Parts List already exists. Results, review, purchasing summaries, and exports derive from this state.

This is the correct convergence point. A new “search cart,” upload BOM, or inventory selection list must not be introduced.

### Filtering

`record_filter` currently provides:

- substring search across caller-selected fields;
- exact categorical filters;
- stock state filtering;
- numeric min/max filters using `engineering_units`;
- distinct-value facet generation.

Main Search and PartsBox Inventory call the dynamic facet renderer. Results/Review uses the same filtering functions with fixed fields. Needs Review replacement results currently do not expose shared filters.

The filter engine is reusable but needs extensions for multiselect filters, location/project membership, facet counts, normalized typed values, and a reusable UI specification. These extensions belong in the shared filter layer.

### PartsBox Inventory

The page is lazy in one important sense: normal AutoBOM startup does not call `part/all`, and navigating to the Inventory page alone still makes no API call. The operator must click **Search / Browse All**. The requested behavior is different: entering PartsBox Inventory should load the complete accessible inventory once and immediately show its first page.

The current page:

- can obtain all parts through an empty `LookupQuery`;
- stores results per browser session;
- applies filters before rendering;
- has no pagination;
- renders the complete filtered dataframe;
- loads storage locations separately behind another button;
- does not join stock ledgers to storage names, projects, or storage-space classifications;
- shows PartsBox stock as unknown even though a tested ledger summarizer exists elsewhere.

## Reuse map

| Existing capability | Reuse decision | Required extension |
|---|---|---|
| `LookupQuery` | Keep as the shared search request | Distinguish draft/live text from supplier-committed text in UI state, not by creating another query model. |
| `LookupResult` | Keep as the common result envelope | Add normalized optional inventory/location fields while preserving `characteristics` and `raw`. |
| `search_components()` | Keep as the only source adapter orchestration | Invoke it separately with source subsets: PartsBox for live changes, suppliers only for Enter. Permit injection of the cached PartsBox snapshot/client. |
| `_partsbox_part_to_result()` | Keep one PartsBox-to-result conversion | Enrich from the shared inventory snapshot with current quantities and location relationships. |
| `record_filter` | Keep as the only filter engine | Add multiselect membership, facet counts, location/project predicates, filter specifications, and deterministic sort support. |
| `engineering_units` | Keep one numeric parser | Normalize whitespace and additional observed symbols; retain field-specific comparisons because the parser is not dimension-aware. |
| `generate_facets()` | Keep one facet derivation path | Derive from the filtered pre-pagination dataset and support counts. Do not emit filters for empty/unreliable fields. |
| `PartsBoxClient` | Keep as the API adapter | Add a shared cached read service above it; do not put Streamlit decorators inside the low-level client. |
| `_net_quantities_by_storage()` | Extract and reuse | Make it a public pure helper used by Inventory and recommendation. Preserve positive-net-only semantics. |
| `ActiveBomState` | Keep as the sole Working Parts List | Store/source the authoritative source selection with the run and pass it through all sourcing mutations. |
| `SupplierLookupCache` | Keep for sourcing decisions | Do not confuse it with the PartsBox catalog cache. Supplier discovery caching should be separately keyed and short-lived if later required. |
| Session state | Keep per-browser UI state | Add explicit search event, results, filter, page, and upload-fingerprint state with namespaced keys. |
| Pagination | No current helper exists | Add one pure `paginate_records()` helper and use native `st.pagination` from pinned Streamlit 1.62. |

## Material findings

### 1. Source selection is not yet one authoritative sourcing configuration

The Search checkboxes are presented as global. Upload reads the Mouser and DigiKey checkbox values, but it does not read the PartsBox source checkbox. Instead, `run_partsbox` comes from **Update PartsBox Project**, which is a write-side configuration with different meaning.

Manual **Add to BOM** also calls `apply_replacement()`, which always instantiates Mouser and DigiKey clients and runs the default Mouser-first/DigiKey-fallback logic. It does not receive the selected sources. Retry Exact and replacement application behave the same way.

This means an unchecked supplier can still be queried during an Add or later re-sourcing action. It creates no purchasing artifact, but it violates the intended global selection and can cause unexpected API traffic.

**Required design:** introduce one small immutable source-selection value, such as `{partsbox, mouser, digikey}`, stored in session configuration and copied into `current_run`. Pass it to upload sourcing, manual add, Retry Exact, and replacement application. Keep **Update PartsBox Project** separate because it controls PartsBox writes, not PartsBox discovery.

### 2. PartsBox instance caching is ineffective across UI searches

`PartsBoxClient._parts_cache` works only while one client instance lives. Current UI calls normally create new instances. Live local filtering must never construct a client and call `part/all` for each text commit.

**Required design:** a process-wide read snapshot with a bounded TTL and manual refresh/invalidation. One cached account-wide snapshot is appropriate because every user on the future Yank PC uses the same PartsBox account. Each session filters its own copy or immutable records.

Recommended initial policy:

- fetch on the first nonempty PartsBox query or when PartsBox Inventory is entered;
- global data cache with a five-minute TTL;
- foreground load on the first request;
- explicit **Refresh PartsBox data** action on the Inventory page;
- invalidate after an AutoBOM PartsBox write that can affect the joined view;
- retain and visibly timestamp the last successful snapshot if a refresh fails.

### 3. Upgrade Streamlit, then use a minimal Enter-event adapter

The selected design is to upgrade Streamlit and use a very small Enter-event adapter around the search input.

Pinned Streamlit 1.62 `st.text_input` commits only on Enter or blur. It cannot update Python results after a typing pause. Streamlit 1.64 adds native debounced `live` commits, which should provide the PartsBox live-typing behavior without implementing custom debounce logic. The Python callback still receives the value rather than an event reason distinguishing “typing pause” from “Enter.” The official 1.62 signature is documented here: [Streamlit 1.62 `st.text_input`](https://docs.streamlit.io/1.62.0/develop/api-reference/widgets/st.text_input). Current Streamlit documentation describes debounced `live` input here: [current `st.text_input`](https://docs.streamlit.io/develop/api-reference/widgets/st.text_input).

The exact requested contract cannot safely infer Enter from ordinary reruns. Timing heuristics would be fragile and could call suppliers during typing.

**Required design:** first upgrade the pinned dependency to Streamlit 1.64.0 (or a later deliberately tested version) and use native debouncing. Then use one minimal search-input adapter whose only additional responsibility is identifying Enter and emitting:

```text
{ value: "rc0603", event: "change" }   # debounced 300-400 ms
{ value: "rc0603", event: "submit" }   # Enter key
```

The adapter is a thin UI wrapper, not a search implementation. It contains no PartsBox, Mouser, DigiKey, filtering, BOM, or purchasing code. Python continues to use `LookupQuery`, `search_components`, `record_filter`, and session state. If a future pinned Streamlit release exposes commit reason natively, remove the adapter without changing the search architecture.

The resulting operator behavior is the chosen design:

```text
Type and pause briefly -> native Streamlit live event -> filter cached PartsBox records
Press Enter           -> adapter submit event        -> query selected Mouser/DigiKey APIs
```

### 4. PartsBox stock/location relationships are implemented only inside the recommender

The tested `_net_quantities_by_storage()` correctly sums signed `stock/quantity` entries by `stock/storage-id` and removes totals at or below zero. This is suitable for inventory display, current-location filtering, and recommendation evidence.

It is not yet shared. `LookupResult.stock` remains unknown for PartsBox, Inventory does not display locations or quantities, and storage data is fetched separately.

**Required design:** extract a pure ledger summarizer and build a shared snapshot that enriches each PartsBox result with:

```text
locations: [
  {storage_id, name, quantity, space_type, project_name?}, ...
]
total_quantity: sum(current positive quantities)
development_locations: [...]
project_locations: [...]
other_locations: [...]
projects: [...]
```

Keep the original raw record. Do not collapse multiple locations into one `storage_space` field.

### 5. The current recommender can prefer project storage

For an exact part in multiple locations, the recommender chooses the location with the highest positive quantity. For similar parts, it counts all positive locations. It has no knowledge of Development versus Project storage. It can therefore recommend a production/project location merely because that location holds more stock or appears more often.

This does not satisfy the requested Inventory placement rule.

**Required design:** reuse the shared location-space classification. For normal `INV-<LOCATION>` electronic inventory placement, score Development locations first. Project locations may be shown as context but must not win merely because the identical part appears there. When no Development evidence exists, return manual selection or an explicitly lower-confidence alternative rather than silently treating project storage as general inventory.

### 6. Result rendering does not scale

Main Search creates a quantity widget and Add button for every result. Needs Review creates one Select button per candidate. Hundreds of controls increase browser payload, server widget state, rerun cost, and key-management risk.

**Recommended presentation:** a compact, selectable `st.dataframe` for the current page, followed by one selection detail panel, one quantity input, and one **Add to BOM** or **Select Replacement** action. Streamlit 1.62 supports dataframe row selection: [Streamlit 1.62 `st.dataframe`](https://docs.streamlit.io/1.62.0/develop/api-reference/data/st.dataframe).

Use cards only for the selected record's expanded details. Do not create one button or number input per row.

## Target shared architecture

```text
                         Search input event
                       change          submit
                          |                |
                          v                v
              cached PartsBox query   committed supplier query
                          |                |
                          +-------+--------+
                                  v
                      normalized LookupResult records
                                  |
                         shared text + filters
                                  |
                              stable sort
                                  |
                              pagination
                                  |
                       context-specific presentation
                                  |
                     Add/Select -> ActiveBomState
```

### Search state

Keep separate session keys for facts with different lifetimes:

```text
search_draft_text                 latest debounced input value
search_supplier_committed_text    last value submitted with Enter
search_selected_sources           authoritative source selection
search_partsbox_results           results for current draft
search_supplier_results           results for last submitted text
search_filters                    active shared filter values
search_page                       current page
search_result_signature           query/sources/filter signature
```

Do not overwrite supplier results on every character. If the draft changes after the last Enter, retain the previous supplier results only if clearly labeled **Supplier results for “old query”**; the cleaner operator behavior is to clear them and show **Press Enter to search selected suppliers**.

### Trigger behavior

#### PartsBox only

1. A debounced `change` event updates `search_draft_text`.
2. For an empty value, show no main-search results. Do not load the catalog at initial page startup.
3. From one character onward, obtain the cached snapshot and filter locally.
4. No external supplier client is constructed.
5. PartsBox occupies full result width.

One-character search is acceptable for the observed 3,450-record catalog because processing is local and only the first 20 filtered rows render. Debounce at 300-400 ms to avoid needless full-script work while an operator types quickly.

#### PartsBox plus Mouser and/or DigiKey

1. `change` updates PartsBox locally only.
2. `submit` stores the committed text and calls only the selected external supplier adapters.
3. PartsBox may recompute from the same submitted text, but no second network fetch occurs when the snapshot is warm.
4. Render two approximately equal columns:
   - left: PartsBox results;
   - right: one combined Mouser/DigiKey ranked table with a visible Source column.

A combined supplier table is preferable to nested tabs or two subnavigation systems. Operators can compare stock and price directly, and Source remains filterable. Preserve the adapter result order initially; add explicit cross-supplier ranking only when the ranking rules are documented and tested.

#### Suppliers only

1. Draft changes clear/stale the previous supplier display and show the Enter instruction.
2. No API call occurs on change, blur, filter, pagination, selection, or quantity changes.
3. Enter calls only the selected suppliers.
4. The combined supplier table uses full width.

### Upload without a Process Upload button

Use the existing `st.file_uploader`, which already supports click, drag/drop, CSV, and XLSX. Add a session-scoped import state machine:

```text
empty -> pending -> processing -> succeeded
                              -> failed
```

Compute a stable fingerprint from filename, byte length, and content hash. When the uploader produces a fingerprint different from the last attempted fingerprint, mark it pending. Perform the existing save/parse/workflow call once during normal script execution, then store the fingerprint and outcome. Do not perform heavy work inside a widget callback.

Other widget reruns must see `succeeded` or `failed` and must not process the file again. A failed import should show an explicit **Retry import** action or require reselecting the file; it must not enter a rerun loop. Provide a compact Upload control next to the Search heading rather than a permanent one-third-width column.

Pass the same authoritative source selection to `run_bom_workflow`. Keep **Update PartsBox Project** as an independent write option in Configuration. Upload, like Search, must pass `run_digikey_mylist=False` and must never call purchasing regeneration.

## One reusable filter and facet system

### Pipeline

Every context should use this order:

```text
base result dataset
    -> text normalization/search
    -> active filters
    -> stable sort
    -> facet/count derivation as defined below
    -> pagination
    -> rendering
```

For faceted navigation, each facet's available values should be calculated from records after text search and all *other* active filters, excluding that facet's own selection. This prevents a selected Manufacturer from collapsing its own option list while still allowing Category or Location options to narrow appropriately. Pagination always comes last.

### Shared filter specification

Define filter metadata once rather than hardcoding widget lists in each page:

```text
field name
label
kind: categorical | multi-categorical | stock | numeric-range | text-membership
contexts: main-search | inventory | replacement
source applicability
reliability predicate
```

The UI renderer consumes the specification and the dynamic facets, inside a collapsed **Filters** expander. Context controls availability; `record_filter` controls semantics.

### Reliable filters now

| Filter | Main Search | PartsBox Inventory | Needs Review | Evidence/constraint |
|---|---:|---:|---:|---|
| Manufacturer | Yes | Yes | Yes | Present on normalized records when supplied. |
| Source | Yes | No | Yes | Meaningful only across mixed-source results. |
| Stock | Suppliers now; PartsBox after enrichment | Yes after enrichment | Yes | CSV confirms numeric total stock and exact agreement with summed current locations. Unknown must remain distinct from zero. |
| Lifecycle | When populated | No current PartsBox evidence | When populated | Dynamic only. |
| Category/Family | Supplier data when populated | Not currently reliable | When populated | Observed PartsBox data lacks category. |
| Package/Mounting | Only when populated | Not currently reliable | When populated | Observed PartsBox data lacks package. |
| Value/tolerance/voltage/current/power | Only when populated and parseable | Only when populated | When populated | Never infer from description in this pass. |
| Storage Space | PartsBox results after enrichment | Yes | PartsBox replacement only | Derived per location; 290 exported parts have multiple locations. |
| Location | PartsBox results after enrichment | Yes | PartsBox replacement only | Searchable multiselect across positive balances; 821 names occur in the export. |
| Project | PartsBox results after enrichment | Yes | PartsBox replacement only | Derived from project/storage convention. |

Do not show empty Category, Package, or parametric groups merely because the filter specification knows their names.

For the current PartsBox data, the first reliable Inventory filters should be MPN/description text, stock availability/quantity, Storage Space, Location, and Project. Manufacturer remains reliable through the API-normalized record but is absent from this CSV export. Category, Package, Mounting, Value, Tolerance, Voltage, Current, and Power should appear only when confirmed structured values exist; description text alone is not enough to label them source-confirmed.

### Engineering values

`parse_engineering_value()` is a suitable shared base, but it is deliberately dimension-unaware. The filter layer must compare only a voltage field with voltage bounds, resistance with resistance, and so on. Enhance and test normalization for whitespace, micro symbols, and observed unit spellings before relying on advanced numeric filters. “Around 10k” should be translated by the UI into an explicit min/max tolerance band rather than adding fuzzy dimensional logic to every caller.

## Pagination design

Use **20 results per page**. A compact selectable dataframe at 20 rows remains readable in full-width and split layouts while reducing 3,450 inventory records to approximately 173 pages. Fifteen is unnecessarily restrictive once per-row controls are removed.

Add a pure helper that accepts already filtered/sorted records and returns:

```text
items
total_items
page
page_size
total_pages
start_index
end_index
```

Use Streamlit 1.62's native `st.pagination` widget, with namespaced keys for Main Search PartsBox, Main Search Suppliers, Inventory, and each active replacement lookup. Keep page state in the current browser session.

Reset the relevant page to 1 when any result-defining input changes:

- search text;
- committed supplier query;
- source selection;
- filter selection or range;
- sort;
- PartsBox snapshot generation/refresh;
- newly uploaded file only for Working Parts List pagination, not component search pagination.

Changing quantity or selecting a row must not reset the page. Adding a search result to the Working Parts List may keep the search page so multiple nearby parts can be added. Upload should not clear search text/results unless the product decision explicitly requires it.

Use a deterministic signature of normalized query, selected sources, filters, sort, and snapshot generation. When it differs from the stored signature, set page to 1 before slicing. Clamp page to the last valid page when the total shrinks.

## PartsBox Inventory design

### Lazy loading

Normal AutoBOM startup must not fetch the catalog. On navigation to **PartsBox Inventory**, call the shared snapshot loader once. The resulting page immediately shows **all parts accessible through the live PartsBox API**, not merely the 3,330 rows in the supplied CSV, through page 1, with an empty search meaning “all inventory.” The displayed total must be calculated from that live snapshot.

The main Search uses the same snapshot but loads it only when PartsBox is selected and the operator enters a nonempty query. Inventory and Main Search therefore share data without sharing page state.

### Complete joined snapshot

Build the snapshot from:

- `part/all`;
- `storage/all`;
- `project/all` when required to validate the same-name project convention;
- configured classification rules.

The snapshot should map storage IDs once, net each part ledger once, and construct normalized records once per cache generation. Searching, filtering, facets, pagination, Inventory display, and recommendations then operate locally.

### Storage-space classification

Represent a part as having zero or more location memberships. Classify each location independently:

```text
Development
Project
Mechanical
Other
```

Classification evidence should come from:

1. explicit configurable tag/rule mapping;
2. the existing `production` tag plus same-name project/storage relationship for Project;
3. configured Mechanical tags/rules when introduced;
4. configured Development patterns/tags;
5. Other when no rule is reliable.

Do not hardcode the full list of storage names. Put rules in a small versioned configuration file and preserve unclassified names as Other. Adding Mechanical must require a rule/config update, not changes to search or filtering code.

Expose:

- **Storage Space:** multiselect of classifications present in the dataset;
- **Location:** searchable multiselect of current positive-balance locations;
- **Project:** searchable multiselect derived from validated project storage relationships.

### Inventory table

Use a full-width selectable dataframe with these compact columns where available:

```text
MPN | Manufacturer | Description | Total Qty | Development | Projects | Other
```

Keep location summaries short, for example `A12 (250); A14 (20)`. On row selection, show an expander/detail panel with every positive location grouped by space:

```text
Development
A12 — 250

Projects
Army Battery — 40
DAB Prototype — 12
```

Large descriptions should be truncated in the table and shown in full in the selected detail. Quantities must come only from the shared signed-ledger summarizer. Historical zero/negative locations must never appear as current locations or facets.

## Needs Review

Keep `build_query_from_bom_row()`, `search_components()`, and `apply_replacement()`. Replace only the UI orchestration and pass the global source selection into the re-sourcing seam.

Needs Review should reuse:

- the same event behavior when multiple sources are enabled;
- the same filter specification, limited to relevant fields;
- the same 20-row paginator;
- the same selectable dataframe and selected-record detail;
- the same cached PartsBox snapshot;
- the same normalized location relationships.

Each row's replacement state must be namespaced by stable `row_id`. Closing a review row or completing a replacement should clean only that row's query, result, filter, and page keys.

## Purchasing side-effect boundary

The following interactions must remain read-only with respect to purchasing artifacts:

- typing or submitting Search;
- PartsBox live filtering;
- supplier discovery queries;
- uploading and parsing;
- filtering and facet changes;
- pagination and sorting;
- row selection and detail expansion;
- adding a candidate to the Working Parts List;
- inventory browsing and recommendation.

Mouser's normal path remains export generation and manual upload. DigiKey MyList creation remains reachable only through explicit Purchasing regeneration. Tests should patch both purchasing clients and assert zero calls across every UI interaction above.

## Performance and state risks

| Risk | Current exposure | Required control |
|---|---|---|
| PartsBox API called per search | High with new client instances | One TTL snapshot shared across sessions; local filtering. |
| Supplier API called while typing | Would be high if the current unified call were attached to live input | Separate `change` and `submit` events; suppliers consume only submit. |
| Full-app reruns while typing | Expensive on the continuous page | Debounce 300-400 ms; isolate search in a fragment if compatible with canonical updates; otherwise keep render work bounded. |
| Thousands of widgets | Current per-result controls scale poorly | Paginate before render; selectable dataframe plus one action panel. |
| Facet recomputation | Acceptable at 3,450 records, but repeated work adds up | Normalize snapshot once; compute facets from in-memory records; cache by result/filter signature only if profiling warrants it. |
| Large descriptions | Bloats tables and websocket traffic | Compact/truncated table column; full text only for selected item. |
| Page state drift | No current model | Namespaced page keys, result signatures, reset/clamp rules. |
| Upload repeats on rerun | Guaranteed if button is simply removed | Content fingerprint plus explicit import state machine. |
| Cross-session mutation | Cached objects may be global | Cache immutable/copy-on-read data; keep queries, pages, selections, and Working Parts Lists in session state. |
| Multiple Yank-PC users refresh together | Cache stampede/API bursts | Use Streamlit's shared cache synchronization or a process lock around refresh; one process remains the deployment recommendation. |
| Incorrect PartsBox quantity | Inventory currently avoids quantity entirely | Reuse tested signed ledger netting; ignore malformed entries and nonpositive totals; add aggregation fixtures. |
| Stale catalog | TTL data can lag external PartsBox changes | Timestamp, five-minute TTL, explicit refresh, invalidation after known writes. |
| Widget state loss | Conditional layouts can remove keys | Store durable UI state in explicit non-widget session keys and render stable keyed widgets. |

Streamlit documents global and session cache scopes and TTL behavior in [`st.cache_data`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data). Its fragment model can limit widget-triggered reruns to one section: [Streamlit fragments](https://docs.streamlit.io/develop/concepts/architecture/fragments). Fragment use should be adopted only after AppTests prove Add-to-BOM mutations and content below the fragment refresh correctly.

## Files to modify

### Existing files

- `app.py`
  - compact Search/Upload layout;
  - input event handling;
  - automatic upload state machine;
  - source-specific result layout;
  - shared filter renderer;
  - pagination state and selectable tables;
  - lazy Inventory load and detail view.
- `src/component_lookup.py`
  - accept/enrich from the shared PartsBox snapshot;
  - expand optional normalized location fields;
  - retain source-specific raw data.
- `src/record_filter.py`
  - multiselect/membership filters;
  - facet counts and exclusion of the facet's own active filter;
  - deterministic shared filter behavior.
- `src/engineering_units.py`
  - tested normalization for observed spacing/symbol variants.
- `src/partsbox_client.py`
  - remain the raw API adapter; expose only any missing read calls needed by the snapshot.
- `src/inventory_location_recommender.py`
  - consume shared ledger/location classification;
  - prefer Development evidence and exclude Project-only evidence from ordinary inventory recommendations.
- `src/review_actions.py`
  - accept authoritative selected suppliers for retry and replacement re-sourcing.
- `src/workflow_runner.py`
  - accept the complete source selection separately from PartsBox project-write configuration.
- `src/active_bom_state.py`
  - no structural rewrite; only adjust if a run-level source configuration needs an explicit access seam.
- relevant tests under `tests/`.

### Genuinely necessary new files

- `src/partsbox_inventory.py`
  - pure snapshot normalization;
  - signed-ledger aggregation;
  - storage/project join;
  - storage-space classification;
  - immutable normalized inventory records.
- `src/pagination.py`
  - pure page calculation/slicing and clamp logic, shared by all contexts.
- `src/search_events.py` or a minimal Streamlit component package
  - wraps the upgraded Streamlit live input and identifies Enter;
  - emits debounced `change` and Enter `submit` events only;
  - contains no search, filtering, API, BOM, or purchasing logic.
- `config/storage_space_rules.json`
  - tags/patterns and precedence for Development, Project, Mechanical, and Other classification.

A separate Main Search engine, Inventory filter engine, replacement filter engine, or PartsBox-specific paginator would be an architecture error.

## Test plan

### Pure filtering and pagination tests

- text search precedes filtering;
- multiselect uses OR within one facet and AND across facets;
- nested location membership works for space, location, and project;
- facet values/counts derive before pagination;
- a facet excludes its own selection while respecting other filters;
- missing fields do not create controls or false matches;
- range filters compare only the intended field and exclude unparseable values;
- 0, 1, 20, 21, and 3,450 records paginate correctly;
- page clamps after result shrink;
- stable sort prevents records moving between pages.

### PartsBox snapshot and storage tests

- one snapshot load calls each required PartsBox read once;
- warm cache is reused across searches and browser sessions;
- TTL/explicit refresh produces a new generation;
- signed transactions net per storage correctly;
- zero and negative balances disappear;
- one part retains multiple positive locations;
- all 3,242 located rows in the supplied export can be represented so location quantities sum to exported Stock;
- duplicate Part/MPN display values remain distinct through stable `part/id`;
- `production` plus project-name convention classifies Project;
- configured general storage classifies Development;
- Mechanical can be added through config only;
- unknown storage classifies Other;
- total quantity equals the sum of positive current balances;
- recommendation prefers Development over a larger Project balance;
- Project-only evidence does not become a high-confidence ordinary inventory recommendation.

### AppTests for live search and Enter boundary

- typing `r`, `rc`, `rc0`, `rc0603` updates PartsBox results after debounce;
- those changes make zero Mouser/DigiKey calls;
- Enter makes one call to each selected supplier and no unselected supplier;
- filter, page, row selection, quantity, and unrelated reruns make no supplier calls;
- PartsBox-only uses full width;
- mixed sources render PartsBox and combined suppliers separately;
- suppliers-only uses full width;
- source/query/filter changes reset only the relevant page;
- selection and quantity do not reset the page;
- 20 or fewer result rows are rendered at once;
- main Search does not load the full PartsBox catalog on blank startup.

### Upload AppTests

- CSV and XLSX selection automatically process once;
- drag/drop and click produce the same uploader object path;
- unrelated reruns do not reprocess or merge duplicate rows;
- a second distinct file merges into the same `ActiveBomState`;
- a failed upload does not loop and can be retried deliberately;
- selected Mouser/DigiKey sources are honored;
- PartsBox discovery selection is distinct from **Update PartsBox Project** writes;
- upload creates no cart or MyList.

### Inventory AppTests

- AutoBOM startup does not call `part/all`, `storage/all`, or `project/all`;
- first entry to Inventory loads the complete snapshot and shows page 1 without a search click;
- returning within TTL reuses the snapshot;
- search and filters operate on the entire dataset before pagination;
- only current-page rows render;
- selecting a part shows every positive location grouped by space;
- zero-balance historical locations never display or facet;
- refresh invalidates and reloads once.

### Canonical-state and side-effect tests

- Search and Upload continue to mutate the same `ActiveBomState`;
- replacement selection writes through `apply_replacement()`;
- the selected source configuration is honored by manual add, upload, Retry Exact, and replacement application;
- Search, Upload, filters, pagination, Inventory, and recommendation produce zero Mouser cart and DigiKey MyList calls;
- only explicit Purchasing regeneration can create a DigiKey MyList.

## Implementation sequence

1. Add pure pagination and PartsBox inventory snapshot modules with unit tests.
2. Extract ledger netting and add storage-space classification tests.
3. Make source selection authoritative through workflow and review seams.
4. Extend `record_filter` and build one filter specification/renderer.
5. Upgrade Streamlit to 1.64.0, run the existing suite, then add the minimal Enter-event adapter and prove change-versus-submit behavior in isolation.
6. Replace Main Search rendering with paginated selectable dataframes and the three source layouts.
7. Add upload fingerprint/state handling and remove Process Upload.
8. Convert PartsBox Inventory to lazy complete-snapshot browsing with shared filters and pagination.
9. Convert Needs Review results to the same shared presentation/filter/pagination components.
10. Run the full suite plus multi-session operator acceptance tests and purchasing-side-effect assertions.

## Final verdict

**READY WITH PRECONDITIONS**

The current code has one lookup model, one generic filter engine, one PartsBox client, one canonical BOM state, and one sourcing decision seam. Those are the right foundations and should remain.

Implementation should begin with the four shared preconditions: a cached/enriched **complete live** PartsBox snapshot, an upgrade to Streamlit 1.64.0 with regression verification, a minimal Enter-event boundary, and an authoritative source-selection object used by every intake and re-sourcing path. The supplied spreadsheet remains test evidence only and must not cap or define Inventory. Once those preconditions are established, compact rendering, pagination, advanced filters, automatic upload, Inventory browsing, and Needs Review can be implemented as contexts over the same machinery without creating parallel systems.
