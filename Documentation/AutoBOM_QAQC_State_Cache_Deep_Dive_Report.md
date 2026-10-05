# AutoBOM QA/QC State and Cache Deep-Dive Report

**Audience:** Claude Code implementation engineer  
**Repository:** `Arr03463/Bom-automation`  
**Branch:** `team_release`  
**Audit date:** 2026-09-26  
**Scope:** Operator controls, cached supplier data, canonical BOM mutations, purchasing outputs, and regression coverage  
**Mode:** Audit and correction design only; application code was not changed

## Executive summary

The audit confirmed **seven defects** in the same family as the reported DigiKey-only failure. Three can directly produce incorrect sourcing or purchasing data, three can present stale or unauthorized choices to the operator, and one blocks a normal retry after processing failure.

| ID | Severity | Finding |
|---|---|---|
| Q1 | Critical | Disabled suppliers can still win sourcing from persistent or run cache. |
| Q2 | Critical | Changing build quantity preserves the old sourcing decision and old supplier order quantity. |
| Q3 | High | Supplier cache has no freshness limit and its key omits quantity-dependent lookup inputs. |
| Q4 | High | A malformed or obsolete cached value suppresses a valid live lookup. |
| Q5 | High | Find Replacement ignores the authoritative supplier checkboxes when choosing which suppliers to search. |
| Q6 | Medium | Main Search continues displaying cached results from suppliers that have been unchecked. |
| Q7 | Medium | A failed upload is marked processed and cannot be retried in place. |

A related purchasing status defect already observed by the operator is also reconfirmed: DigiKey can show `Not Required` beside a nonzero DigiKey item count after a canonical BOM mutation.

## Audit method and evidence

The review traced the following paths end to end:

- Search source checkboxes to uploaded BOM sourcing;
- source selection through Add to BOM, Retry Exact, and Find Replacement;
- persistent and per-run supplier cache reads;
- build quantity mutation through purchasing builders and exports;
- canonical BOM mutation through artifact freshness;
- upload deduplication and failure handling; and
- existing automated tests for each boundary.

The repository test suite was run with:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: **534 tests run; 533 passed and 1 errored**. The error was in `test_stale_supplier_caption_appears_when_draft_diverges_from_last_query`, where the test calls `at.session_state.get(...)`; the installed Streamlit AppTest session-state proxy does not expose `.get`. This is a test compatibility defect rather than evidence that the application behavior passed or failed.

`pytest` was unavailable in the active Python environment.

## Q1 — Disabled supplier cache bypass

**Severity: Critical**  
**Status: Confirmed and operator reproduced**

### Defect

The application represents a disabled supplier with `lambda row: None`. `source_row()` still calls `_cached_supplier_lookup()` for that supplier. `_cached_supplier_lookup()` checks the run and persistent caches before invoking the no-op function. A cached Mouser result can therefore win during DigiKey-only sourcing, and a cached DigiKey result can influence Mouser-only sourcing.

### Required correction

Add an explicit `enabled_sources` boundary to the shared sourcing engine and check it before any run-cache read, persistent-cache read, client construction, or live lookup. Pass the same set through uploads, Add to BOM, Retry Exact, Find Replacement re-sourcing, and the CLI.

Full implementation detail and acceptance tests are in:

`Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md`

## Q2 — Build quantity mutation leaves sourcing and purchasing quantities stale

**Severity: Critical**  
**Status: Confirmed by code path**

### Defect

`app.py::_apply_build_quantity()` recalculates these fields for uploaded lines:

- `build_quantity`;
- `required_qty`;
- cleaning `status`; and
- cleaning `notes`.

It does not recalculate or clear:

- `selected_supplier`;
- `supplier_order_qty`;
- `mouser_stock` / `digikey_stock`;
- `supplier_part_number`;
- `unit_price`; or
- `sourcing_status` / `sourcing_notes`.

Example failure:

1. A line has `qty_per_board = 3`, build quantity 1, and is sourced successfully with `supplier_order_qty = 3`.
2. The operator changes build quantity to 20 and clicks **Apply Build Quantity to Uploaded Lines**.
3. `required_qty` becomes 60, but `supplier_order_qty` remains 3 and the row remains `Ready` with its old supplier and stock decision.
4. Purchasing regeneration consumes `supplier_order_qty`, so the resulting Mouser export or DigiKey MyList can request the old quantity.

Marking artifacts stale does not repair the canonical row. Regeneration exports the stale sourcing fields.

### Required correction

Choose and enforce one safe behavior:

**Recommended:** Re-source every affected uploaded row immediately through the shared `source_row()` seam using the current authoritative source selection after applying the new quantity.

If immediate vendor calls are undesirable, clear all sourcing-decision fields on affected rows and place them in Needs Review until the operator explicitly re-sources them. Do not leave a row Ready with an old quantity decision.

### Required tests

- Increasing build quantity beyond old stock must not leave the row Ready.
- `supplier_order_qty` must equal the recomputed requirement after successful re-sourcing.
- A supplier that covered the old quantity but not the new quantity must not remain selected.
- Regenerated Mouser/DigiKey purchasing data must use the new quantity.
- Manually added rows without `qty_per_board` must remain unchanged.

## Q3 — Supplier cache is indefinitely stale and omits quantity-dependent inputs

**Severity: High**  
**Status: Confirmed by cache schema and client behavior**

### Defect A: no expiration

`SupplierLookupCache` stores supplier results without a timestamp or TTL. Stock, price, supplier part number, and candidate selection can be reused indefinitely. PartsBox has an explicit five-minute snapshot TTL; external supplier sourcing has no corresponding freshness rule.

This can mark a row Ready using inventory that no longer exists.

### Defect B: cache key omits required quantity

`build_lookup_key()` uses:

- supplier;
- normalized manufacturer;
- normalized MPN; and
- normalized supplier part number.

It omits `required_qty`. Supplier lookup and candidate ranking receive `required_qty` and may choose a different stocked variation or candidate depending on the required quantity. A result cached for quantity 1 can be reused for quantity 1,000 without performing the quantity-sensitive lookup again.

Even when the final stock comparison rejects an insufficient cached result, the engine does not perform a fresh lookup to find a different candidate that may cover the new quantity.

### Required correction

- Store cache metadata including `cached_at` and schema version.
- Add a configurable supplier cache TTL, with a conservative production default.
- Include normalized `required_qty` in the cache key, or cache a quantity-independent complete candidate set and rerank it for the current quantity.
- Prefer the complete-candidate approach if supplier responses expose all viable variations; otherwise include quantity in the key.
- Provide an explicit operator or maintenance action to invalidate supplier cache safely.

### Required tests

- Expired cached data triggers a live lookup.
- Unexpired data is reused.
- Different required quantities cannot incorrectly share a quantity-dependent result.
- A cached insufficient result does not prevent a fresh lookup from finding another sufficient candidate.
- Cache schema upgrades fail open to live lookup.

## Q4 — Invalid cache entry suppresses live lookup

**Severity: High**  
**Status: Confirmed by control flow**

### Defect

`_supplier_result_from_cache()` catches `TypeError` and returns `None` for an obsolete or malformed cached object. `_cached_supplier_lookup()` then stores that `None` in the run cache and returns it immediately. It never invokes `lookup_fn()`.

Therefore, one malformed truthy cache entry becomes a false “supplier has no match” result for the run, even if the live supplier lookup would succeed.

### Required correction

Treat cache deserialization or validation failure as a cache miss:

1. remove or ignore the invalid entry;
2. do not put `None` into the run cache as the result of invalid cached data;
3. perform the live lookup; and
4. replace the bad entry with a valid versioned value if the lookup succeeds.

Validate that the restored result has the expected supplier and usable field types before accepting it.

### Required tests

- Missing fields, extra incompatible fields, wrong types, and old schema entries all fall through to live lookup.
- A genuine live “no result” can remain an in-memory run-cache miss optimization if desired, but must be distinguishable from corrupt persistent data.

## Q5 — Find Replacement searches unchecked suppliers

**Severity: High**  
**Status: Confirmed by UI handler**

### Defect

The **Find Replacement** button sets:

```python
st.session_state.replacement_lookup_sources = frozenset({"mouser", "digikey"})
```

This ignores `_authoritative_sources()`. As a result, with only DigiKey selected, Find Replacement still searches Mouser and presents Mouser candidates. Application text says the same source checkboxes govern Find Replacement.

The later **Use Selected Replacement** action passes `_authoritative_sources()` into re-sourcing, but that does not repair the unauthorized discovery call or the misleading candidate list. Q1 can then make the disabled cached supplier win again.

### Required correction

At Find Replacement activation, capture the currently enabled external suppliers:

```python
replacement_lookup_sources = frozenset(
    source for source in _authoritative_sources()
    if source in {"mouser", "digikey"}
)
```

If the set is empty, do not issue supplier searches; show a clear instruction to select at least one external supplier. Keep **Check PartsBox** as the separate PartsBox-only action.

Clear replacement results and selection when the active source set changes so candidates from a now-disabled supplier cannot remain actionable.

### Required tests

- DigiKey-only Find Replacement calls DigiKey and never constructs/calls Mouser.
- Mouser-only does the reverse.
- No external suppliers produces no external calls.
- Toggling sources while the replacement panel is open clears incompatible results and selection.

## Q6 — Main Search displays results from suppliers that are now unchecked

**Severity: Medium**  
**Status: Confirmed by retained session-state design**

### Defect

Main Search stores a combined `component_search_supplier_results` list. Unchecking a supplier does not filter that stored list before rendering. The code clears the selected row if its source is unchecked, but old rows from the unchecked supplier remain visible as long as at least one supplier checkbox remains enabled.

This creates the same visual contradiction the operator encountered elsewhere: the source controls show DigiKey-only while the supplier table can still show Mouser results from the last combined search.

### Required correction

Filter retained results to the currently enabled supplier set before facets, pagination, display, and selection. Keep the underlying previous result set only if useful for avoiding another call when a source is re-enabled, but never present a disabled source as active current results.

Display a stale indicator when the current source set differs from the source set used for the last submitted search, and require Enter to fetch newly enabled sources.

### Required tests

- Search both suppliers, then uncheck Mouser: no Mouser rows remain displayed or selectable.
- Re-enable Mouser without pressing Enter: clearly mark results stale; do not imply a fresh lookup occurred.
- Facets and pagination derive only from currently visible sources.

## Q7 — Failed upload is marked processed before success is established

**Severity: Medium**  
**Status: Confirmed by upload control flow**

### Defect

`render_upload_intake()` writes:

```python
st.session_state["upload_intake_processed_file_id"] = uploaded_file.file_id
```

immediately after `run_bom_workflow()` returns and before checking `result["success"]` or whether an active BOM state was produced. On rerun, the same file is skipped as already processed.

A transient supplier failure may still produce an active reviewable BOM, but an early parsing/configuration failure can leave no usable state while blocking an in-place retry. The operator must remove and reselect the file to obtain a new file ID.

### Required correction

Track upload state explicitly by file ID or content fingerprint:

- `processing`;
- `completed`;
- `completed_with_reviewable_errors`; or
- `failed_retryable`.

Only suppress automatic reprocessing for completed states. Provide **Retry Upload** for a failed state. A content fingerprint is more stable and auditable than relying only on Streamlit's transient `file_id`.

### Required tests

- Parse failure exposes retry and the second attempt calls the workflow again.
- Successful processing remains idempotent across unrelated reruns.
- A supplier error that still produces canonical BOM rows does not duplicate rows on rerun.
- Same filename with different contents is treated as a new upload.

## Q8 — DigiKey artifact status can contradict current item count

**Severity: High**  
**Status: Confirmed and operator reproduced**

### Defect

`_mark_artifacts_stale_if_current()` only transitions `current` artifacts to `stale`. A DigiKey MyList previously marked `not_required` remains `not_required` after a row mutation or merge introduces DigiKey-sourced items. Purchasing summary item counts are recomputed from the live BOM, producing the contradictory display:

- Status: `Not Required (no items for this supplier)`
- Items: nonzero

### Required correction

After every canonical BOM mutation or merge, reconcile supplier artifact state with `_supplier_requirement()`:

- not required → required: set `not_generated` or `stale`;
- required → not required: set `not_required`;
- current required artifact with changed BOM: set `stale`.

Do this centrally in `refresh_response_snapshot()`, not separately in UI handlers.

## Q9 — Cleaned workbook becomes permanently stale after normal edits

**Severity: Medium**  
**Status: Confirmed by deliberate current behavior**

### Defect

After Retry Exact, replacement, build quantity change, DNP, customer-reference change, or merged upload, the multi-sheet cleaned workbook is marked stale. `regenerate_purchasing()` regenerates the cleaned CSV and purchasing-related CSV files but deliberately does not regenerate the workbook. The workbook download therefore remains disabled for the rest of that session even though the canonical BOM can be valid again.

This behavior is covered by a test, but it is an operator workflow gap: a normal correction permanently removes the richer workbook artifact.

### Required correction

Regenerate the workbook from the current canonical state, including a freshly derived Review Items sheet, or remove the workbook from the promised post-edit deliverables and clearly explain the limitation in the UI and operator guide. Regeneration is preferred.

## Cross-cutting correction design

### 1. Make authorization explicit

Use an explicit `enabled_sources` value throughout discovery and sourcing. A callback that happens to return `None` is not an authorization control.

### 2. Separate cached facts from current decisions

A supplier response may be cached, but supplier selection, stock sufficiency, order quantity, and Ready/Needs Review status must be recalculated from current inputs every time those inputs change.

Inputs include:

- enabled sources;
- MPN;
- manufacturer;
- supplier part number;
- required quantity; and
- cache freshness.

### 3. Centralize mutation reconciliation

Every canonical BOM mutation should run one reconciliation function that:

- recomputes derived row status;
- invalidates or recalculates affected sourcing decisions;
- reconciles required/not-required artifact states;
- marks generated outputs stale; and
- refreshes serialized snapshots.

UI handlers should not each approximate part of this sequence.

### 4. Test warm-state behavior

Most current source-selection tests disable persistent caching or use empty caches. Add a reusable test matrix covering:

- cold cache;
- warm valid cache;
- expired cache;
- corrupt cache;
- old-schema cache;
- changed required quantity;
- source toggled off after caching; and
- canonical BOM changed after artifact generation.

## Implementation order

1. **Q1 and Q5:** enforce source authorization before cache/client access and replacement discovery.
2. **Q2:** make build quantity changes invalidate and re-source purchasing decisions.
3. **Q3 and Q4:** version, validate, and expire supplier cache entries; include all decision-affecting inputs.
4. **Q8:** centralize supplier artifact requirement transitions.
5. **Q6 and Q7:** correct retained UI state and retry behavior.
6. **Q9:** restore workbook regeneration after canonical edits.
7. Run the full suite and add the warm-state matrix before live operator testing.

## Release acceptance criteria

Do not approve the QA/QC correction until all criteria pass:

1. An unchecked supplier is absent from discovery, cache use, client construction, sourcing decisions, and purchasing outputs.
2. Quantity changes cannot leave old stock sufficiency, supplier selection, or order quantity marked Ready.
3. Supplier cache entries expire and are validated; invalid entries fall through to live lookup.
4. Quantity-dependent lookups cannot reuse an incompatible cache result.
5. Find Replacement and Main Search reflect the currently selected sources.
6. Failed uploads can be retried without removing and reattaching the file.
7. DigiKey artifact status cannot say no items while current item count is nonzero.
8. All canonical edits produce regeneratable current exports, including the cleaned workbook if it remains a supported deliverable.
9. All tests pass in the deployment Python environment, including populated-cache regression tests and AppTests.

## Files expected to change

- `app.py`
- `src/sourcing_engine.py`
- `src/supplier_lookup_cache.py`
- `src/workflow_runner.py`
- `src/review_actions.py`
- `src/main.py`
- relevant source-selection, sourcing accuracy, purchasing-state, workflow, and AppTest modules
- operator documentation describing cache freshness and upload retry behavior

The correction must preserve the existing explicit Purchasing Handoff boundary: normal search, upload, retry, and replacement actions must not create a DigiKey MyList. Only the operator-triggered purchasing regeneration action may perform that vendor side effect.
