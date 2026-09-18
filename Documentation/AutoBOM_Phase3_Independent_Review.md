# AutoBOM Phase 3 Independent Review

**Date:** 2026-09-18  
**Scope:** Current Phase 3 repository. The implementation report and durable-token strategy were read as claims/context; the repository and tests were used to verify behavior. No Phase 4 work or production changes were made.  
**Evidence labels:** **Confirmed** = code inspection or local check; **Inferred** = effect expected from confirmed code; **External** = vendor API behavior still requiring verification.

## 1. Executive Verdict

**NO-GO for the next implementation phase until the replacement and state-consistency defects below are fixed.** Phase 3 added a useful single `ActiveBomState`, persistent session rendering, and shared lookup/filter entry points. However, selecting a replacement currently declares the discovery supplier to be the purchasing supplier without running the existing sourcing decision. A candidate with stock below required quantity can become `Ready`, and purchasing quantity may be empty or stale. PartsBox selection can leave a previous external supplier selected. These are purchasing-correctness defects, not merely unfinished UI polish.

The 138 reported tests pass, but the replacement tests seed a pre-existing `supplier_order_qty` and assert that cart/MyList builders accept manually stamped supplier fields. They do not prove that the normal sourcing decision ran or that required quantity is covered.

## 2. Test Results

- `python -m unittest discover -s tests -v`: **138 passed**. Streamlit emitted bare-mode context warnings during AppTest; tests still passed.
- `python -m compileall -q app.py src tests`: **passed**.
- Read-only focused checks confirmed: a DigiKey replacement with stock 1 and required quantity 10 is marked `sourced_digikey`/`Ready` with an empty order quantity; a PartsBox replacement of a row previously sourced from Mouser remains sourced from Mouser; an `Error` row is included in `review_items()` but omitted from `summary_counts()["needs_review"]`.
- No live vendor API calls were made. Existing UI tests inject lookup candidates; they do not validate real supplier responses or end-to-end re-sourcing.

## 3. Streamlit Session-State Review

**Confirmed:** `app.py:56-68,88-143` stores one `current_run` per browser session and renders messages, downloads, and Results on each rerun. A new run replaces `current_run` and clears the selected review row. Navigation uses Streamlit's sidebar radio and does not delete the active run. AppTest covers page load, navigation, and a replacement click.

**Medium:** `lookup_results` and `replacement_results_<row_id>` are stored in session state, but starting a new run clears only `selected_review_row_id` (`app.py:130-134`). Results from a prior run can reappear if a later run produces a matching `row_id` key or if a previous search is revisited. Run IDs make accidental row-key reuse unlikely, but general Component Search results remain from the previous run regardless of the new run. Clear result caches and review widget state when the run changes.

**Medium:** Results filters use fixed widget keys (`app.py:201-219`). A selected value can persist into a new run even if absent from the new options, causing confusing or invalid filter state. Reset run-scoped filters on a new run and test the transition. Per-session state does not intentionally expose another browser session's run; server-side run artifacts still need their separate retention/access policy.

## 4. Canonical BOM-State Review

**Confirmed:** `ActiveBomState` wraps one DataFrame (`src/active_bom_state.py:102-123`); `rows()`, `review_items()`, and `get_row()` derive from it, and `update_row()` changes it by stable run-prefixed index (`:125-203`). Results and Needs Review render from this object, so UI views are not independent mutable BOMs.

**High:** `current_run` also retains snapshots created once at workflow completion: `bom_rows`, `review_items`, `results_summary`, `summary`, `purchasing`, and exported files (`src/workflow_runner.py:475-518`). `apply_replacement()` and Retry mutate only `ActiveBomState`; those snapshots and existing downloads do not update. The UI's five Results metrics derive fresh from state, but old summary messages, downloadable BOM/report, and purchasing metadata can disagree with the displayed row. Define whether post-selection exports/purchasing are stale or regenerate them from the canonical DataFrame before handoff. Do not treat the copies as current state.

## 5. Results Workspace Review

**Confirmed:** `app.py:182-253` renders active-state metrics, a table, and All Results/Needs Review tabs. Text search covers MPN, manufacturer, description, supplier part number, and designators. Source, Status, Manufacturer, and Stock widgets feed the shared `search_and_filter()`. Options come from current rows.

**Medium:** Results rows generally have `mouser_stock`/`digikey_stock`, not a unified `stock` field. The Stock widget passes `"stock"` to `record_filter._matches_stock_filter()` (`src/record_filter.py:56-84`), so sourced Results rows with real supplier stock can be classified as `Out of Stock` because `record.get("stock")` is missing. Normalize a Results stock field from the chosen supplier or make the filter use an explicit field mapping. Unknown stock should be distinct from confirmed zero stock.

## 6. Shared Search/Filter Review

**Confirmed:** General Component Search and both Needs Review lookup actions call `component_lookup.search_components()` (`app.py:289-375`); Results and general search call `record_filter.search_and_filter()`. The lookup uses the existing PartsBox, Mouser, and DigiKey clients, and `manufacturer_aliases.manufacturers_equivalent()` (`src/component_lookup.py:18-212`). No new vendor HTTP client or parallel sourcing engine was introduced.

**Medium:** The application reports a source-toggle combination, but `LookupQuery.sources` falls back to PartsBox when empty (`src/component_lookup.py:114`), and the general UI also substitutes `DEFAULT_SOURCES` when every checkbox is off (`app.py:356-371`). Turning all sources off unexpectedly searches PartsBox. Respect an explicitly empty source set and show a prompt or empty result.

**Medium:** `_search_partsbox()` iterates all cached parts locally while supplier calls use their existing search endpoints. This is shared through one function, but it may be slow for large inventories. This is a scaling concern, not a Phase 3 regression proven by tests.

## 7. Parametric Search Readiness

**Implemented:** MPN/keyword term, manufacturer filtering, source toggles, and generic exact field/stock filtering over returned records. PartsBox results expose category/package if present.  
**Scaffolding:** `LookupQuery` has category, package, mounting, dielectric, tolerance, voltage, current, power, value, and arbitrary characteristics (`src/component_lookup.py:30-66`). These fields are not applied to supplier queries or filtered results in this phase.  
**Still needed later:** Parse real BOM characteristics, map source-specific fields, present available facets, handle units/ranges, and test category-specific filters. This is planned future work, not a Phase 3 regression.

## 8. Needs Review Workflow

**Confirmed:** Needs Review derives from `ActiveBomState.review_items()` and provides Retry Exact, Find Replacement, and Check PartsBox in that order (`app.py:256-286`). `build_review_items()` is reused rather than copied into the UI. PartsBox is an explicit later action, not an automatic first fallback.

**High:** The UI allows selecting a candidate without checking its required-quantity coverage or forcing a sourcing decision. A replacement can leave the queue while being unsuitable for purchase. The action should keep the row in review until the existing sourcing engine resolves it.

## 9. Replacement Lookup Review

**Confirmed:** Both replacement buttons use `render_replacement_lookup()`, `build_query_from_bom_row()`, and `search_components()` (`app.py:289-335`). Search prefill uses known MPN or description, and candidate selection writes through `ActiveBomState.update_row()` via `review_actions.apply_replacement()`.

**Medium:** Lookup priority is MPN over keywords (`src/component_lookup.py:64-65`). For an unavailable exact part, the default Find Replacement query can repeat only the same part-number search until the operator manually loosens it. This is usable as a first exact retry, but replacement discovery should offer a description/specification route without retyping known data.

## 10. Replacement Re-Sourcing Decision

**Critical, confirmed:** `apply_replacement()` at `src/review_actions.py:81-154` sets `selected_supplier`, supplier part number, stock, and `sourcing_status` directly from the lookup result. It does **not** call `sourcing_engine.apply_sourcing_decisions()` or `decide_no_split_supplier()` for the new component. Discovery source is therefore treated as purchasing source. A DigiKey-discovered part can be chosen even if Mouser could fulfill it, and a candidate below required quantity can be marked `Ready`. `supplier_order_qty` is not recalculated or reliably populated.

**Smallest fix:** Update the canonical row's component identity first; clear stale sourcing/PartsBox match fields; then re-run that row through the existing `apply_sourcing_decisions()` path (or a shared per-row seam extracted from it that preserves its cache, fallback, and no-split behavior). Copy the resulting decision back through `ActiveBomState.update_row()`. Keep the discovery source as traceability metadata only. Test Mouser full stock, Mouser shortage/DigiKey full stock, both shortage, API failure, and missing quantity after replacement.

## 11. Retry Exact Review

**Confirmed:** `retry_exact_sourcing()` calls existing client `find_best_match_for_row()` methods and `decide_no_split_supplier()`; it clears prior decision fields through `_EMPTY_DECISION` (`src/review_actions.py:23-79`). Errors are recorded in notes and the row is updated through canonical state.

**Medium:** Retry always calls DigiKey even after Mouser has enough stock, unlike `apply_sourcing_decisions()` (`src/sourcing_engine.py:151-180`). It therefore duplicates part of orchestration, may add unnecessary API traffic, and can append an irrelevant DigiKey error to a successfully Mouser-sourced row. Prefer invoking the existing sourcing path for one-row input, then merging that row back. Ensure prior supplier part number is not reused as a fallback for a newly selected component.

## 12. PartsBox Fallback Review

**Confirmed:** Check PartsBox uses the shared lookup and does not mutate inventory. `component_lookup._partsbox_part_to_result()` leaves stock unknown rather than inventing a value (`src/component_lookup.py:167-186`).

**Critical, confirmed:** The PartsBox branch of `apply_replacement()` sets `partsbox_match_status` but does not clear old `selected_supplier`, `supplier_part_number`, or `sourcing_status` (`src/review_actions.py:130-148`). A row previously sourced by Mouser still displays `source=Mouser` and `Ready` after selecting a different PartsBox component. Existing cart builders can still order the old supplier part. Clear all stale purchasing fields and keep external purchase readiness distinct from an internal part match. A PartsBox match alone does not prove stock availability.

## 13. Source/Status Model Review

**Confirmed:** `source` and `result_status` are separate derived fields in `src/active_bom_state.py:35-79`; the raw cleaner and sourcing statuses remain available.

**High, confirmed:** `_derive_result_status()` returns `Error` before checking `_needs_review()`, while `review_items()` uses `build_review_items()` and includes `supplier_match_status=error` (`src/active_bom_state.py:10-33,54-65,144-154`). `summary_counts()` counts only `result_status == "Needs Review"` (`:205-229`). A focused check produced one review row with `result_status=Error` and a Needs Review metric of zero. Count review membership directly, or define Error as a review subtype and keep tab count, status, and rows consistent.

**High:** `_derive_source()` prioritizes any `selected_supplier` even when its status is stale or does not match the selected component. This becomes visible in the PartsBox replacement case and should be made consistent when transitions clear old fields.

## 14. Purchasing Pipeline Interaction

**Confirmed:** `build_mouser_cart_items()` and `build_digikey_mylists_parts()` read the canonical DataFrame and select rows by `selected_supplier`/`sourcing_status`. They can consume a replacement row, but current tests prove only that manually stamped fields pass their gates (`tests/test_review_actions.py:95-150`). They do not prove legitimate sourcing or sufficient stock.

**Critical:** A replacement can be stamped sourced with an empty or stale `supplier_order_qty`; the item builders may skip it or submit the old quantity. Existing cart/MyList objects and exported files in `current_run` are not refreshed after a replacement. The handoff should consume a newly computed sourcing decision and regenerated artifacts, with a clear pending state before that occurs.

## 15. Cohesive-System Architecture Review

The main architecture rule is mostly preserved: one canonical DataFrame, one lookup entry point, one generic filter, and reused supplier/PartsBox adapters. The exception is replacement selection, which recreates sourcing *outcomes* inside `review_actions.py` instead of reusing the sourcing engine. Retry reuses the decision function but partially duplicates orchestration. Fix those seams by extending the existing sourcing path; no new replacement sourcing engine is needed.

## 16. Regression Findings

No existing cleaning, supplier priority, cart API invocation, MyList API invocation, or export test failed. Confirmed new defects are replacement-driven: premature supplier assignment, missing order quantity, stale supplier data after PartsBox selection, stale response/export snapshots, and inconsistent review counts. The general search all-off toggle also invokes PartsBox unexpectedly. The added tests cover UI rendering and direct state mutation but miss these cross-service transitions.

## 17. Findings by Severity

| Severity | Finding | Primary evidence |
|---|---|---|
| Critical | Discovery source becomes purchasing source without re-sourcing; shortage can show Ready | `src/review_actions.py:81-154` |
| Critical | PartsBox replacement leaves old supplier/order state active | `src/review_actions.py:130-148` |
| Critical | Purchasing can skip or use stale quantity after replacement | `src/review_actions.py:81-154`; cart/MyList item builders |
| High | Error rows are in review but omitted from Needs Review count | `src/active_bom_state.py:54-65,144-154,205-229` |
| High | Run response snapshots and downloads drift after state mutation | `src/workflow_runner.py:475-518`; `app.py:165-179` |
| Medium | Results Stock filter reads absent `stock` field | `app.py:214-219`; `src/record_filter.py:56-84` |
| Medium | Retry duplicates DigiKey call even after full Mouser stock | `src/review_actions.py:35-57` |
| Medium | All sources off still searches PartsBox | `app.py:356-371`; `src/component_lookup.py:114` |
| Medium | New run retains lookup/filter widget state | `app.py:65-68,130-134,201-219` |

## 18. Required Fixes Before Next Phase

1. Make replacement selection update component identity and invoke the existing sourcing decision before setting purchasing supplier/status/quantity. Preserve discovery source separately.
2. Clear stale sourcing and PartsBox fields on every component transition, including a PartsBox selection. Distinguish internal match from external purchase readiness.
3. Make status, review queue, and summary counts agree for Error and Needs Review rows.
4. Define and implement post-mutation refresh for response snapshots and downloads, or mark old artifacts clearly stale and prevent purchasing handoff until regenerated.
5. Add cross-service tests with realistic quantities, fallback, shortages, errors, PartsBox selection after prior sourcing, and an actual UI selection path that validates the resulting purchasing state.

## 19. Deferrable Improvements

- Full characteristic parsing and DigiKey-style parametric facets, once real source fields are mapped.
- Large PartsBox inventory search performance and dedicated inventory view.
- Reset run-scoped widgets and search-result caches when starting a new run.
- Distinguish unknown stock from confirmed out-of-stock, and make Results Stock filtering use the correct source field.
- Remove redundant DigiKey retry calls after a successful Mouser result.
- Durable DigiKey refresh-token persistence remains a separate deployment gate documented in `AutoBOM_DigiKey_Durable_Token_Strategy.md`.

## 20. External API Verification Items

Live Mouser CartKey envelope; DigiKey MyLists share identifier and add-parts response; PartsBox part/stock/tag/project-entry schemas; supplier stock fields and exact candidate response shapes. These were not verified with live calls and should not be inferred from mocked tests. No unsupported endpoint is proposed.

## 21. Final Recommendation: NO-GO

**NO-GO for the next feature phase until the critical replacement and consistency fixes are in place.** The shared state and lookup foundation is worth retaining. Correcting its transition rules through the existing sourcing path is smaller and safer than building another workflow. The separate DigiKey durable-token gate must also be resolved before hosted MyLists automation is declared release-ready.
