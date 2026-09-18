# AutoBOM Phase 1 and Phase 2 Independent Review

**Date:** 2026-09-18  
**Scope:** Current repository at commit `b0b74ba`, with one unrelated untracked Phase 2 report. No Phase 3 feature work was performed.  
**Evidence labels:** **Confirmed** = demonstrated by code or local test; **Inferred** = likely effect of confirmed behavior; **External** = vendor or hosting behavior requiring a source beyond this repository.

## 1. Executive Verdict

**GO WITH FIXES for Phase 3 development; NO-GO for hosted team release.** Phase 1 established genuinely reusable run workspaces and a richer workflow result. Phase 2 improved cache writes and separated DigiKey token persistence from the client. However, the cache lock can time out and save without exclusion, PartsBox deduplication is only an exact identity check and can both miss changed quantities and append duplicates after an unrecognized response, and the default hosted DigiKey token store does not preserve rotations even across new client instances in the same process. These issues should be corrected before Phase 3 relies on the foundation.

## 2. Test Results

- `python -m unittest discover -s tests -v`: **51 tests passed**.
- `python -m compileall -q app.py src tests`: **passed**.
- Focused, read-only Python checks confirmed a new `MemoryTokenStore` instance cannot read a value set on an earlier instance; changing only `entry/quantity` leaves `_entry_signature()` unchanged; an unrecognized PartsBox entries response becomes an empty list; nested `Cart.CartKey` extraction works.
- No live supplier or PartsBox calls were made. The existing tests use mocked integrations, so they cannot establish real response shapes or hosted token continuity.

## 3. Phase 1 Verification

**Confirmed:** `app.py` calls `build_run_workspace()` for each button-triggered run and passes its ID and output directory to `run_bom_workflow()`. The runner threads that output directory through the current exporters. Same-name upload tests and workflow tests pass. The result contract adds `run`, `bom_rows`, `review_items`, `partsbox`, and `purchasing` while preserving previous top-level keys. PartsBox project/storage reuse and new-storage production tagging are present. Automatic Mouser cart creation and DigiKey MyList creation remain in the runner.

**Qualification:** The Phase 1 report calls the PartsBox work “idempotency.” It prevents some exact duplicate appends, but does not synchronize changed quantities or safely handle every existing-entry response shape. See section 5.

## 4. Per-Run Workspace Review

**Confirmed:** `src/run_workspace.py:9-52` uses UUID4 IDs and `runs/<id>/input` and `runs/<id>/output`. `app.py:70-89` creates a workspace per execution, saves the upload there, and passes `output_folder`; `src/workflow_runner.py:247-269,313-466` uses that folder for summary, sourcing, DigiKey list, PartsBox CSVs, and cleaned BOM files. Exceptions use the same `output_folder` for the summary. The CLI path still defaults to global `output/` by design. Two same-name upload tests pass. No Streamlit state reuses a run ID.

**Medium, confirmed:** The UI displays downloads only inside the button branch (`app.py:70-153`), so a later Streamlit rerun can remove the previous result/download controls. It does not store the active result in `st.session_state`. This matters for Phase 3 state continuity, although it is not a cross-user collision.

**Medium, confirmed:** There is no cleanup or retention rule for `runs/`. Uploaded customer BOMs and raw outputs accumulate on the server (`src/run_workspace.py:20-52`). The UUID paths limit guessing but are not an access-control mechanism. The current UI does not expose arbitrary run paths to another session.

## 5. PartsBox Idempotency Review

**Confirmed:** `src/partsbox_project_builder.py:188-225` retrieves existing entries and skips signatures already present. `_entry_signature()` at lines 157-173 sorts designators, so reordered designators compare equally; part IDs distinguish matched components. First, repeat, and new-line tests pass.

**High, confirmed:** The signature excludes `entry/quantity`. A BOM line whose quantity changes is skipped as “already present,” leaving the PartsBox project stale. A focused check produced the same signature for quantities 2 and 5. The current implementation is append deduplication, not full BOM synchronization. The smallest safe response is to detect a same-identity, different-quantity entry and flag it for update/manual review until a supported update operation is verified.

**High, confirmed:** `_extract_existing_entries()` at lines 176-185 returns `[]` for any unrecognized successful response shape. `add_bom_entries_to_project()` then adds all intended entries. A schema change or unexpected envelope can silently recreate duplicates. Reject unrecognized responses before writing; test malformed and empty but valid responses separately. API exceptions already propagate rather than silently marking entries as present.

**Medium, inferred:** Signature fallback for unmatched entries uses only lowercased name plus designators. Missing names can create weak identities, and a formerly unmatched row that later resolves to a part ID changes signature and can be appended again. Test these transitions against realistic PartsBox records. Same component with different designators is intentionally treated as a different entry. Concurrent runs against the same project can still both read before either writes; no PartsBox-side transactional guarantee was verified.

**Confirmed:** `PartsBoxClient.call()` dry-run guards current write operations (`src/partsbox_client.py:60-72`). A dry-run project has no ID, so entry addition skips safely; a reused real project may still reach dry-run `add-entries`, but the client blocks the write.

## 6. PartsBox Production-Tag Review

**Confirmed:** Project and storage names match (`src/partsbox_project_builder.py:14-22`). New storage receives `["production"]` at lines 275-280. Existing same-name storage is reused and inspected; missing tags set `storage_tag_missing` at lines 263-289, and `src/workflow_runner.py:439-446` emits a warning. Empty tags are treated as missing. No update endpoint was invented, and saved-filter creation remains absent.

**Medium, external:** `_storage_has_tag()` expects a list, tuple, or set of plain strings under `storage/tags` or `tags` (`src/partsbox_project_builder.py:230-239`). If the actual API returns tag objects or another envelope, it may incorrectly warn. Confirm the real response schema before relying on tag status. Creation and reuse tests only exercise plain-string lists.

## 7. Structured Workflow Contract Review

**Confirmed:** `src/workflow_runner.py:39-64` preserves prior keys and adds structured fields. `_dataframe_to_row_records()` at lines 67-86 assigns `run_id:index` IDs; `review_items` comes from a filtered copy of `clean_bom` and retains corresponding pandas index labels (`src/main.py:299-311`). The runner exports before populating rows at lines 456-485. Its unit tests verify basic metadata and two rows.

**High for Phase 3, confirmed:** `bom_rows` and `review_items` are two copied lists of dictionaries, not references to a single mutable row. A future replacement action that edits one list will not update the other, the exported BOM, or purchasing automatically. The shared `row_id` is a join key, not canonical state. Phase 3 should designate one active BOM state and derive review/purchasing views from it, using the existing sourcing and exporter functions.

**Medium, inferred:** `_dataframe_to_row_records()` converts nulls but does not explicitly normalize all pandas/numpy values to JSON primitives; `_write_run_summary()` serializes the entire response (`src/workflow_runner.py:211-220`). Raw vendor payloads are usually JSON but no validation enforces that. If a non-serializable value arrives, summary writing can make an otherwise completed run report failure. Add a serialization contract test with representative numeric/date/vendor fields and isolate summary-writing errors from core processing.

## 8. Mouser Cart Preservation Review

**Confirmed:** `src/mouser_cart_client.py:20-60,100-116` still POSTs the aggregated items to `/api/v1/cart/items/insert`; its raw response reaches `_build_mouser_purchasing()` (`src/workflow_runner.py:131-154`) and is returned. `_extract_mouser_cart_key()` at lines 111-128 checks top-level `CartKey` and `Cart.CartKey` and returns `None` otherwise. The current code does not falsely fabricate a key.

**Medium, confirmed:** `created` may be true while `cart_key` is `None`; the UI only displays “items prepared.” That is ambiguous for purchasing. Distinguish dry-run, submitted-with-key, and submitted-without-key states. Live Mouser response shape remains unverified. Preserve automatic cart creation and treat manual sharing as a separate temporary step.

## 9. DigiKey MyList/Structured Handoff Review

**Confirmed:** `src/digikey_mylists_client.py:213-259` still creates a list and adds parts. Its `list_id`, name, create result, and add result propagate through `src/workflow_runner.py:157-187`. Missing list ID returns `created=False`; API exceptions become runner errors. `share_id` is explicitly `None`, so the code does not claim a verified share identifier. No Mouser-style manual share requirement was added for DigiKey.

**Medium, confirmed:** The client marks `created=True` after `add_parts_to_list()` returns, without validating an application-level success field in that result. Actual response schema and any share key field need API verification.

## 10. Supplier Cache Concurrency Review

**Confirmed:** `src/supplier_lookup_cache.py:104-114` writes a unique temp file and atomically replaces the JSON file on successful completion. `save()` re-reads disk and merges only pending updates at lines 144-164. Ordinary sequential and eight-thread tests pass. Same-key updates are last writer wins. Corrupt JSON is treated as empty, allowing recovery, though a valid cache may be lost after corruption.

**High, confirmed:** The lock does not guarantee exclusion: `_FileLock.acquire()` returns after ten seconds without setting `_acquired` (`src/supplier_lookup_cache.py:41-62`), and `save()` still executes read/merge/write. Two such writers can each read the same snapshot and overwrite unrelated updates. Atomic replacement prevents partial reads but does not prevent this lost-update race.

**Medium, confirmed:** A lock older than 30 seconds is deleted by pathname regardless of whether its owner is still working (`src/supplier_lookup_cache.py:64-87`). A later owner may acquire a new lock; the original owner then releases by pathname and can delete that new owner's lock. This is rare under normal short writes but undermines the lock guarantee on slow or paused processes. Temp files are cleaned after `os.replace()` failure, but a failure during the initial `write_text()` can leave a temp file.

## 11. File-Lock Timeout Safety Decision

**Decision: change before Phase 3.** On timeout, skip cache persistence for that run and keep sourcing results in memory; do not execute the merge/write without ownership. This preserves business behavior while allowing a disposable cache update to be lost. The lock should also avoid deleting a successor's lock by tracking an owner token and rechecking it at release/reclaim. Add deterministic timeout and stale-owner tests; existing fast threaded tests do not exercise either branch. On Windows, `os.replace()` can fail if another process holds the destination open; that should leave the sourcing run usable and only reduce cache persistence.

## 12. DigiKey TokenStore Review

**Confirmed:** `DigiKeyClient` now reads and writes through `TokenStore` (`src/digikey_client.py:18-44,67-107`). `digikey_oauth_setup.py` reuses `EnvFileTokenStore`; it no longer has its own env-file writer. Dry-run returns before token API calls. Stored token takes precedence over the static environment value when the same store instance is supplied. The abstraction is useful and small enough to retain.

**High, confirmed:** `build_token_store()` creates a *new* `MemoryTokenStore` on each call (`src/token_store.py:130-146`). `DigiKeyMyListsClient` creates a new `DigiKeyClient` per list operation/run. Therefore a rotated token in the default cloud backend is lost on the next client construction, even without restart. A focused check confirmed this. The Phase 2 report's claim of continuity across client instances is false. Use a process-shared store instance as a short-term correction, while still solving restart persistence for deployment.

**Medium, confirmed:** `EnvFileTokenStore.set()` writes directly to `.env` (`src/token_store.py:64-83`), so the report's broad “file writes are atomic” claim does not apply to this backend. `FileTokenStore.set()` uses a fixed `.tmp` name at lines 105-112; concurrent writers can collide. Neither file backend coordinates refresh-token use between concurrent clients. DigiKey token rotation makes that coordination relevant.

## 13. Streamlit Cloud Token-Persistence Decision

**External, confirmed by current vendor documentation:** DigiKey regenerates the refresh token on each refresh and says the previous token is no longer valid. [DigiKey OAuth documentation](https://developer.digikey.com/tutorials-and-resources/oauth-20-3-legged-flow). Streamlit says Community Cloud does not guarantee persistence of local file storage. [Streamlit storage documentation](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data).

**Conclusion:** With the current default memory backend, a refresh can invalidate the host-configured token; the next client instance may already fall back to that invalid token, and restart certainly does. The operator would have to reauthorize and update the host secret. That is not acceptable for an automated team purchasing handoff. Do not deploy this DigiKey MyLists path on Community Cloud as-is. A small persistent secret/value store with coordinated refresh, or a host with a durable private volume plus synchronization, is warranted. `TokenStore` can support this without redesign. The exact hosting choice is an implementation decision for a later phase.

## 14. Security Review

**Confirmed:** `Documentation/env` still exists locally, is ignored by `.gitignore`, is not tracked, and has no commit touching that path in current local history. The same is true of `.env`. Do not infer that credentials were never copied elsewhere. Rotate the credentials identified in the Phase 1 report; no values were read or reproduced in this review.

**Medium, confirmed:** `src/digikey_oauth_setup.py:87-90,139-142` prints full OAuth error response bodies. An error payload could contain sensitive request details; print a sanitized status and request ID instead. `src/partsbox_client.py:85-86` also prints full error bodies, and raw vendor results are embedded in the run summary JSON; review retention and redaction before team release. `runs/` has no cleanup policy.

**Informational:** The Phase 2 implementation report is currently untracked (`git status --short`); that does not affect runtime behavior. A filename-only search of tracked files found no obvious committed env/credential file. This is not a full secret-history scan.

## 15. Regression Findings

The existing sourcing accuracy tests still pass, and the runner still calls the existing Mouser, DigiKey, PartsBox, and export functions. No confirmed regression in supplier priority, quantity calculation, cart submission, MyList invocation, or CSV/XLSX generation was found. The meaningful uncovered branches are cache timeout/stale-lock behavior, token store instance continuity, changed PartsBox quantity, unexpected PartsBox response shape, vendor identifier extraction, and structured results after partial failures.

## 16. Cohesive-System / Phase-3 Readiness

The architecture is reusable: one runner owns processing, one sourcing engine decides suppliers, and existing adapters handle vendor calls. No parallel supplier or PartsBox client was introduced. The `row_id` bridge helps identify review rows, but it is not itself a state model. Phase 3 can use this foundation if it keeps a single active BOM state and derives search/review/purchasing views from it. Results rendered only from copies or exports would drift. Keep `app.py` thin and extend the runner/shared services.

## 17. Findings by Severity

| Severity | Finding | Evidence |
|---|---|
| High | Cache timeout permits unlocked save and lost updates | `src/supplier_lookup_cache.py:41-62,144-164` |
| High | Memory token backend loses rotations across client instances | `src/token_store.py:17-35,130-146`; `src/digikey_client.py:18-44` |
| High | Rotating DigiKey token lacks durable, coordinated cloud persistence | Same code; DigiKey and Streamlit docs in section 13 |
| High | PartsBox changed quantity is silently skipped | `src/partsbox_project_builder.py:157-173,188-225` |
| High | Unknown PartsBox entry response can cause duplicate append | `src/partsbox_project_builder.py:176-209` |
| High for Phase 3 | BOM and review rows are copied, requiring a canonical-state decision | `src/workflow_runner.py:67-86,478-483` |
| Medium | Stale lock can remove another owner's lock | `src/supplier_lookup_cache.py:64-87` |
| Medium | UI loses results on rerun; runs have no cleanup | `app.py:70-153`; `src/run_workspace.py:20-52` |
| Medium | Env-file writes are not atomic; fixed token temp name can collide | `src/token_store.py:64-83,105-112` |
| Medium | OAuth error bodies printed; raw results retained in summary | `src/digikey_oauth_setup.py:87-90,139-142`; `src/workflow_runner.py:211-220` |
| Medium | Cart can be marked created without extracted CartKey | `src/workflow_runner.py:111-154` |

## 18. Required Fixes Before Phase 3

1. Make cache timeout skip persistence safely; test timeout and stale-lock ownership.
2. Make PartsBox existing-entry parsing fail closed, and define changed-quantity behavior without silently skipping it.
3. Establish one canonical active BOM state for upcoming UI work; derive review rows from it.
4. Correct the process-memory token-store instance bug and define a durable, coordinated token plan before enabling hosted DigiKey MyLists. Phase 3 UI work can proceed only with the cloud limitation explicitly gated from release.

## 19. Recommended Fixes That Can Be Deferred

- Add run retention/cleanup and a session-state result holder before team rollout.
- Harden token file backends and sanitize OAuth/vendor error logging before deployment.
- Add realistic cart/list response fixtures and a test for summary JSON serialization.
- Confirm PartsBox tag representation and unmatched-to-matched entry transitions.

## 20. External API Items Still Requiring Verification

- Real Mouser Cart API response envelope and CartKey field; future sharing endpoint remains unverified.
- DigiKey MyLists share identifier and application-level add-parts success response.
- PartsBox project/get-entries response envelope, tag representation, entry update semantics, saved-filter creation, and storage tag update support. No endpoint should be invented from this review.

## 21. Final Recommendation

**GO WITH FIXES for Phase 3 development.** Fix the cache lock and PartsBox correctness gaps first, and define canonical BOM state before the Results UI consumes the new contract. **NO-GO for Streamlit Community Cloud team release with DigiKey MyLists enabled** until rotated refresh tokens have durable, coordinated persistence. No Phase 3 features or production changes were made in this review.
