# AutoBOM Disabled Supplier Cache Bypass — Correction Report

**Audience:** Claude Code implementation engineer  
**Repository:** `Arr03463/Bom-automation`  
**Branch:** `team_release`  
**Review date:** 2026-09-26  
**Status:** Confirmed correctness defect; implementation required

## 1. Operator report

When the operator unchecks PartsBox and Mouser and leaves only DigiKey selected, an uploaded BOM can still produce rows sourced from Mouser. The observed screen showed:

- DigiKey selected
- Mouser not selected
- three Working Parts List rows with `Source = Mouser`
- zero DigiKey rows

This is not an operator sequencing problem. The source checkboxes are passed correctly from `app.py` into `run_bom_workflow()`.

## 2. Severity and impact

**Severity: High — purchasing correctness and operator-control violation.**

An explicitly disabled supplier can still be selected for purchasing. The application UI states that the source checkboxes govern uploaded sourcing, Add to BOM, Retry Exact, and Find Replacement. Current behavior violates that contract whenever a persistent cached result exists for the disabled supplier.

The defect can affect:

- uploaded BOM sourcing;
- Add to BOM re-sourcing;
- Retry Exact;
- Find Replacement after candidate selection;
- the command line DigiKey-only mode; and
- any future caller that disables a supplier by passing a no-op lookup.

## 3. Confirmed root cause

### 3.1 Checkbox wiring is correct

`app.py::_authoritative_sources()` reads the Mouser and DigiKey checkbox state. `render_upload_intake()` converts that set into `use_mouser_sourcing` and `use_digikey_sourcing`, then passes both booleans into `workflow_runner.run_bom_workflow()`.

The existing UI test only proves this handoff:

```python
self.assertFalse(kwargs["use_mouser_sourcing"])
self.assertTrue(kwargs["use_digikey_sourcing"])
```

It does not test the sourcing result in the presence of a cached result.

### 3.2 A no-op lookup does not disable cache reads

In DigiKey-only mode, `src/workflow_runner.py` currently calls:

```python
apply_sourcing_decisions(
    result.clean_bom,
    mouser_lookup=lambda row: None,
    digikey_lookup=digikey.find_best_match_for_row,
)
```

`src/review_actions.py::_lookup_functions()` uses the same no-op-lambda pattern for an unchecked supplier. `src/main.py` also uses it for DigiKey-only mode.

However, `src/sourcing_engine.py::source_row()` always calls `_cached_supplier_lookup("mouser", ...)` first. `_cached_supplier_lookup()` checks the run cache and persistent cache before it invokes the supplied lookup function:

```python
if key in run_cache:
    return run_cache[key]

cached_value = persistent_cache.get(key)
if cached_value:
    return _supplier_result_from_cache(cached_value)

result = lookup_fn()
```

Therefore, `lambda row: None` prevents a new Mouser API request but does not prevent AutoBOM from using an old Mouser result. A cached Mouser result with sufficient stock wins under the normal Mouser-first decision logic, so DigiKey is never queried and the row is marked `sourced_mouser`.

The reverse problem also exists: a disabled DigiKey supplier can be satisfied from the DigiKey cache if execution reaches the DigiKey branch.

## 4. Required correction

Enforce supplier selection **before every cache read and before every live lookup** in the shared sourcing engine. Do not use a no-op callable as the authorization boundary.

### 4.1 Recommended interface

Add an explicit enabled-source argument to the shared sourcing functions, defaulting to both suppliers for backward compatibility:

```python
def source_row(
    row,
    mouser_lookup,
    digikey_lookup,
    persistent_cache=None,
    run_cache=None,
    enabled_sources=None,
):
    enabled = (
        frozenset({"mouser", "digikey"})
        if enabled_sources is None
        else frozenset(enabled_sources)
    )
```

Then guard the complete supplier path:

```python
if mpn:
    required_qty = parse_int(row.get("required_qty"))

    if "mouser" in enabled:
        try:
            mouser_result = _cached_supplier_lookup(
                "mouser", row, persistent_cache, run_cache,
                lambda: mouser_lookup(row),
            )
        except Exception as exc:
            lookup_notes.append(f"Mouser lookup failed: {exc}")

    if "digikey" in enabled and (
        not mouser_result
        or required_qty is None
        or mouser_result.stock < required_qty
    ):
        try:
            digikey_result = _cached_supplier_lookup(
                "digikey", row, persistent_cache, run_cache,
                lambda: _call_digikey_lookup(
                    digikey_lookup, row, mpn, manufacturer
                ),
            )
        except Exception as exc:
            lookup_notes.append(f"DigiKey lookup failed: {exc}")
```

Extend `apply_sourcing_decisions()` with the same argument and pass it unchanged to every `source_row()` call.

### 4.2 Update all callers

1. **`src/workflow_runner.py`**
   - Pass the set derived from `use_mouser_sourcing` and `use_digikey_sourcing` into `apply_sourcing_decisions()`.
   - Stop relying on `lambda row: None` to represent a disabled supplier.

2. **`src/review_actions.py`**
   - Pass the authoritative `sources` set into `source_row()` for Retry Exact and replacement re-sourcing.
   - Prefer constructing a `MouserClient` or `DigiKeyClient` only when that supplier is enabled. This avoids unnecessary configuration and token work for a disabled service.

3. **`src/main.py`**
   - Pass `enabled_sources={"digikey"}` in DigiKey-only mode.

4. **Other direct callers and tests**
   - Preserve default behavior when `enabled_sources is None` so existing both-supplier callers remain compatible.

### 4.3 Required invariant

For supplier `S`, when `S` is absent from `enabled_sources`:

- do not read `S` from the run cache;
- do not read `S` from the persistent cache;
- do not call `S`'s client or lookup function;
- do not use an earlier `S` result to make the sourcing decision; and
- do not report the row as sourced from `S`.

Cache entries may remain on disk for later runs where the supplier is enabled. Deleting the entire cache is neither required nor a sufficient permanent correction.

## 5. Regression tests required

Add tests at the shared sourcing-engine level. They must use a populated cache because an empty-cache test cannot reproduce this defect.

### Test A: DigiKey-only ignores cached Mouser

1. Create a row with a valid MPN and required quantity.
2. Prepopulate `SupplierLookupCache` with a sufficient Mouser result for the row.
3. Supply a DigiKey lookup that returns a sufficient DigiKey result.
4. Call sourcing with `enabled_sources={"digikey"}`.
5. Assert:
   - `selected_supplier == "DigiKey"`;
   - `sourcing_status == "sourced_digikey"`;
   - DigiKey lookup is called;
   - Mouser lookup is not called; and
   - cached Mouser stock does not appear in the decision.

### Test B: Mouser-only ignores cached DigiKey

Prepopulate a sufficient DigiKey result, enable only Mouser, and assert the DigiKey cache and lookup cannot influence the decision.

### Test C: Disabled supplier with no enabled match goes to review

Prepopulate a sufficient result for the disabled supplier while the enabled supplier returns no match. Assert the row is `check_wall_inventory`, not sourced from the disabled supplier.

### Test D: Both enabled still reuse cache

Confirm the correction does not disable the cache generally. With both suppliers enabled, an applicable cached result should still be reused and its live lookup should remain uncalled.

### Test E: Retry Exact and Find Replacement honor selection

At least one integration-level test must prepopulate a disabled-supplier cache entry and invoke the review-action seam with `sources={"digikey"}`. Assert that the updated canonical BOM row cannot become Mouser-sourced.

### Test F: Upload workflow result, not only parameter forwarding

Extend coverage beyond `test_app_navigation.py`'s boolean forwarding assertion. Run the workflow with Mouser disabled and a prepopulated Mouser cache entry, then assert the resulting BOM contains no `sourced_mouser` rows.

## 6. Acceptance criteria

The correction is complete when all of the following are true:

1. With only DigiKey selected, zero rows can be sourced from Mouser, even when valid Mouser results already exist in both run and persistent caches.
2. With only Mouser selected, zero rows can be sourced from DigiKey under the same cache conditions.
3. No API client or lookup callable for an unchecked supplier is invoked or constructed unnecessarily.
4. Upload, Add to BOM, Retry Exact, and Find Replacement all follow the same source restriction.
5. Both-supplier mode retains Mouser-first, DigiKey-fallback behavior and continues using cached results.
6. Existing cache concurrency and persistence tests continue to pass.
7. New populated-cache regression tests pass.

## 7. Related status-display defect

A separate confirmed issue can make Purchasing Handoff display `Not Required (no items for this supplier)` while simultaneously showing a nonzero DigiKey item count. In `src/workflow_runner.py::_mark_artifacts_stale_if_current()`, only artifacts with status `current` become `stale`; a prior `not_required` DigiKey MyList status survives after BOM mutations introduce DigiKey-sourced rows.

Correct this by reconciling supplier artifact status against the current `_supplier_requirement()` after a canonical BOM mutation. If DigiKey changes from not required to required, its MyList status must become `not_generated` or `stale`, never remain `not_required`. Add a regression test for the transition from zero DigiKey items to one or more DigiKey items.

This related display defect does not cause the disabled-supplier cache bypass, but it can obscure the result and should be corrected in the same implementation pass.

## 8. Files expected to change

- `src/sourcing_engine.py`
- `src/workflow_runner.py`
- `src/review_actions.py`
- `src/main.py`
- sourcing-engine and workflow/review-action test modules
- `src/workflow_runner.py` tests for the related `not_required` transition

Do not solve this by clearing the cache, disabling cache globally, or changing supplier priority. The required correction is to make the authoritative source selection gate both cache access and live supplier access.
