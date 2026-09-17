# AutoBOM Technical Review Findings

**Review result:** PASS WITH FINDINGS for the current local workflow; BLOCKED for a multi-user team release.  
**Scope:** The `bom-automation-main` files present in this workspace.  
**Basis:** Direct code inspection and local test execution. The attached audit charter and pasted brief were used as reference material; their planned requirements are distinguished from functionality confirmed in the code.

## Executive summary

The current application has a reusable workflow: `app.py` calls `run_bom_workflow()` in `src/workflow_runner.py`. The runner cleans a BOM, calculates build quantities, applies Mouser/DigiKey sourcing decisions, optionally creates purchasing and PartsBox artifacts, and exports reports. The sourcing decision preserves Mouser-first, DigiKey-fallback, no-split behavior.

The largest release risks are shared input/output filenames, repeated PartsBox BOM entry creation, and loss of structured cart, list, and processed-row data before it reaches the UI. The current UI offers upload, run controls, metrics, messages, and downloads. Planned results, search, inventory, and replacement views are not present in this code.

## Findings

### P0 — Shared files can collide across users

**Confirmed from code.** `app.py:29-36` saves an upload as `input/<sanitized original filename>`. `src/workflow_runner.py:93-101` writes a summary named from the source stem, and its report/export calls write to the shared `output/` directory. Two sessions using `bom.xlsx` can overwrite one another's input or generated files. `app.py:39-50` downloads from those paths, so a later run can affect an earlier user's download.

**Minimal fix:** Assign a unique directory per run and pass it to the existing workflow and exporters. Add a test with two same-name uploads and verify distinct paths and contents.

### P0 — Repeated PartsBox runs can add duplicate BOM entries

**Confirmed from code.** `src/partsbox_project_builder.py:184-225` reuses a same-name project and storage location. `add_bom_entries_to_project()` at lines 157-181 then builds and adds the entire BOM without comparing existing entries. `PartsBoxClient.get_project_entries()` exists at `src/partsbox_client.py:102-103` but is not used by that path. A repeat run against a reused project can therefore append duplicate entries.

**Minimal fix:** Check existing project entries through the current client before adding missing entries. Test first and repeated runs with mocked PartsBox responses. Preserve the current project/storage reuse behavior.

### P1 — Purchasing identifiers are dropped by orchestration

**Confirmed from code.** `src/mouser_cart_client.py:100-116` returns the cart API response inside `result`; a CartKey, if present in that response, is available there. `src/workflow_runner.py:186-200` keeps only an item count and message. `src/digikey_mylists_client.py:213-259` returns `list_id`, list name, and API results; `src/workflow_runner.py:217-233` reduces these to messages. Neither structured result reaches `app.py`.

**Minimal fix:** Add cart and MyList objects to the runner's returned dictionary while retaining current summary and output keys. Test realistic successful and missing-ID response shapes. Actual API response shapes require external verification.

### P1 — Processed and review rows are unavailable to the UI

**Confirmed from code.** `src/workflow_runner.py:130-315` holds `result.clean_bom` and computes `result.review_items`, but returns only counts, messages, warnings, errors, and paths. `app.py:103-153` displays metrics and downloads. It has no in-app processed BOM table, Needs Review list, or row state that a replacement could update.

**Minimal fix:** Expose a structured, stable representation of processed and review rows from the existing runner. Preserve current exports and summary. Add tests for the returned contract before extending the UI.

### P1 — Production storage tagging and saved filter are absent

**Confirmed from code.** `build_default_names()` at `src/partsbox_project_builder.py:14-22` already gives the project and storage the same name. `create_partsbox_project_and_storage()` at lines 184-225 looks both up before creation, but does not pass the `production` tag when creating storage or ensure it when reusing storage. `src/partsbox_client.py` exposes `storage/create` and `storage/all`; no saved-filter operation is implemented.

**Minimal fix:** Extend the existing PartsBox client/lifecycle to ensure the tag. Determine saved-filter API support from current PartsBox documentation before adding an endpoint; provide a documented manual filter procedure if unsupported.

### P1 — Persistent supplier cache is unsafe for concurrent writes

**Confirmed from code.** `SupplierLookupCache.save()` in `src/supplier_lookup_cache.py:39-52` writes directly to one JSON file without locking or atomic replacement. Concurrent runs can lose updates or encounter partial JSON. A load error resets the cache to empty at lines 21-30.

**Minimal fix:** Use atomic replacement with appropriate coordination, or disable/isolate the persistent cache in hosted multi-user use. Test concurrent update behavior.

### P1 — DigiKey token rotation assumes a writable shared `.env`

**Confirmed from code.** `DigiKeyClient.get_user_access_token()` in `src/digikey_client.py:56-95` calls `_update_env_value()` when a refresh token rotates. That helper rewrites the repository `.env` at lines 435-449. This can fail on read-only hosting or race between users/runs.

**Minimal fix:** Put token persistence behind a deployment-appropriate secret store before cloud deployment, with a mocked rotation test. No live token behavior was tested here.

## Existing capabilities to preserve

- `src/bom_cleaner.py`: CSV/XLSX cleaning, column mapping, consolidation, quantity calculations, and exports.
- `src/sourcing_engine.py`: shared supplier decision, Mouser-first/DigiKey-fallback, no-split full-quantity choice, and lookup caching.
- `src/mouser_client.py` and `src/digikey_client.py`: supplier lookup and candidate matching.
- `src/partsbox_client.py` and `src/partsbox_project_builder.py`: one PartsBox integration path, same-name project/storage lookup and creation, BOM entry building, and dry-run handling for implemented writes.
- `src/mouser_cart_client.py`: automatic Mouser cart API call and aggregated item payload.
- `src/digikey_mylists_client.py`: automated MyList creation and part addition.
- `src/workflow_runner.py`: common orchestration seam and existing summary/output contract.

Extending these paths preserves the cohesive-system rule. A separate search, replacement, supplier, or PartsBox implementation would duplicate working code.

## Current gaps relative to the attached charter

The repository has supplier part lookup and PartsBox part lookup, but no general component search UI or shared search/filter service. It has no dedicated PartsBox inventory view, replacement selection flow, saved PartsBox filter operation, stock retrieval operation, or build operation. The current `build_review_items()` in `src/main.py:299-311` is a DataFrame filter, not an interactive review workflow. These are planned features absent from this baseline, not regressions demonstrated by this audit.

PartsBox dry-run handling in `src/partsbox_client.py:61-72` covers the three write operations currently implemented: `project/create`, `storage/create`, and `project/add-entries`. Future writes must be added to that guard.

## Tests and limits

**Commands run:**

- `python -m unittest discover -s tests -v` — 9 tests passed.
- `python -m py_compile app.py src/workflow_runner.py src/partsbox_client.py src/partsbox_project_builder.py src/mouser_cart_client.py src/digikey_mylists_client.py src/sourcing_engine.py` — passed.

No production code or tests were changed for this review. The workspace does not contain `.git` metadata, so tracked-file history and secret-commit status could not be verified. No live PartsBox, Mouser, or DigiKey API call was made. Confirm saved-filter support, CartKey response shape, and DigiKey share identifiers against the live API or current vendor documentation before implementation.
