# AutoBOM Phase 4 Implementation Report

**Scope:** PartsBox Inventory workspace, expansion of the shared search/filter system toward parametric component filtering, Purchasing Handoff workspace — all built as extensions of the Phase 3 architecture (`ActiveBomState`, `component_lookup`, `record_filter`, `sourcing_engine`, `PartsBoxClient`/`MouserClient`/`DigiKeyClient`, `workflow_runner`). None of those systems was rewritten or duplicated.
**Explicitly not built:** PartsBox write operations (unverified API support), saved-filter automation (unverified), Mouser share automation, DigiKey durable token backend, full DigiKey-style parametric ontology, final deployment.

## 1. Files changed

**New:**
- `src/engineering_units.py` — shared numeric/SI-prefix/unit parsing for range filters
- `tests/test_engineering_units.py`, `tests/test_purchasing_state.py`, `tests/test_digikey_list_export.py`

**Modified:**
- `src/record_filter.py` — range filters, `generate_facets()`
- `src/component_lookup.py` — PartsBox browse-all, generic characteristics extraction, `stock_sufficient`, flattened `characteristics` in `to_dict()`
- `src/sourcing_engine.py` — `SupplierResult.category` field
- `src/mouser_client.py`, `src/digikey_client.py` — defensive `category` extraction
- `src/digikey_list_export.py` — bug fix (see §10)
- `src/workflow_runner.py` — `derive_purchasing_status()`, `build_purchasing_summary()`, `regenerate_purchasing()`
- `app.py` — PartsBox Inventory page, Purchasing Handoff page, dynamic facet filters on Component Search, disabled-while-stale downloads
- `tests/test_component_lookup.py`, `tests/test_record_filter.py`, `tests/test_app_smoke.py` — new coverage

## 2. PartsBox Inventory design

`render_partsbox_inventory_page()` in `app.py`:
- Search box (MPN/keywords) + manufacturer filter, "Search / Browse All" button building one `LookupQuery(sources={"partsbox"})` and calling `component_lookup.search_components()` — the identical function Component Search and Find Replacement use.
- Dynamic facet filters via the same `render_dynamic_facet_filters()` helper Component Search uses (see §5).
- A results table (`INVENTORY_DISPLAY_COLUMNS`) via the same `render_lookup_results_table()` Component Search uses.
- A Storage Locations section calling the pre-existing `PartsBoxClient.list_storage_locations()`, showing name, tags, and whether the `production` tag is present — the same detection logic `partsbox_project_builder._storage_has_tag()` already implements, just surfaced for browsing.
- **Read-only.** No write action is offered. §3 explains why.

## 3. Shared inventory/search reuse

No second PartsBox client, search engine, filter system, or part model was created:
- Browsing (empty query) and searching (MPN/manufacturer/keywords) both go through `component_lookup._search_partsbox()` — the guard that previously required a non-empty query was removed, so an empty query now means "match everything" through the *same* function, rather than adding a separate listing path.
- Filtering (categorical facets, range facets, and the existing manufacturer/stock logic) goes through `record_filter`.
- Storage-location tag detection reuses the exact convention `partsbox_project_builder.py` already implements for the production-tag check.

## 4. Parametric filter implementation

`record_filter.apply_filters()` now recognizes three kinds of filter value per field:
1. A plain string → case-insensitive exact match (unchanged from Phase 3).
2. The `stock` field with `"In Stock"`/`"Out of Stock"`/`"Unknown"` (unchanged from Phase 3).
3. **New:** a dict `{"min": ..., "max": ...}` → the record's raw value for that field is parsed via `engineering_units.parse_engineering_value()` and must fall within the bounds (either bound may be `None` for unbounded).

`engineering_units.py` is a small, deliberately non-exhaustive parser: it strips a leading `±`/`+/-`, a known unit suffix (`V`, `A`, `W`, `F`, `H`, `Hz`, `ohm`, `%`, `s`), and a trailing SI prefix (p/n/u or µ/m/k/M/G), returning a plain float in base units. It does not know what a volt *is* — callers are responsible for only comparing values that are the same kind of quantity. This is the one shared numeric-parsing layer; no page implements its own.

## 5. Facet-generation design

`record_filter.generate_facets(records, candidate_fields)` returns `{field: sorted distinct values}` for only the fields in `candidate_fields` that have at least one non-empty value across the given records — a field with no real data never produces an empty/useless filter.

`app.py`'s `render_dynamic_facet_filters(results, key_prefix)` is the one shared UI implementation built on top of `generate_facets()`, used by both Component Search and PartsBox Inventory:
- `CATEGORICAL_FACET_FIELDS = ["category", "package", "mounting", "dielectric", "lifecycle_status"]` → an exact-match selectbox per facet that has data.
- `RANGE_FACET_FIELDS = ["voltage", "current", "power", "tolerance", "resistance", "capacitance", "inductance", "unit_price"]` → min/max text inputs per facet that has data, parsed through `engineering_units` before being placed in the filters dict as a range.
- `stock` is deliberately excluded from both lists — it keeps its existing dedicated In Stock/Out of Stock/Unknown selector rather than gaining a second, redundant numeric range control.

## 6. Range/unit handling

Handled entirely by `engineering_units.parse_engineering_value()` (§4) plus `value_in_range()`. A value that can't be parsed (e.g. a package code like "SOIC-8", or truly missing data) never matches a bounded range — it is excluded, not treated as zero or as a wildcard match. No dimensional analysis, no unit conversion between different units of the same quantity (e.g. no mixing "25V" against a filter typed in mV) — deliberately out of scope per the instructions ("do not overbuild a complete electronics ontology"); the architecture (one shared parsing function, one shared range-filter mechanism) is what's reusable, not an exhaustive unit system.

**Where real parametric data actually reaches this machinery today:** PartsBox part fields not already mapped to a named `LookupResult` field (e.g. a hypothetical `part/capacitance`, `part/voltage`) are captured generically into `characteristics` and flattened onto the top level of the result dict — so if PartsBox's live API returns such fields, they become filterable/faceted immediately, with no code change. Mouser/DigiKey's `SupplierResult` gained a defensively-populated `category` field only (§9) — deeper parametric extraction from their raw responses was deliberately not attempted, since the exact field names/shapes (`ProductAttributes`, `Parameters`, etc.) are unverified against a live call, and guessing risks either silently returning nothing (acceptable) or crashing on an unexpected shape (not acceptable). This matches the instructions exactly: the range/facet architecture is ready and tested; population from Mouser/DigiKey awaits live API verification.

## 7. Purchasing Handoff architecture

`workflow_runner.py` gained three functions, all reading from `response["_active_bom_state"]` (never a second BOM representation):

- **`derive_purchasing_status(response)`** — one of `Not Available` / `Needs Review` / `Stale — BOM Changed` / `Generation Failed` / `Not Yet Generated` / `Ready for Handoff`, checked in that priority order. This describes purchasing *artifacts*, kept as a concept distinct from a BOM row's `result_status` (component sourcing status) — the same Source/Status separation principle from the Results Workspace, applied to purchasing.
- **`build_purchasing_summary(response)`** — per-supplier item/quantity counts read from the existing, unmodified `mouser_cart_client.build_mouser_cart_items()` / `digikey_mylists_client.build_digikey_mylists_parts()` selection functions (the same functions actual cart/MyList creation uses), plus CartKey/list ID/share-ID and the current `needs_review_count`. No sourcing/selection decision is recalculated here.
- **`regenerate_purchasing(response, ...)`** — see §10.

`app.py`'s `render_purchasing_page()` renders status, per-supplier summary cards, a `Regenerate Purchasing` button (disabled while any row needs review — enforcing the intended "resolve reviews, then regenerate" flow directly rather than just warning about it), and the existing downloads section.

## 8. Mouser workflow

Unchanged and preserved exactly: `mouser_cart_client.create_mouser_cart_from_bom()` and `build_mouser_cart_items()` were not modified. `regenerate_purchasing()` calls the former the same way `run_bom_workflow()` already does, gated by the same `MOUSER_CART_ENABLED` env var, and passes the result through the existing `_build_mouser_purchasing()` helper (unchanged) so CartKey extraction is identical either way. Manual Model B sharing is unchanged — the Purchasing page states the manual-share instruction directly (*"complete the Share action in Mouser directly and hand the resulting Access ID to purchasing. No need to paste it back into AutoBOM"*) rather than adding any paste-back UI.

## 9. DigiKey workflow

Unchanged and preserved exactly: `digikey_mylists_client.create_digikey_mylist_from_bom()` / `build_digikey_mylists_parts()` were not modified. `regenerate_purchasing()` calls the former the same way a normal run does, gated by `DIGIKEY_MYLISTS_ENABLED`. The Purchasing page shows List ID and the `share_id` field, which — as in Phase 1–3 — remains `None`, since no confirmed DigiKey share-identifier field exists in this integration; the page states this explicitly (*"Not confirmed by current API"*) rather than fabricating a value. `SupplierResult.category` (§6) is unrelated to purchasing and does not touch the MyLists path.

## 10. Purchasing staleness/regeneration design

Building on Phase 3's `stale_after_mutation` flag (set by `refresh_response_snapshot()` after Retry/Replacement):

- `regenerate_purchasing(response, run_mouser_cart=True, run_digikey_mylist=True)` is called **only** from the "Regenerate Purchasing" button handler — never from any code path that runs on every Streamlit script execution. `test_rerun_alone_never_triggers_regeneration` proves a plain rerun never calls it.
- It re-exports `cleaned_csv`, `sourcing_report`, `digikey_list_csv`, and (when a project name is set) `partsbox_import_csv` from the **current** `active_bom_state.dataframe` using the existing, unmodified exporters (`export_clean_bom`, `export_sourcing_report`, `export_digikey_list`, `export_partsbox_import_csv`), overwriting the same output paths. It then calls the gated Mouser/DigiKey functions (§8/§9), rebuilds `response["purchasing"]` via the existing `_build_mouser_purchasing()`/`_build_digikey_purchasing()` helpers, calls `refresh_response_snapshot()` for `bom_rows`/`review_items`/`results_summary`, and clears `stale_after_mutation`.
- **Known, stated limitation:** the multi-sheet `cleaned_workbook` (XLSX with Clean_BOM/Review_Items/Column_Mapping/Warnings sheets) is **not** regenerated. `export_clean_bom_workbook()` needs the original run's `column_mapping`/`warnings` DataFrames, which are not retained anywhere in `response` after the run completes — reconstructing them would require either persisting two more DataFrames through the whole response lifecycle (a larger contract change, out of scope for this pass) or fabricating placeholder sheets (rejected — would silently misrepresent the original mapping/warnings). The CSV/summary regeneration above was judged sufficient for the purchasing/downloads use case this phase targets; the workbook gap is listed as a remaining limitation, not hidden.
- Errors during regeneration (a failed export, a failed vendor call) are collected into `response["purchasing_regeneration_errors"]` and surfaced as `Generation Failed` status plus `st.error()` messages — nothing raises out of the button handler.
- **Bug found and fixed along the way:** `digikey_list_export.export_digikey_list()` crashed with `AttributeError: 'str' object has no attribute 'astype'` when `clean_bom` has no `selected_supplier` column yet (a BOM that hasn't been through sourcing). `clean_bom.get("selected_supplier", "")` returns the plain default string `""` in that case, not a Series, and `.astype(str)` on a string fails. This was never exercised before because normal runs only call this export *after* sourcing adds the column; `regenerate_purchasing()` can legitimately be called against an un-sourced BOM (e.g. `run_sourcing=False` runs). Fixed with an explicit column-existence check; 3 new regression tests in `tests/test_digikey_list_export.py`.

## 11. Download regeneration behavior

`show_download()`/`render_downloads()` now accept/pass a `disabled` flag, set to `current_run["stale_after_mutation"]`. While stale, every download button on the Run BOM and Purchasing pages is **disabled** (not just accompanied by a warning, matching the explicit instruction), with a warning explaining why and pointing to the Purchasing page's Regenerate button. Once `regenerate_purchasing()` runs, `stale_after_mutation` clears and downloads (now pointing at the freshly re-exported files) re-enable automatically on the next render.

## 12. Navigation/UI changes

Sidebar now has four entries: `Run BOM`, `Component Search`, `PartsBox Inventory`, `Purchasing` (was two). No additional nesting — each is a single top-level page, matching "do not over-nest the UI." Results/Needs Review remain part of the Run BOM page's flow (unchanged from Phase 3), as instructed.

## 13. Tests added

60 new/changed tests:
- `test_engineering_units.py` (15) — plain numbers, unit suffixes, SI prefixes, tolerance `%`/`±`, negative numbers, non-numeric text, range bound checks including the "unknown value never matches a bounded range" case.
- `test_record_filter.py` (+8) — range filter bounds, unbounded sides, unparseable-value exclusion, range+categorical combination, facet generation (only-real-data, sorted/deduplicated, empty-input).
- `test_component_lookup.py` (+14) — PartsBox browse-all (empty query returns everything, still respects manufacturer filter), generic characteristics extraction (unrecognized fields captured and flattened; known fields not duplicated), `stock_sufficient` in all four states (sufficient/short/unknown-stock/no-requirement), Mouser `category` extraction.
- `test_digikey_list_export.py` (3, new) — the bug fix in §10.
- `test_purchasing_state.py` (16, new) — `derive_purchasing_status()`'s six states in priority order, `build_purchasing_summary()` counting only sourced rows and reflecting a replacement resolution, `regenerate_purchasing()`'s disabled/enabled vendor-call gating (mocked, asserted called exactly once), failure handling, CSV re-export, and a full replacement-then-regenerate integration test.
- `test_app_smoke.py` (+11) — PartsBox Inventory page load, shared-lookup reuse (asserting the exact `LookupQuery.sources` passed), shared-filter reuse, absence of any write-action button, shared storage-location client reuse; Component Search facet widgets appearing when data is present; Purchasing page load, regenerate-button disabled/enabled states, single-call regeneration, and rerun-alone-never-regenerates.

A **Streamlit `AppTest` mocking gotcha was found and fixed** while writing the new smoke tests: `AppTest` never registers `app.py` under `sys.modules["app"]` (confirmed directly: `'app' in sys.modules` is `False` after `at.run()`), so `patch("app.search_components")` etc. silently patches a disconnected phantom module imported as a side effect of `unittest.mock.patch`'s string resolution, not anything `AppTest` actually executes — the mock is simply never hit, and the original code runs for real. All affected tests now patch at the *source* module instead (`component_lookup.search_components`, `partsbox_client.PartsBoxClient`, `workflow_runner.regenerate_purchasing`), which works because those callables are looked up from their defining module's namespace at call time (the same mechanism that already made `patch("review_actions.MouserClient")` work correctly in Phase 3). Verified directly before fixing all the tests, not just assumed.

## 14. Full test results

```
python -m unittest discover -s tests -v
Ran 216 tests in 16.935s
OK
```
(156 at the start of this phase → 216; all prior tests pass unmodified.)
```
python -m py_compile app.py src/*.py tests/*.py
```
passes clean.

## 15. External API assumptions still unverified

- **PartsBox:** part schema beyond `part/id`/`part/mpn`/`part/name`/`part/manufacturer` (already relied on elsewhere in the app) — `part/description`, `part/category`, `part/package` remain best-effort field-name guesses, clearly labeled "Inferred" in the Inventory page. No stock/quantity field exists anywhere in this integration. Saved-filter creation support and any storage-tag-update or stock-manipulation write operation remain unconfirmed — none was implemented or invented. `Documentation/partsbox api rules.pdf` (73 MB) still could not be parsed in this environment; no PDF text-extraction library is installed and no live API access is available.
- **Mouser/DigiKey:** the defensively-added `category` field's raw source key (`"Category"`) and shape are guesses based on plausible API conventions, not confirmed against a live response — extraction degrades to `""` if absent or shaped unexpectedly, never fabricated. Mouser CartKey envelope, DigiKey MyLists share identifier, and DigiKey `Category`/parametric `Parameters` fields remain unverified, unchanged from prior phases.

## 16. Remaining deployment blockers

Unchanged from prior phases, none resolved or newly introduced by this pass:
- Durable DigiKey refresh-token persistence (`Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md`).
- Live verification of DigiKey share identifier, Mouser CartKey response shape, Mouser private/share API, PartsBox saved-filter API, PartsBox live stock/tag schema.
- `runs/` retention/cleanup policy.
- Raw vendor-result retention/security review for `run_summary.json`.
- **New, scoped to this phase:** the `cleaned_workbook` regeneration gap (§10) — a teammate who downloads the multi-sheet XLSX after a Needs Review mutation and subsequent Regenerate still gets the *original* run's workbook, not a refreshed one (the CSV/summary downloads *do* refresh correctly). Worth resolving before this specific artifact is relied on post-replacement.

## 17. Is the application ready for final deployment-hardening work?

**Functionally, yes** — the locked-scope feature set (shared component search with parametric filtering, PartsBox Inventory, Results Workspace, Needs Review with correctly re-sourced replacements, Purchasing Handoff with explicit regeneration) is now implemented end-to-end and covered by 216 passing tests, including real `AppTest` execution of every page and the core interaction flows.

**Not yet ready to skip straight to deployment**, for reasons that are all pre-existing/external, not new gaps from this phase: durable DigiKey token persistence is still unresolved, several vendor field shapes remain unverified against live APIs (meaning some displayed values — Mouser CartKey, DigiKey share ID, PartsBox description/category, Mouser/DigiKey category — may need adjustment once verified), and the workbook-regeneration gap in §10/§16 should be closed or explicitly accepted before a teammate relies on it. None of these require architecture changes; they are verification and small follow-up items on top of the architecture now in place.
