# AutoBOM Phase 3 Correctness Fix Pass — Implementation Report

**Trigger:** independent Codex review of Phase 3 (`Documentation/AutoBOM_Phase3_Independent_Review.md`), verdict **NO-GO for the next feature phase**.
**Scope:** correctness fixes only, on the existing Phase 3 architecture. No PartsBox Inventory, purchasing hand-off polish, parametric search expansion, Mouser share automation, DigiKey durable persistence, or deployment work was touched.

## 1. Files changed

**New:** none (this pass extends existing files only).

**Modified:**
- `src/sourcing_engine.py` — extracted `source_row()`, the shared single-row sourcing seam
- `src/review_actions.py` — `apply_replacement()`/`retry_exact_sourcing()` rewritten around `source_row()`
- `src/active_bom_state.py` — `needs_review` boolean, `_derive_stock()`, `summary_counts()` fix
- `src/record_filter.py` — source-specific stock coercion exposed publicly, Unknown-stock filter state
- `src/component_lookup.py` — explicitly-empty source set no longer falls back to PartsBox
- `src/workflow_runner.py` — new `refresh_response_snapshot()`, `stale_after_mutation` flag
- `app.py` — session-state reset on new run, staleness warning, quick-fill search buttons, all-sources-off handling
- `tests/test_review_actions.py` — rewritten around the corrected re-sourcing behavior
- `tests/test_active_bom_state.py`, `tests/test_record_filter.py`, `tests/test_component_lookup.py`, `tests/test_workflow_runner_contract.py`, `tests/test_app_smoke.py` — new coverage

## 2. Replacement re-sourcing design

**The defect:** `apply_replacement()` previously set `selected_supplier`, `sourcing_status`, stock, and supplier part number **directly from the discovery candidate** — the service that happened to surface the candidate (Mouser, DigiKey, or PartsBox) became the purchasing supplier by fiat, bypassing the existing sourcing decision entirely.

**The fix — one new shared seam, no second sourcing algorithm:**

`sourcing_engine.py` now exposes `source_row(row, mouser_lookup, digikey_lookup, persistent_cache=None, run_cache=None)`, extracted verbatim from the loop body `apply_sourcing_decisions()` already ran per row (same conditional DigiKey skip when Mouser covers the requirement, same cache dedup, same `decide_no_split_supplier()` call). `apply_sourcing_decisions()` itself now just calls `source_row()` once per row inside its existing loop — behavior is byte-for-byte unchanged (verified: all 9 pre-existing `test_sourcing_accuracy.py` tests still pass unmodified).

`review_actions.apply_replacement()` now:
1. Updates the canonical row's `mpn`/`manufacturer`/`description` to the replacement candidate's identity.
2. Clears every stale sourcing field (`EMPTY_SOURCING_DECISION`, moved into `sourcing_engine.py`) and PartsBox/legacy field (`partsbox_match_status`, `partsbox_part_id`, `supplier_match_status`) from the *old* component.
3. If the candidate was discovered via PartsBox, records that as an internal match (`partsbox_match_status="matched"`) — traceability only, not a purchasing decision.
4. Calls `source_row()` against the *new* component identity using real `MouserClient`/`DigiKeyClient` (or injected fakes in tests), and writes the resulting decision through `ActiveBomState.update_row()`.

The discovery source never determines the purchasing supplier. `test_discovered_via_digikey_but_mouser_covers_requirement_is_sourced_from_mouser` proves the review's exact example: a candidate found via DigiKey search ends up `selected_supplier="Mouser"` because Mouser can cover the requirement — normal Mouser-first rules decide, not discovery source.

## 3. How stale sourcing fields are cleared

`EMPTY_SOURCING_DECISION` (in `sourcing_engine.py`, used by both `source_row()`'s always-present-keys guarantee and `apply_replacement()`'s clearing step) resets `selected_supplier`, `supplier_part_number`, `unit_price`, `supplier_order_qty`, `mouser_stock`, `digikey_stock`, `sourcing_status`, `sourcing_notes` to `""` before re-sourcing runs. A second small dict, `_STALE_NON_SOURCING_FIELDS` (in `review_actions.py`, since `sourcing_engine.py` has no reason to know about PartsBox columns), clears `partsbox_match_status`/`partsbox_part_id`/`supplier_match_status`. Both are applied via one `ActiveBomState.update_row()` call before the new identity is even searched, so no stale value from the old component can leak into the new component's row under any code path — including a lookup exception on the new component (which still writes `EMPTY_SOURCING_DECISION`'s cleared values through `decide_no_split_supplier()`'s no-match branch).

`test_partsbox_replacement_clears_old_external_supplier_state` and the "old supplier part number cannot survive component transition" scenario (same test) directly verify a previously-Mouser-sourced row loses that supplier/part-number state before a PartsBox replacement's own state is set.

## 4. PartsBox replacement behavior

A PartsBox-discovered candidate is recorded as an internal inventory match (`partsbox_match_status="matched"`, `partsbox_part_id`) but **always** still goes through `source_row()` against Mouser/DigiKey. Three outcomes are now distinguishable and tested:
- No external match found → `partsbox_match_status="matched"` but `result_status` is **not** `"Ready"` (`test_partsbox_match_alone_does_not_claim_ready`) — a PartsBox match is not proof of purchasable external stock, since this client has no confirmed PartsBox stock field to trust.
- An external match is found too → both facts coexist: `partsbox_match_status="matched"` **and** `selected_supplier="Mouser"`/`result_status="Ready"` (`test_partsbox_replacement_still_attempts_external_sourcing_and_can_be_ready`).
- A previously Mouser-sourced row switching to a PartsBox replacement loses the old Mouser state entirely (§3 above).

## 5. Retry Exact changes

`retry_exact_sourcing()` now calls `source_row()` directly instead of unconditionally calling both `MouserClient.find_best_match_for_row()` and `DigiKeyClient.find_best_match_for_row()`. `test_retry_skips_digikey_when_mouser_already_covers_requirement` proves DigiKey is not queried when Mouser alone satisfies the row (0 calls recorded on the fake DigiKey client); `test_retry_falls_back_to_digikey_when_mouser_insufficient` proves the fallback still happens when it's needed. This removes the exact duplication/divergence the review flagged — Retry no longer risks appending an irrelevant DigiKey error note to an already-Mouser-sourced row.

## 6. Required-quantity handling

All five of the review's minimum scenarios are covered by dedicated tests in `test_review_actions.py`, all going through the real `decide_no_split_supplier()` via `source_row()` (not asserted against a hand-computed expectation):
- Mouser covers requirement → Mouser, Ready (`test_discovered_via_digikey_but_mouser_covers_requirement_is_sourced_from_mouser`)
- Mouser short, DigiKey covers → DigiKey, Ready (`test_discovered_via_mouser_but_mouser_shortage_falls_back_to_digikey`)
- Both short → `selected_supplier=""`, `sourcing_status="check_wall_inventory"`, `result_status="Needs Review"`, never Ready (`test_both_suppliers_short_stays_needs_review_not_ready`)
- Both lookups raise → `result_status != "Ready"`, failure recorded in `sourcing_notes` (`test_supplier_api_failure_does_not_mark_ready`)
- Missing/invalid `required_qty` → `sourcing_status="manual_review"`, never Ready (`test_missing_required_quantity_does_not_mark_ready`)

`supplier_order_qty` recalculation is verified directly against a distinct `qty_per_board`/`build_quantity` combination (`test_supplier_order_qty_is_recalculated_for_the_new_component`, expects `3 × 4 = 12`, not the row's stale prior value).

## 7. Review/status/count model

Kept the review's recommended model: `Error` remains a distinct `result_status` label (not forced into the string `"Needs Review"`), but a new `needs_review: bool` field — computed by the same `_needs_review()` check used everywhere (identical criteria to `build_review_items()`) — is injected into every row record. `summary_counts()["needs_review"]` now sums that boolean instead of string-matching `result_status == "Needs Review"`, so it is *always* exactly `len(review_items())`, and an Error row is counted and shown in the Needs Review tab even though its status label reads "Error." `test_error_rows_are_included_in_needs_review_count_and_view` asserts this equality directly. The app.py tab label (`f"Needs Review ({summary['needs_review']})"`) inherits the fix automatically since it reads the same `summary_counts()` value.

## 8. Post-mutation refresh / stale-artifact handling

New `workflow_runner.refresh_response_snapshot(response)`: recomputes `bom_rows`, `review_items`, and `results_summary` from `response["_active_bom_state"]` in one call, and sets `response["stale_after_mutation"] = True`. `purchasing` and `outputs` are deliberately left untouched — they describe artifacts already generated (cart submissions, exported files), which regenerating in-memory dict fields can't retroactively fix; instead, `stale_after_mutation` is the signal that those specific keys and any already-downloaded file no longer necessarily match the current state.

`app.py` calls this one shared function after both `retry_exact_sourcing()` and `apply_replacement()` succeed (never hand-updates `bom_rows`/`review_items`/`results_summary` inline), and `render_downloads()` shows a warning — *"Downloads, purchasing carts/lists, and the run summary below reflect the BOM before that change. Re-run BOM Automation to regenerate them..."* — instead of presenting stale files as current. No live cart/MyList API call is triggered automatically; regeneration remains an explicit operator action (re-running BOM Automation), consistent with the instruction not to auto-invoke purchasing APIs from a Needs Review click.

The Results Workspace display itself was already immune to this staleness before this pass — it renders exclusively from `active_bom_state.rows()`/`review_items()`/`summary_counts()`, never from the `current_run` dict snapshot keys. The fix closes the gap for anything that *does* read those snapshot keys (the downloads section, and any future purchasing-consuming code, which must now check `stale_after_mutation` first).

## 9. Stock filter correction

`record_filter.py` exposes `coerce_int_or_none()` (public, was a private duplicate). `active_bom_state.py`'s `to_records()` now injects a normalized `stock` field via `_derive_stock()`, which reads `mouser_stock` or `digikey_stock` depending on the row's actual `source` — BOM result rows never had a generic `stock` field, so the filter was previously always missing it and misclassifying every sourced row as unknown/zero. `_matches_stock_filter()` now has three states — `"In Stock"` (confirmed > 0), `"Out of Stock"` (confirmed ≤ 0), `"Unknown"` (no confirmed figure, e.g. a PartsBox-only row) — explicitly distinguishing missing data from confirmed zero. Both `app.py` stock selectboxes (Results Workspace and Component Search) now offer `"Unknown"` as a fourth option.

## 10. Session reset on new run

`app.py`'s `reset_run_scoped_session_state()` (called immediately when a new run replaces `current_run`) clears: `selected_review_row_id`, `results_search`, and all four `results_filter_*` widget keys back to their defaults, plus purges any `replacement_results_*`/`replacement_query_*` session keys left over from the previous run's Needs Review interactions. General Component Search's `lookup_results` is deliberately left alone — per the review's own allowance ("[Component Search] may remain independent only if that is intentional"), since it is a global entry point independent of any specific BOM run, not a per-run cache. `test_new_run_resets_run_scoped_session_state` exercises this through the *real* "Run BOM Automation" button click (via `AppTest.file_uploader.upload()`), not a hand-simulated call to the reset function.

## 11. Tests added

31 new/rewritten tests. Full list of the review's required minimum scenarios, each with its own test:
- Replacement discovered via DigiKey, sourced via Mouser after normal sourcing — §2/§6
- Replacement discovered via Mouser, Mouser shortage → DigiKey fallback — §6
- Both suppliers shortage — §6
- Supplier API failure — §6
- Missing required quantity — §6
- `supplier_order_qty` recalculation — §6
- PartsBox selection clears old external supplier state — §3/§4
- Old supplier part number cannot survive a component transition — §3
- Needs Review count includes Error rows — §7
- Purchasing builders receive only legitimately-sourced rows, and exclude shortage rows (`test_shortage_replacement_is_excluded_from_purchasing_builders`, plus the Mouser/DigiKey re-entry tests) — §2
- Stale artifacts are marked/regenerated correctly (unit-level in `test_workflow_runner_contract.py`, UI-level in `test_app_smoke.py`) — §8
- Stock filter handles source-specific stock and Unknown — §9
- All lookup sources disabled produces no supplier lookup (`test_explicitly_empty_source_set_returns_no_results_not_partsbox_fallback`) — component_lookup fix
- New run resets run-scoped session state, through the real button click — §10
- Actual Streamlit UI replacement selection ends with a correctly re-sourced canonical state, not manually stamped state (`test_selecting_a_replacement_updates_canonical_state_via_ui`, mocking `review_actions.MouserClient`/`DigiKeyClient` since the real UI path has no other injection point and this environment's `.env` has `SUPPLIER_DRY_RUN=false`) — §2

Also fixed a **test infrastructure bug found while writing these**: several new tests reused MPNs (`"NEWPART"`, etc.) across test methods, and `retry_exact_sourcing()`/`apply_replacement()` each build their own `SupplierLookupCache()` when not given one — without disabling the cache, tests were reading/writing the real on-disk persistent cache and leaking results between each other. `test_review_actions.py` and `test_app_smoke.py` now disable `SUPPLIER_LOOKUP_CACHE_ENABLED` for their duration.

## 12. Full test results

```
python -m unittest discover -s tests -v
Ran 156 tests in 5.253s
OK
```
(132 at the start of this pass → 156.) Tests that encoded the incorrect Phase 3 behavior were intentionally rewritten rather than left passing against a wrong contract — specifically the old `test_partsbox_replacement_marks_matched_without_sourcing_status` (asserted `result_status == "Ready"` for a bare PartsBox match) is now `test_partsbox_match_alone_does_not_claim_ready` (asserts the opposite, correct behavior), and the old retry test asserting unconditional dual-supplier calls is replaced by the Mouser-first-aware versions in §5.

```
python -m py_compile app.py src/*.py tests/*.py
```
passes clean.

## 13. Remaining known limitations

- **Component Search's own results are not reset on a new BOM run** — confirmed as an intentional, review-permitted choice (§10), not an oversight.
- **Purchasing artifacts are marked stale, not regenerated.** No automatic cart/MyList re-submission was added; the operator must re-run BOM Automation. This matches the instruction against auto-invoking live purchasing APIs from a Needs Review click, but means a teammate could still download a stale cart CSV/summary if they ignore the new warning.
- **Find Replacement's default query is still single-term** (MPN or description, chosen via the quick-fill buttons, not both simultaneously) — the underlying Mouser/DigiKey `search_candidates()` methods only accept one search string each; combining both would require a new vendor API call shape, which is explicitly out of scope for this pass.
- **External API limitations carried over unchanged:** Mouser Cart API response envelope/CartKey shape, DigiKey MyLists share identifier, PartsBox `project/get-entries` envelope and tag representation, and PartsBox stock/quantity field remain unverified against live calls.
- **DigiKey durable token persistence** remains gated in `Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md`, untouched by this pass.
- `FileTokenStore`'s temp-file naming and `runs/` retention remain deferred, as in prior phases.

## 14. Is Phase 3 now safe to build upon?

**Yes, for the specific defects this pass was scoped to fix.** The critical replacement re-sourcing defect (discovery source treated as purchasing source, shortage marked Ready) is corrected and re-verified through the real sourcing decision path, not a second implementation. Stale-state clearing, PartsBox/external-purchase separation, Retry Exact's orchestration, the review-count consistency bug, the stock-filter field bug, the all-sources-off bug, and session-state leakage between runs are all fixed and regression-tested, including one full pass through the actual Streamlit UI with mocked vendor clients.

**Still not appropriate to build final purchasing hand-off, PartsBox Inventory, or deployment on top of:** those remain correctly out of scope per the instructions, and the staleness-marking mechanism in §8 is a stopgap (mark-as-stale) rather than the eventual real answer (regenerate-on-demand or re-source-on-save), which a future purchasing-hand-off phase should design deliberately rather than inherit as-is.
