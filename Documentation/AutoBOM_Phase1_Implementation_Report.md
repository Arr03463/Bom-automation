# AutoBOM Team Release — Phase 1 Implementation Report

**Phase:** 1 of the phased plan in `AutoBOM_Claude_Code_Implementation_Spec_REVISED_AFTER_CODEX.md`
**Scope completed:** repository inspection/baseline verification, multi-user file isolation (P0), PartsBox duplicate-entry prevention (P0), PartsBox production-tag lifecycle (P1), structured `workflow_runner` return contract (P1).

## Baseline verification

- The repository was not under version control. Initialized git; the first commit (`fbc794d`) is the untouched baseline, before any Phase 1 changes.
- Confirmed audit facts: `python -m unittest discover -s tests -v` → 9 tests passed. `python -m py_compile` on all core modules → passed.
- **Discrepancy found vs. the audit:** `Documentation/env` contains live, unredacted PartsBox/Mouser/DigiKey API keys and a DigiKey refresh token, and was not covered by `.gitignore`. It was staged for the first commit and was removed before committing; it has never entered git history. `.gitignore` now excludes it explicitly.
  **Action needed from you:** rotate those credentials and either delete this file or move its contents into `.env` (which is already gitignored).

## Files changed

**New:**
- `src/run_workspace.py` — shared per-run workspace helper
- `tests/test_run_workspace.py`
- `tests/test_partsbox_lifecycle.py`
- `tests/test_workflow_runner_contract.py`

**Modified:**
- `app.py`
- `src/workflow_runner.py`
- `src/partsbox_project_builder.py`
- `.gitignore`

## What was fixed

### 1. P0 — Shared-file collisions
`run_workspace.py` gives every BOM run an isolated `runs/<run_id>/{input,output}` directory (`run_id` = a UUID4 hex). `app.py` saves uploads there instead of the shared `input/` folder; `workflow_runner.run_bom_workflow()` accepts `run_id`/`output_folder` parameters and threads them through every export call instead of the shared `output/` constant. No exporter (`sourcing_report.py`, `digikey_list_export.py`, `export_clean_bom*`, PartsBox CSV exports) needed changes — they already accepted an `output_folder` argument.

### 2. P0 — Repeated PartsBox runs duplicating BOM entries
`add_bom_entries_to_project()` now calls the existing `PartsBoxClient.get_project_entries()` before adding anything, builds a signature per entry (PartsBox part-id, or name, plus designators), and only submits entries whose signature isn't already present in the project. First-run, unchanged-repeat-run, and changed-BOM scenarios are covered by tests.

### 3. P1 — Production storage tagging
New storage locations are created with `tags=["production"]` (the client already accepted a `tags` parameter — no new endpoint needed). Reused storage that's missing the tag is detected and surfaced as a run warning: *"PartsBox storage '\<name\>' is missing the 'production' tag and no supported API call exists to add it to an existing storage location. Add the tag manually in PartsBox."* No tag-update endpoint was invented.

### 4. P1 — Structured workflow return contract
`run_bom_workflow()` now returns, in addition to the existing `summary`/`outputs`/`messages`/`errors`/`warnings`/`success` keys:
- `run`: `run_id`, `project_name`, `build_quantity`, `source_file_name`
- `bom_rows`: every cleaned BOM row as a dict, each with a stable `row_id` (`"<run_id>:<index>"`)
- `review_items`: the same shape, filtered to rows needing review, sharing `row_id` values with `bom_rows` so a review action can be matched back to its source row
- `partsbox`: project/storage names, reuse flags, `storage_tag_missing`, entries added/skipped/considered, unmatched count
- `purchasing.mouser`: `attempted`, `created`, `items_count`, `cart_key` (best-effort extraction, unverified against a live response), raw result
- `purchasing.digikey`: `attempted`, `created`, `list_id`, `list_name`, `share_id` (currently always `None` — no share-ID field exists in the current MyLists client), `parts_count`, raw create/add results

## Existing capabilities reused (not rebuilt)

- `PartsBoxClient.get_project_entries()`, `create_storage_location(tags=...)`
- `export_sourcing_report`, `export_digikey_list`, `export_clean_bom`, `export_clean_bom_workbook`, `export_partsbox_import_csv`, `export_partsbox_unmatched_csv`
- `build_review_items`, `apply_sourcing_decisions`, `create_mouser_cart_from_bom`, `create_digikey_mylist_from_bom`
- `main.py`'s CLI path is untouched and still works — `run_bom_workflow()`'s new parameters default to the original shared `OUTPUT_FOLDER` when not supplied.

## Tests

25 passed (9 original + 16 new). Full `py_compile` clean across `app.py`, `src/`, and `tests/`.

New coverage:
- Two runs uploading the same filename produce distinct paths and independent file contents (`test_run_workspace.py`)
- PartsBox first-run / unchanged-repeat-run / changed-BOM / no-project-id idempotency (`test_partsbox_lifecycle.py`)
- Production tag applied on create, detected-but-not-fabricated on reuse, no duplicate project/storage creation (`test_partsbox_lifecycle.py`)
- Structured response contract (`run`, `bom_rows` with `row_id`, `review_items`, `purchasing`, `partsbox` defaults) plus backward-compatible keys, end-to-end through `run_bom_workflow()` with isolated per-run output (`test_workflow_runner_contract.py`)

## Known limitations / unresolved items

- **Mouser CartKey / DigiKey share-ID shapes** are extracted defensively (`_extract_mouser_cart_key`) but unverified against a live API response — flagged in code comments in `workflow_runner.py`.
- **PartsBox saved-filter creation and any storage-tag-update endpoint** remain unconfirmed. `Documentation/partsbox api rules.pdf` (73 MB) could not be parsed in this environment (no PDF renderer/library available) — needs manual verification before either is implemented. No endpoint was invented in its place; the gap is surfaced as a warning instead.
- **Supplier lookup cache concurrency (P1)** and **DigiKey `.env` token-rewrite on refresh (P1)** are not yet addressed.

## Regression risk

Low. All changes are additive to the response contract or parameterize previously-hardcoded paths with a default matching the old behavior; no existing keys, exported file formats, or CLI (`main.py`) behavior were changed.

## Recommended next phase

Supplier lookup cache concurrency safety and DigiKey token persistence (the two remaining P1 hosting blockers), before starting the Results workspace / shared component search UI work.
