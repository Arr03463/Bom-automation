# AutoBOM Direct Cart Handoff — Implementation Report

**Repository:** `Arr03463/Bom-automation`
**Branch:** `team_release`
**Implemented:** 2026-09-28
**Authority documents:**
`Documentation/AutoBOM_Claude_Code_Direct_Cart_Handoff_Implementation_Prompt.md`
(assignment), `Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md`
(evidence/context)

## 1. Implementation summary

The normal AutoBOM purchasing handoff no longer creates a DigiKey MyList
or a Mouser cart. It now produces:

- **DigiKey:** a deterministic FastAdd cart-loading URL the recipient
  opens directly in a browser, plus a verified-shape supplier-import
  CSV. When the encoded URL would exceed the safe length, the link is
  suppressed entirely and the CSV becomes the supported fallback — never
  a truncated link.
- **Mouser:** a supplier-import CSV.

Both are built from one shared, validated selection of canonical
purchasing lines (`src/purchasing_lines.py`), so item counts, the
DigiKey URL contents, and both CSVs can never disagree about which rows
qualify. Neither artifact makes a live vendor API call. DigiKey MyLists
automation (`src/digikey_mylists_client.py`) still exists in the
codebase but is no longer imported or reachable from the Streamlit app's
normal run/regenerate path at all — it survives only as an explicitly
separate, already-gated legacy path in `src/main.py`'s CLI tool.

## 2. Exact files changed

### New modules
- `src/purchasing_lines.py` — `PurchasingLine`, `PurchasingLineError`,
  `PurchasingLineResult`, `parse_purchasing_quantity()` (strict quantity
  parser), `build_purchasing_lines()` (the one shared
  selection/validation/aggregation implementation).
- `src/digikey_fastadd.py` — `build_digikey_fastadd_url()`, the pure
  FastAdd URL builder, `FASTADD_SAFE_LENGTH_CHARS = 1700`.

### Rewritten
- `src/digikey_list_export.py` — now a verified-shape DigiKey
  supplier-import CSV built from `purchasing_lines`, including the
  DigiKey supplier part number (previously omitted — H3 in the audit).
- `src/mouser_export.py` — now a Mouser supplier-import CSV built the
  same way (best-effort header verification — see §4).
- `src/workflow_runner.py` — the purchasing artifact/readiness model:
  `REQUIRED_ARTIFACT_KEYS`, new `digikey_cart_link` artifact with
  `STATUS_CSV_FALLBACK`, `_purchasing_requirement()`,
  `_is_required_artifact_valid()`, `_reconcile_purchasing_requirement_status()`,
  rewritten `derive_purchasing_status()`/`build_purchasing_summary()`/
  `regenerate_purchasing()`/`run_bom_workflow()`. Removed the
  `run_digikey_mylist` parameter and the `purchasing`/`_purchasing_raw`
  MyList-shaped response fields entirely from new runs.
- `app.py` — `render_purchasing_handoff_section()` rewritten (Open
  DigiKey Cart / copyable `st.code()` URL / Download DigiKey CSV /
  Download Mouser CSV; no List ID, Share Identifier, or MyList-created
  fields); `render_downloads()`'s "Other Outputs" list no longer
  duplicates the two supplier CSVs; several stale MyList-era docstrings
  updated.
- `src/config_validation.py` — `collect_startup_warnings()` no longer
  calls `digikey_mylists_config_status()`/`mouser_cart_config_status()`
  (both legacy, gated behind their own `..._ENABLED` flag which defaults
  false).
- `src/deployment_preflight.py` — clarifying comment; behavior
  unchanged (already only warns when a legacy flag is explicitly true).
- `src/main.py` — CLI prompt/docstring now explicitly labels the
  cart/list-creation path as legacy.
- `.env.example` — DigiKey 3-legged OAuth / durable token-store section
  relabeled LEGACY/ADVANCED and moved under the MyLists flag; normal
  deployment only needs `DIGIKEY_CLIENT_ID`/`DIGIKEY_CLIENT_SECRET`.
- `Documentation/AutoBOM_Operator_Guide.md`,
  `Documentation/AutoBOM_Deployment_Guide.md` — Purchasing Handoff/
  Downloads/deployment sections rewritten for the new workflow; guide
  now states upfront that normal deployment needs no MyLists OAuth setup.

### Tests
- New: `tests/test_purchasing_lines.py` (21 tests),
  `tests/test_digikey_fastadd.py` (21 tests).
- Rewritten: `tests/test_purchasing_state.py` (34 tests),
  `tests/test_digikey_list_export.py`, `tests/test_mouser_export.py`
  (golden-file coverage for both CSV formats).
- Updated for the new API/UI shape: `tests/test_app_smoke.py`,
  `tests/test_app_navigation.py`, `tests/test_workflow_runner_contract.py`,
  `tests/test_customer_reference_ui.py`, `tests/test_config_validation.py`.

### Not changed
- `src/mouser_cart_client.py`, `src/digikey_mylists_client.py` — retained
  unmodified as the legacy implementations `src/main.py`'s CLI still
  uses.
- `src/sourcing_report.py` — already the rich, all-columns internal
  sourcing report distinct from the two supplier-import CSVs; satisfied
  the audit's H8 requirement without any change.

## 3. Key design decisions

- **One canonical selection, not four.** `build_purchasing_lines()`
  replaces the four previously-divergent selectors
  (`build_mouser_cart_items`, `build_digikey_mylists_parts`,
  `export_mouser_list`, `export_digikey_list`'s own ad hoc filters).
  Eligibility: matching supplier + confirmed sourced status + not DNP +
  nonblank supplier part number + a quantity that passes
  `parse_purchasing_quantity()`. A row that matches supplier+status but
  fails part-number/quantity becomes a `PurchasingLineError` — never a
  silent drop.
- **Requirement includes errors, not just valid lines.** A mid-review
  fix caught this: `_purchasing_requirement()` originally checked only
  `bool(result.lines)`, so a DigiKey row with an invalid part number
  (zero valid lines, one error) was invisible to the requirement check —
  its artifacts were never in `REQUIRED_ARTIFACT_KEYS`'s `required_keys`,
  so their `failed` status could never block "Ready for Handoff". Fixed
  to `bool(result.lines) or bool(result.errors)`. Caught by
  `test_digikey_row_missing_supplier_part_number_fails_and_blocks_ready`.
- **`digikey_cart_link` has its own status vocabulary.**
  `current`/`not_required`/`csv_fallback`/`failed`/`stale`.
  `csv_fallback` counts as "current and valid" for readiness — it's a
  documented terminal state (an oversized-but-otherwise-fully-valid
  DigiKey purchasing set), not a degraded one.
- **Everything reruns on every regeneration.** The old DigiKey MyList's
  "skip if already current" protection existed specifically to avoid
  creating a duplicate live list. Neither the CSVs nor the FastAdd link
  have a side effect to protect against duplicating, so all three simply
  re-export/re-derive every time, like `cleaned_csv`/`sourcing_report`
  already did.
- **`newcart=true` always sent.** So a recipient's existing DigiKey cart
  is never silently merged into by a link generated from an unrelated
  BOM.
- **No new `PurchasingLine` field for MPN/manufacturer changes the
  aggregation key.** `mpn`/`manufacturer` were added to `PurchasingLine`
  as descriptive-only fields (from the first contributing row) so the
  CSVs don't need a second lookup back into the BOM — they are never
  part of the `(supplier, supplier_part_number, customer_reference)`
  aggregation key or any eligibility decision.

## 4. Verified format sources

- **DigiKey FastAdd** (fully verified, 2026-09-28): DigiKey's own
  TechForum post "DigiKey FastAdd — Bulk add parts into a DigiKey cart
  via third party tooling and URLs"
  (`forum.digikey.com/t/digikey-fastadd-bulk-add-parts-into-a-digikey-cart-via-third-party-tooling-and-urls/61356`),
  which gives the base URL, 1-indexed `partN`/`qtyN`/`crefN` parameters,
  `newcart`/`utm_source`/`utm_content`, and the ~1700-character safe
  length, plus a complete example URL matched exactly by
  `build_digikey_fastadd_url()`'s output shape. This is a community
  TechForum post, not DigiKey's formal API reference — the best
  available primary source, not independently confirmed via a real
  FastAdd cart load from this environment (no DigiKey account/cart
  access here).
- **DigiKey CSV columns** (best-effort, 2026-09-28): based on a real
  DigiKey-format BOM export found via web search
  (`github.com/im-tomu/tomu-hardware/blob/master/bom-digikey.csv`) and
  DigiKey's BOM Manager documentation. Not independently verified via a
  live DigiKey upload from this environment.
- **Mouser CSV columns** (limitation disclosed, NOT independently
  verified): Mouser's own BOM Tool pages
  (`mouser.com/en/bomtool/`, `mouser.com/en/help/tools/how-to-create-a-new-bom`)
  could not be fetched from this environment (repeated timeouts,
  2026-09-28), and available secondary sources describe Mouser's
  importer as a flexible column-mapping tool rather than one fixed
  required header set. The shipped headers (`Mouser Part Number`,
  `Manufacturer Part Number`, `Quantity`, `Customer Reference`) use
  Mouser's own confirmed-live Cart API field names
  (`MouserPartNumber`/`Quantity`/`CustomerPartNumber`, confirmed live in
  an earlier session pass) translated to plain columns — a reasonable
  best effort, explicitly disclosed as such in `mouser_export.py`'s
  module docstring. **Re-verify directly against Mouser's current BOM
  Tool before relying on this for high-volume production use.**

## 5. State migration / backward compatibility

New runs no longer populate `response["purchasing"]`/
`response["_purchasing_raw"]` or `artifact_status["digikey_mylist"]` at
all. An existing in-memory Streamlit session that survived a hot reload
(or any other source of an old MyList-shaped response dict) is handled
by construction, not a separate normalization pass: every new reader
(`derive_purchasing_status()`, `build_purchasing_summary()`,
`_purchasing_requirement()`, `_mark_artifacts_stale_if_current()`) reads
only the new `REQUIRED_ARTIFACT_KEYS`/`digikey_cart_link` keys and never
looks at `purchasing`/`digikey_mylist` at all — those legacy keys, if
present, are simply inert. Verified directly by
`LegacyStateCompatibilityTests` in `tests/test_purchasing_state.py`,
which injects both legacy keys into an otherwise-real response and
confirms neither crashes nor influences the new readiness/summary
output.

## 6. Tests added and results

Commands run (from the repo root, using the project's `.venv`):

```
.venv/Scripts/python.exe -m unittest tests.test_purchasing_lines tests.test_digikey_fastadd -v
→ Ran 42 tests — OK

.venv/Scripts/python.exe -m unittest tests.test_mouser_export tests.test_digikey_list_export -v
→ Ran 17 tests — OK

.venv/Scripts/python.exe -m unittest tests.test_purchasing_state tests.test_workflow_runner_contract -v
→ Ran 52 tests — OK

.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
→ Ran 620 tests — OK
```

Coverage added matches the assignment's "Required tests" sections:
canonical-line selection/validation/aggregation/ordering, the strict
quantity parser's boundary cases, the FastAdd builder's encoding/
boundary/no-MPN-fallback/ordering behavior, zero-MyLists-call
verification (patched at `digikey_mylists_client`, the actual defining
module — patching `workflow_runner.create_digikey_mylist_from_bom`
would raise `AttributeError`, since that name is no longer imported
there), required-artifact-depends-on-supplier-counts, export-failure-
blocks-Ready-only-when-required, oversized-link-CSV-fallback-still-Ready,
failed-regeneration-clears-old-URL, retry-isolation, and the legacy
state-compatibility tests described in §5.

## 7. Manual validation

- `python -m py_compile` across every changed/new `src/*.py` and
  `app.py` — clean.
- `streamlit run app.py --server.headless true` launched successfully;
  `GET /` returned HTTP 200, `GET /_stcore/health` returned `ok`, and the
  process log showed zero errors/exceptions on startup and initial
  render.
- No browser-automation tool is available in this environment, so a full
  interactive click-through of all 10 manual scenarios in the assignment
  (oversized-link BOM, mixed-supplier BOM, DNP row, etc.) was not
  performed directly — the equivalent behavior is covered by the
  AppTest-based UI tests in `tests/test_app_smoke.py`
  (`PurchasingPageSmokeTests.test_digikey_cart_link_ui_shows_open_and_code_no_mylist_fields`
  drives the real `render_purchasing_handoff_section()` code with a real
  DigiKey+Mouser sourced BOM and asserts the Open link/code box/download
  buttons appear and no MyList-era field remains) and the workflow-level
  tests in §6, which exercise the actual `regenerate_purchasing()`/
  `build_purchasing_summary()` code paths for each scenario. This is the
  same disclosed limitation noted in this project's prior UI
  implementation passes.

## 8. Remaining limitations / risks

1. Mouser CSV column names are a best-effort translation of Mouser's own
   confirmed Cart API field names, not independently verified against
   Mouser's current BOM Tool import contract (see §4). Verify with a
   real Mouser BOM Tool upload before high-volume production reliance.
2. The DigiKey FastAdd URL format is sourced from a community TechForum
   post, not DigiKey's formal documentation, and has not been
   round-tripped through a real DigiKey cart load from this environment.
3. `src/digikey_mylists_client.py`/`src/mouser_cart_client.py` remain in
   the codebase, reachable only from `src/main.py`'s CLI tool behind its
   own operator prompt and `DIGIKEY_MYLISTS_ENABLED`/`MOUSER_CART_ENABLED`
   flags (both default `false`). They were not removed, per the
   assignment's "retain legacy code only if another clearly separate and
   supported function still uses it" allowance.
4. No live vendor credentials were available or used in this pass — all
   verification is via `python -m unittest`, `py_compile`, and a local
   `streamlit run` smoke test, not a real Mouser/DigiKey account
   round-trip.

## 9. Working-tree hygiene

This branch already carried substantial uncommitted work from an
earlier, separate session pass (a QA/QC state/cache correctness audit —
`src/review_actions.py`, `src/sourcing_engine.py`,
`src/supplier_lookup_cache.py`, and several `tests/test_sourcing_engine_*.py`/
`tests/test_review_actions.py` changes, plus
`Documentation/AutoBOM_QAQC_State_Cache_Deep_Dive_Report.md` and
`Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md`)
before this Direct Cart Handoff assignment began. All of it was
preserved untouched throughout this pass. An untracked file unrelated to
either pass, `Documentation/AutoBOM_Per_Line_Customer_Part_Number_Audit.md`,
was also present in the working tree throughout and was not read or
modified.

One background subagent delegated part of this work (rewriting
`tests/test_purchasing_state.py`) was accidentally launched with
worktree isolation, which put it on a stale, unrelated git branch
lacking this session's uncommitted changes. It correctly diagnosed the
mismatch, reconstructed enough of the real source files by reading them
directly from the main checkout to write a correct test file against
real ground truth, and reported back rather than guessing. Its output
was reviewed, applied directly to the real working tree, and verified
by running it against the real environment (catching and fixing one
real bug in the process — §3). The stale worktree and its branch were
then removed; three further sync agents it had spawned to reconstruct
the rest of the stale worktree were stopped as unnecessary once the
correct fix path was identified.

## 10. Final git status

```
 M .env.example
 M Documentation/AutoBOM_Deployment_Guide.md
 M Documentation/AutoBOM_Operator_Guide.md
 M app.py
 M src/config_validation.py
 M src/deployment_preflight.py
 M src/digikey_list_export.py
 M src/main.py
 M src/mouser_export.py
 M src/workflow_runner.py
 M tests/test_app_navigation.py
 M tests/test_app_smoke.py
 M tests/test_config_validation.py
 M tests/test_customer_reference_ui.py
 M tests/test_digikey_list_export.py
 M tests/test_mouser_export.py
 M tests/test_purchasing_state.py
 M tests/test_workflow_runner_contract.py
?? Documentation/AutoBOM_Claude_Code_Direct_Cart_Handoff_Implementation_Prompt.md
?? Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md
?? Documentation/AutoBOM_Direct_Cart_Handoff_Implementation_Report.md
?? src/digikey_fastadd.py
?? src/purchasing_lines.py
?? tests/test_digikey_fastadd.py
?? tests/test_purchasing_lines.py
```

(`src/review_actions.py`, `src/sourcing_engine.py`,
`src/supplier_lookup_cache.py`, `tests/test_review_actions.py`,
`tests/test_sourcing_engine_cache_validity.py`,
`tests/test_sourcing_engine_disabled_supplier_cache.py`,
`Documentation/AutoBOM_QAQC_State_Cache_Deep_Dive_Report.md`,
`Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md`,
and `Documentation/AutoBOM_Per_Line_Customer_Part_Number_Audit.md` are
listed separately above/omitted here as they belong to other,
independent work — not part of this assignment.)

No commit was created as part of this work; nothing has been pushed.

## 11. Completion gates — explicit accounting

1. **Normal AutoBOM use makes no DigiKey MyLists call.** ✅ Verified by
   `test_run_bom_workflow_never_calls_digikey_mylists`,
   `test_regenerate_purchasing_never_calls_digikey_mylists_even_with_digikey_rows`,
   `test_plain_rerun_creates_no_vendor_or_file_side_effect`, and the
   equivalent AppTest-level guard in `test_app_navigation.py`.
2. **DigiKey FastAdd uses confirmed DigiKey supplier part numbers.** ✅
   `test_never_falls_back_to_mpn`; `build_purchasing_lines()` rejects a
   blank supplier part number as an error, so a `PurchasingLine` can
   never lack one.
3. **Counts, URL contents, and supplier CSVs originate from the same
   validated lines.** ✅ One shared `build_purchasing_lines()`/
   `_generate_supplier_csv()`/`_generate_digikey_cart_link()` path in
   `workflow_runner.py`.
4. **Invalid or unresolved lines block a Ready state with a useful
   reason.** ✅ `test_digikey_row_missing_supplier_part_number_fails_and_blocks_ready`
   (after the `_purchasing_requirement()` fix in §3).
5. **Oversized URLs select a complete CSV fallback without truncation.**
   ✅ `test_oversized_digikey_cart_link_falls_back_to_csv_and_stays_ready`,
   `test_oversized_url_is_never_exposed_truncated`.
6. **Required artifact failures block Ready.** ✅
   `test_digikey_csv_export_failure_blocks_ready_when_digikey_required`.
7. **Purchasing mutations invalidate old links and exports.** ✅
   `_mark_artifacts_stale_if_current()` covers `digikey_cart_link`
   alongside the file artifacts; `test_cart_link_url_is_cleared_after_a_failed_regeneration`.
8. **Supplier CSV formats are supported by documented evidence and
   golden tests.** ⚠️ DigiKey: documented evidence + golden test. Mouser:
   golden test present; documented evidence is best-effort only (§4/§8).
9. **Old MyList-shaped state cannot crash or mislabel the UI.** ✅ §5,
   `LegacyStateCompatibilityTests`.
10. **The full relevant test suite passes.** ✅ 620/620.
11. **Operator and deployment documents describe the new workflow and no
    longer require MyLists OAuth/token persistence for normal
    deployment.** ✅ §2.
