# AutoBOM Foundation Fix Pass — Implementation Report

**Trigger:** independent Codex review of Phase 1 + Phase 2 (`Documentation/AutoBOM_Phase1_Phase2_Independent_Review.md`), verdict **GO WITH FIXES for Phase 3 development; NO-GO for hosted team release**.
**Scope completed:** the review's four required-before-Phase-3 fixes, plus the requested security corrections. No Results Workspace, search/filter, Needs Review, replacement, or Inventory UI was built.

## 1. Files changed

**New:**
- `src/http_error_utils.py` — shared, allow-list-based HTTP error describer
- `src/active_bom_state.py` — canonical active BOM state wrapper
- `tests/test_http_error_utils.py`
- `tests/test_active_bom_state.py`
- `Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md`

**Modified:**
- `src/supplier_lookup_cache.py` — lock ownership correction
- `src/token_store.py` — shared memory-store singleton
- `src/digikey_oauth_setup.py` — sanitized error output
- `src/mouser_cart_client.py`, `src/partsbox_client.py`, `src/digikey_mylists_client.py` — sanitized error output
- `src/partsbox_project_builder.py` — changed-quantity detection, fail-closed unknown response
- `src/workflow_runner.py` — canonical BOM state wiring, quantity-mismatch/unrecognized-response warnings
- `tests/test_supplier_lookup_cache_concurrency.py`, `tests/test_partsbox_lifecycle.py`, `tests/test_digikey_token_persistence.py`, `tests/test_workflow_runner_contract.py` — new coverage for all of the above

## 2. Cache-lock correction (exact behavior)

**The bug:** `_FileLock.acquire()` previously returned (implicitly `None`) on timeout without ever setting `_acquired = True`, but `SupplierLookupCache.save()` used `with _FileLock(...):` — the `with` block's body (read → merge → atomic write) ran regardless of whether the lock was actually held. A timed-out acquire silently proceeded as if locked, reintroducing the exact lost-update race Phase 2 was meant to close.

**The fix:**
- `_FileLock.acquire()` now returns `True`/`False` explicitly and never proceeds past a timeout implying success. `save()` checks the return value and, on `False`, returns immediately **without** touching the file — no read, no merge, no write.
- Each holder writes a random **owner token** (`pid:uuid4hex`) into the lock file instead of just the PID. `release()` re-reads the lock file and only deletes it if it still holds *this instance's* token — if a different token is now present (because this lock was reclaimed as stale and re-acquired by a successor while the original holder was still working), `release()` leaves it alone. This directly fixes the "original owner deletes a successor's lock" scenario the review demonstrated.
- `save()` now also catches `OSError` around the atomic write itself (not just the lock acquire) and treats it as a skipped, non-fatal save — covering the review's Windows `os.replace()`-can-fail note.
- The lock timeout is configurable via `SUPPLIER_LOOKUP_CACHE_LOCK_TIMEOUT_SECONDS` (default 10s) so tests can exercise the timeout path in milliseconds instead of really waiting 10 seconds.
- Atomic replace (temp file + `os.replace`) and merge-on-save (re-read latest file, apply only this run's pending updates) are unchanged from Phase 2 — this was a correctness fix to the locking, not a redesign.

**Tests added** (`tests/test_supplier_lookup_cache_concurrency.py`, 7 new + reused sourcing/cache fixtures):
`test_acquire_succeeds_when_free`, `test_acquire_times_out_when_held_by_another_owner`, `test_stale_lock_is_reclaimed_and_can_be_acquired`, `test_release_does_not_delete_a_successors_lock`, `test_save_is_skipped_without_error_when_lock_cannot_be_acquired`, `test_sourcing_decisions_still_succeed_when_cache_save_is_skipped` (runs real `apply_sourcing_decisions()` against a held lock and checks the sourcing result is still correct), `test_same_key_updates_resolve_last_write_wins`.

## 3. PartsBox changed-quantity behavior (exact behavior)

`_entry_identity()` (renamed from `_entry_signature()`) still deliberately excludes quantity — it answers "is this the same logical BOM line" (part-id or name, plus sorted designators), not "is this fully in sync." `add_bom_entries_to_project()` now, for every built entry:

1. Looks up an existing entry with the same identity.
2. **Not found** → genuinely new → appended.
3. **Found, quantity matches** → already present → skipped (unchanged from Phase 2).
4. **Found, quantity differs** → **neither skipped nor duplicated**. Recorded in a new `quantity_mismatches` list (entry name, part id, designators, existing quantity, intended quantity) and surfaced as a run warning: *"PartsBox quantity mismatch for '\<name\>': project has X, BOM now requires Y. Not updated automatically -- no verified PartsBox update operation is implemented; update the quantity manually in PartsBox."*

No PartsBox update endpoint was invented — the review's audit and my own read of `partsbox_client.py` confirm no such operation currently exists in this codebase, and `Documentation/partsbox api rules.pdf` still could not be parsed in this environment (73 MB, no PDF renderer available) to independently verify one.

## 4. PartsBox unknown-response behavior (exact behavior)

`_extract_existing_entries()` → replaced with `_extract_existing_entries()` returning an `ExistingEntriesExtraction(recognized: bool, entries: list)`:

- **Recognized, entries present or empty**: the response has one of `data`/`entries`/`project/entries` and its value is a list (an empty list is a valid, recognized "no entries yet" project). Proceeds normally.
- **Unrecognized**: response isn't a dict at all, or the expected key exists but its value isn't a list. `add_bom_entries_to_project()` returns `skipped=True, unrecognized_response=True` and **adds nothing**, rather than the old behavior of quietly treating an unparseable response as an empty list and re-adding everything. `workflow_runner.py` surfaces this as both a message and a warning.

## 5. Canonical active BOM state (design)

`src/active_bom_state.py` — `ActiveBomState(dataframe, run_id)` wraps the **same** `clean_bom` DataFrame object by reference, not a copy. It is the one thing `workflow_runner.py` now constructs per run:

- `rows()` — every row as JSON-safe dicts with `row_id = f"{run_id}:{index}"`.
- `review_items_dataframe()` / `review_items()` — derived **fresh on every call** via the existing shared `build_review_items()` (reused, not reimplemented).
- `to_records(dataframe)` — the one dict-conversion implementation used for both `rows()` and `review_items()`, so there is exactly one way rows become transport dicts.
- `get_row(row_id)` / `update_row(row_id, updates)` — the shared mutation seam a future replacement-selection flow must call through. Not used by any UI yet (none was built), but present and tested so Phase 3 has one seam to extend instead of inventing ad hoc dict mutation.

`workflow_runner.py` now builds one `ActiveBomState` near the end of the run, and derives `result.review_items` (used by the exported workbook's Review_Items sheet), `response["bom_rows"]`, and `response["review_items"]` all from that single object — removing the previous `_dataframe_to_row_records()` helper that was called independently against `result.clean_bom` and `result.review_items` as two separately-produced snapshots. Exporters (`export_clean_bom`, `export_clean_bom_workbook`) now explicitly consume `active_bom_state.dataframe` (the canonical object). Purchasing (`create_mouser_cart_from_bom`, `create_digikey_mylist_from_bom`) already operated on this same object by reference before and after this change — no separate purchasing-side copy was ever introduced.

**Tests added:** `tests/test_active_bom_state.py` (7 tests: all rows present, review derives from canonical state, updating a row is reflected in `rows()`, updating a row removes it from `review_items()` on regeneration, no second DataFrame copy, unknown-row-id handling for `get_row`/`update_row`). Plus one integration test in `tests/test_workflow_runner_contract.py` running a real BOM with a review-worthy row through `run_bom_workflow()` end-to-end and confirming the review row's `row_id` and field values are also present in `bom_rows` — proving both come from one canonical object, not two independently drifting copies.

## 6. DigiKey shared-memory token correction (exact behavior)

`build_token_store()` previously called `MemoryTokenStore()` fresh on every invocation. `token_store.py` now holds a module-level `_shared_memory_token_store`, lazily created once and reused for every subsequent call that resolves to the "memory" backend, plus `reset_shared_memory_token_store()` for test isolation. `DigiKeyClient(token_store=...)` injection is unchanged — this only affects the default (`token_store=None` → `build_token_store()`) path.

**Test added** (`tests/test_digikey_token_persistence.py`, `DigiKeyClientSharedMemoryTokenStoreTests`): constructs `DigiKeyClient()` (client A, no explicit store) with a mocked token endpoint that returns a rotated refresh token; asserts client A's rotation succeeds; then constructs `DigiKeyClient()` again (client B, no explicit store) and asserts `client_b.refresh_token == "rotated-by-client-a"`. This is exactly the review's reproduction case, now fixed and regression-tested. Also added `test_repeated_calls_share_the_same_memory_store_instance` and `test_reset_creates_a_fresh_memory_store` at the `token_store` level.

**This fixes process-lifetime continuity only.** It does not, and cannot, make a rotated token survive a process restart, redeploy, or Streamlit Community Cloud's own hibernation cycle — that limitation is separate and is addressed in the next section, not solved here.

## 7. Durable token-persistence recommendation

Documented in `Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md`, with an explicit gate: *final team deployment with `DIGIKEY_MYLISTS_ENABLED=true` must not be marked complete until a durable backend exists.* No infrastructure was added — this is a decision document, per the instructions.

Three candidate categories, no vendor chosen or hardcoded:
1. **A small external secret/value store reachable over HTTPS** — a `TokenStore` subclass making a `GET`/`PUT` call with a static API key (itself supplied via the host's own secret config).
2. **A durable private volume on a different host** — the existing `FileTokenStore` backend already implements this; pointing `DIGIKEY_TOKEN_STORE=file` + `DIGIKEY_TOKEN_STORE_PATH` at such a volume is a zero-code-change fix if the team moves off Community Cloud.
3. **A minimal persistent backend the team already operates** for other purposes (one row/object is enough).

Interim guidance until one is chosen: treat DigiKey MyLists automation on Community Cloud as best-effort, expect manual re-authorization after restarts that land between token rotations, and consider `DIGIKEY_MYLISTS_ENABLED=false` in the hosted deployment if that operational burden is unacceptable (DigiKey CSV export remains available regardless).

## 8. Security changes

- **OAuth error output** (`digikey_oauth_setup.py`, both `print(response.text)` sites): replaced with `describe_error_response()` — status code plus an allow-list of known-safe fields (`error`, `error_description`, `message`, `ErrorMessage`, `ErrorDetails`, `detail`, request-id-style fields). Never includes the raw body.
- **Vendor error output**, opportunistically corrected while already touching these paths per the instructions' "smallest safe corrections" guidance: `mouser_cart_client.py` (the Cart API call passes `apiKey` as a URL query parameter — the clearest real leak vector, since some vendor error responses echo request details back), `partsbox_client.py`, and all four raw-body prints in `digikey_mylists_client.py`. All now use the same shared `describe_error_response()` rather than four different ad hoc fixes.
- **Deliberately not touched:** the existing `_raise_for_status()` exception-message builders in `digikey_client.py` and `digikey_mylists_client.py` already attempt structured field extraction before falling back to raw text, and only reach that fallback on a true parse failure — rewriting them was judged out of scope for "do not broadly rewrite error handling in this pass."
- Re-verified: `Documentation/env` (live unredacted credentials, found in Phase 1) remains git-ignored and untouched by any code in this pass.

**Tests added:** `tests/test_http_error_utils.py` (5 tests) — known-field extraction, non-JSON fallback never contains the raw body, a JSON body with only unlisted fields never leaks them (tested with fake `apiKey=...`/`client_secret=...` strings), truncation.

## 9. Full test results

```
python -m unittest discover -s tests -v
Ran 83 tests in 2.056s
OK
```
(51 at the start of this pass → 83; all 51 prior tests still pass unmodified.)

```
python -m py_compile app.py src/*.py tests/*.py
```
passes clean.

## 10. Remaining external API verification items (unchanged from prior phases)

- Mouser Cart API response envelope / `CartKey` field shape — unverified against a live call.
- DigiKey MyLists share-identifier field and application-level add-parts success response — unverified.
- PartsBox `project/get-entries` response envelope, tag representation on `storage/tags`, any entry-update operation, and saved-filter creation support — unverified; `Documentation/partsbox api rules.pdf` still could not be parsed in this environment.

## 11. Remaining release blockers / risks (explicitly not fixed in this pass, by design)

These were flagged by the independent review as **deferrable** (its own section 19), not required before Phase 3, and were intentionally left alone here to avoid scope creep beyond the six requested items:

- **DigiKey durable token persistence itself** — documented and gated (§7), not implemented. This is the one item explicitly called out as blocking *hosted DigiKey MyLists production use*, not blocking Phase 3 UI work.
- `FileTokenStore.set()` uses a fixed `.tmp` suffix rather than a unique per-write temp name — a real but minor collision risk under concurrent writers, same class of issue as what was fixed in the supplier cache but not mirrored here yet.
- No `runs/` retention/cleanup policy — uploaded BOMs and outputs accumulate indefinitely under UUID-named directories.
- `app.py` does not yet store the active run result in `st.session_state`, so a later Streamlit rerun can drop the previous result/download UI. Not a cross-user collision; a Phase 3 UI concern.
- Raw vendor payloads (Mouser cart result, DigiKey create/add results) are embedded in `run_summary.json` on disk under `output/<run>/` — worth a retention/redaction review before team release, not fixed here.
- `_storage_has_tag()` assumes `storage/tags` is a plain list of strings — unverified against the live PartsBox response shape.

## 12. Is the foundation ready for Phase 3?

**Yes, for the specific items this pass was scoped to fix.** All four of the independent review's "required before Phase 3" items are corrected and regression-tested: the cache lock cannot save without ownership, PartsBox changed quantities are flagged rather than silently skipped and unknown responses fail closed, one canonical `ActiveBomState` now backs both `bom_rows` and `review_items`, and the DigiKey in-process token-sharing bug is fixed with the cloud-persistence gap explicitly gated in its own document rather than assumed away.

**Not yet ready for a hosted team release with DigiKey MyLists enabled** — that remains gated on choosing and implementing one of the three durable-persistence categories in §7. Phase 3 UI work (Results Workspace, shared search, Needs Review, replacement, PartsBox Inventory) can proceed against this foundation, per the instructions, but final release sign-off should not treat the DigiKey durability gap as resolved by this pass.
