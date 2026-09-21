# AutoBOM Phase 4 Final Independent Review

**Date:** 2026-09-21  
**Scope:** Current repository after Phase 4. The implementation reports and strategy documents were treated as claims and context; the repository is the source of truth. No implementation or deployment-hardening work was performed.  
**Evidence labels:** **Confirmed** means demonstrated by code or a local test; **Inferred** means the likely consequence of confirmed behavior; **External** means vendor or hosted behavior still requiring verification.

## 1. Executive Verdict

**GO WITH FIXES.** Phase 4 completed the main functional scope through shared foundations: PartsBox Inventory uses `component_lookup`, filters and facets use `record_filter`, purchasing reads `ActiveBomState`, and live cart/MyList creation occurs only behind the explicit Regenerate Purchasing button. The prior replacement defect is corrected through the shared sourcing path.

Deployment hardening should not start until purchasing regeneration and download state are corrected. The current code clears the global stale flag even when regeneration partially fails, re-enabling failed or unchanged artifacts. The old multi-sheet workbook becomes downloadable again after regeneration despite still representing the pre-mutation BOM. Purchasing can also report **Ready for Handoff** when both vendor generations returned `created=False`, and retrying a partial failure can recreate the supplier artifact that already succeeded.

## 2. Independent Test Results

- `python -m unittest discover -s tests -v`: **216 tests passed** in 22.5 seconds.
- `python -m compileall -q app.py src tests`: **passed**.
- Streamlit AppTest produced expected bare-mode context warnings but no test failures.
- Focused read-only checks confirmed `derive_purchasing_status()` returns `Ready for Handoff` when both suppliers have `attempted=True` and `created=False`.
- The new tests meaningfully cover shared lookup reuse, facets, basic range filtering, explicit button invocation, once-per-click mocked calls, current CSV regeneration, and replacement-to-purchasing flow. They do not cover partial regeneration, stale workbook downloads, `created=False` status, or retry after one vendor succeeds.

## 3. PartsBox Inventory Review

**Confirmed:** `app.py:570-622` creates a PartsBox-only `LookupQuery` and calls `component_lookup.search_components()`. Empty-query browse-all uses the same `_search_partsbox()` loop as search (`src/component_lookup.py:182-212`). Manufacturer aliases reuse `manufacturers_equivalent()`. Results use the shared dynamic facet renderer and `search_and_filter()`. No inventory write button or new PartsBox write endpoint was added.

**Confirmed performance limitation:** Browse-all calls `PartsBoxClient.get_parts()` and materializes/adapts every returned part in memory before filtering. This is reasonable for a modest internal inventory but may become slow at larger scale. Measure with the real inventory during deployment verification; it is not currently a correctness defect.

**Low cohesion finding:** Storage locations correctly use `PartsBoxClient.list_storage_locations()`, but `app.py:652-660` reimplements production-tag detection instead of calling the established helper in `partsbox_project_builder.py`. The UI version accepts only a list cleanly, while the lifecycle helper also accepts tuple/set. Promote one public shared tag helper and use it in both places.

## 4. Shared Search/Filter Reuse

**Confirmed:** Component Search, replacement lookup, and PartsBox Inventory all route through `component_lookup.search_components()`. Results, Component Search, and Inventory route through `record_filter`. Existing Mouser, DigiKey, and PartsBox clients are reused. No second BOM model, supplier-selection engine, cart builder, or MyList builder was introduced.

The storage-tag display duplication above is the only material Phase 4 cohesion exception found. It is small and isolated.

## 5. Engineering-Unit Parser Review

**Confirmed safe behavior:** `src/engineering_units.py:36-90` returns `None` for missing or unparseable values, handles negative values, tolerance markers, known unit suffixes, and listed SI prefixes. `value_in_range()` never treats unknown as zero. Package text such as `SOIC-8` does not parse as a number.

**Low limitation:** Parsing is deliberately narrow and case-sensitive. Scientific notation, leading `+`, leading-decimal notation, and lower-case unit forms such as `5v` are rejected. This safely excludes data rather than misclassifying it. Document accepted syntax near the range UI or broaden tests/parser during hardening if live data uses these forms.

**Medium ambiguity:** The parser removes units and compares only base numeric values; it performs no dimensional validation. Generic PartsBox fields are mapped by key name into specific facet names, which limits accidental cross-dimension comparisons, but guessed or inconsistent live fields could still mix meanings. Verify real fields and units before presenting a facet as authoritative.

## 6. Parametric Filtering Review

**Implemented today:** Case-insensitive text search; exact categorical filtering; Source, Status, Manufacturer, and three-state Stock filtering; dynamic category/package/mounting/dielectric/lifecycle facets; numeric min/max filtering for voltage, current, power, tolerance, resistance, capacitance, inductance, and unit price when those fields exist.

**Dynamically supported:** Unrecognized non-empty PartsBox `part/*` fields are placed in `characteristics` and flattened into lookup records. A field matching the approved facet lists becomes available without page-specific parsing. Facets appear only when the current result set has data.

**Unverified:** Actual PartsBox characteristic names/types and Mouser/DigiKey parametric structures. Supplier results currently add only defensively extracted category data. Missing fields degrade to blank/absent and do not crash. This is safe scaffolding, not a defect.

**Low UI limitation:** Invalid bounds are silently ignored because they parse to `None` in `app.py:479-482`. A mistyped bound can therefore look applied when it is not. Show a validation message when nonblank input cannot be parsed.

## 7. Required-Quantity/Stock Review

**Confirmed:** `component_lookup.search_components()` derives `stock_sufficient` after lookup (`src/component_lookup.py:154-179`). It produces `True` for coverage, `False` for shortage, and `None` for unknown stock or missing/unparseable required quantity. PartsBox stock remains unknown rather than being fabricated.

This value is informational. Replacement selection re-enters `sourcing_engine.source_row()`, and the sourcing engine remains authoritative for final supplier choice. No second supplier decision was introduced.

## 8. Purchasing Handoff Review

**Confirmed:** `build_purchasing_summary()` reads the canonical DataFrame and reuses existing cart/MyList item builders (`src/workflow_runner.py:143-181`). It does not perform supplier selection. The page displays item and quantity counts, CartKey, DigiKey list ID, and the explicit unverified share-ID state.

**High:** A summary reflects current canonical items even when the displayed CartKey/list ID belongs to an older artifact. The status flag is meant to communicate this, but after partial regeneration the stale flag is cleared. Until per-artifact freshness is tracked, identifiers and item counts can describe different generations.

## 9. Purchasing-State Review

**Confirmed states:** Not Available, Generation Failed, Stale — BOM Changed, Needs Review, Not Yet Generated, and Ready for Handoff are implemented at `src/workflow_runner.py:114-140`.

**High, confirmed:** Readiness checks only whether either supplier was *attempted*, not whether required artifacts were created. Both `{attempted: True, created: False}` results produce `Ready for Handoff`. This happens legitimately when there are no items, an API returns a non-created result without raising, or an enabled integration skips internally. Define readiness per required supplier: no items should be “No artifact required”; items plus `created=False` should be pending/failed; items plus successful creation should be ready.

**Medium:** Regeneration flags passed by the UI are always `True`; environment-disabled services are represented as attempted but not created. This contributes to the false Ready state. Preserve a separate `enabled`, `required`, `attempted`, and `created` distinction.

## 10. Explicit Regeneration Safety

**Confirmed:** Only the handler at `app.py:723-726` calls `regenerate_purchasing()`. Normal reruns, navigation, filtering, expanding reviews, replacements, and downloads do not call it. Existing AppTest asserts a rerun causes no regeneration and one click invokes the shared function once.

One Streamlit event invokes each vendor function at most once. The code does not provide idempotency across repeated button clicks, browser retries, or a manual retry after partial failure. The UI does not disable the button after a completed generation, so a second intentional or accidental click creates another cart/list.

## 11. Mouser Workflow Review

**Confirmed:** Automatic cart creation remains in `mouser_cart_client.create_mouser_cart_from_bom()` and is reused unchanged by regeneration. Resolved rows come from canonical sourcing state. `_build_mouser_purchasing()` preserves best-effort CartKey extraction. Manual Model B sharing remains a separate instruction; no paste-back field, browser automation, or invented share endpoint was added.

**External:** Live CartKey response shape and future supported/private share API remain unverified.

## 12. DigiKey Workflow Review

**Confirmed:** Regeneration reuses `create_digikey_mylist_from_bom()`. List ID is retained, and `share_id` remains explicitly `None`/unconfirmed. Normal rerenders do not create a list. Phase 4 did not weaken the TokenStore implementation.

**Deployment gate:** Durable refresh-token persistence remains unresolved as documented. This is not a Phase 4 regression, but hosted MyLists cannot be release-ready without it or an explicit operational disablement.

## 13. Stale-Download Protection

**Confirmed before regeneration:** Retry/replacement calls refresh the in-memory snapshot and set `stale_after_mutation=True`; `render_downloads()` disables every download on Run BOM and Purchasing (`app.py:234-259`). Stale files are not downloadable through these controls.

**High, confirmed after regeneration:** `regenerate_purchasing()` clears `stale_after_mutation` unconditionally at `src/workflow_runner.py:278-290`, even if sourcing-report, DigiKey-list, PartsBox-export, vendor, or run-summary regeneration failed. `render_downloads()` disables solely from that Boolean. Therefore Generation Failed can coexist with enabled old/partial downloads.

Track freshness per artifact, or keep the global stale flag true whenever any required regeneration fails. Enable only files successfully regenerated from the current canonical state.

## 14. Regenerated Output Consistency

**Confirmed:** Cleaned CSV, sourcing report, DigiKey list CSV, and PartsBox import CSV are generated from `active_bom_state.dataframe`; snapshots and run summary are refreshed. Successful regeneration therefore includes current replacement MPNs, supplier decisions, quantities, and review count.

**High failure-path defect:** Cleaned CSV export at `src/workflow_runner.py:224-228` is outside a `try` block. Its failure escapes `regenerate_purchasing()` and the Streamlit button handler, unlike the report's claim that regeneration errors do not raise. Other export failures are caught but still permit staleness to clear. Wrap all regeneration stages and preserve safe artifact state.

**Medium:** `partsbox_unmatched_csv` is never regenerated. After replacement/resourcing, that old file is re-enabled with all other downloads and may contradict current PartsBox match state. Either regenerate it from retained current data or omit/disable it after mutation.

## 15. Workbook-Regeneration Gap

1. The original workbook path remains in `outputs`.
2. It is disabled immediately after mutation.
3. Successful or partially failed regeneration clears the global stale flag, so the unchanged workbook becomes downloadable again.
4. A user can reasonably mistake it for the current BOM because the button retains the ordinary “Download cleaned workbook” label and no post-regeneration warning remains.
5. Retaining original mapping/warnings DataFrames is a manageable contract extension for deployment hardening, but it is not required for the smallest safe correction.
6. **Smallest safe behavior:** after any canonical mutation, keep `cleaned_workbook` disabled or remove its output entry until it can be regenerated faithfully. Do not fabricate mapping/warning sheets.

**Severity: High** because the workbook can carry obsolete replacement and purchasing data while presented as current.

## 16. Failure/Retry Safety

**Confirmed:** Caught vendor/export failures populate `purchasing_regeneration_errors`; `derive_purchasing_status()` then reports Generation Failed. Canonical BOM state is not mutated by artifact generation.

**High:** If Mouser succeeds and DigiKey fails, the response discards the successful Mouser result when the function rebuilds both purchasing entries only from this attempt's local results in `src/workflow_runner.py:278-281`. A retry calls Mouser again and can create another cart before retrying DigiKey. The same inverse risk applies to MyList success followed by another-stage failure. Preserve successful per-supplier results and retry only missing/failed artifacts, or require an explicit “create another” action.

**High:** A vendor helper may return `created=False` without raising; this is not added to regeneration errors and can be labeled Ready. Validate returned creation state when items require an artifact.

## 17. Security/Retention Review

**Confirmed:** Run summaries exclude underscore-prefixed live objects but include structured purchasing objects containing raw Mouser cart and DigiKey create/add responses (`src/workflow_runner.py:347-397,423-438`). API keys and Authorization headers are request-side values and are not intentionally inserted into these response objects. Error logging uses the shared allow-list sanitizer in current clients.

**Medium deployment risk:** Vendor payload schemas are unverified and may contain internal IDs, account metadata, or future sensitive fields. Persisting entire raw responses in `run_summary.json` and retaining run directories indefinitely expands exposure. Before team release, store an allow-listed purchasing summary and retain raw payloads only when explicitly needed for short-lived diagnostics. Define `runs/` cleanup and access policy.

## 18. Cohesive-System Review

The intended flow is now structurally continuous: upload → clean → source → Results/Needs Review → shared replacement lookup → canonical mutation → shared re-sourcing → stale purchasing → explicit regeneration. Purchasing and exports consume the canonical DataFrame, and no manual re-entry of known component data is required.

The remaining problems are artifact lifecycle and failure semantics rather than a competing architecture. They should be fixed inside `workflow_runner` and the existing download/status UI.

## 19. Navigation/User-Flow Review

The four top-level pages are present and share session state appropriately. Run context survives navigation. Component Search and Inventory remain independent tools, while Purchasing uses the active run. The workflow is understandable, but Generation Failed currently leaves enabled downloads and a usable regeneration button without explaining duplicate-artifact risk. Add per-artifact result/freshness indicators during hardening.

## 20. Findings by Severity

| Severity | Finding | Location |
|---|---|---|
| High | Regeneration clears staleness despite export/vendor errors, enabling old/partial files | `src/workflow_runner.py:221-297`; `app.py:234-259` |
| High | Old workbook is re-enabled and presented as current after regeneration | `src/workflow_runner.py:193-200,284-290`; `app.py:247-259` |
| High | Ready for Handoff can be reported when required artifacts were not created | `src/workflow_runner.py:114-140` |
| High | Partial-success retry can duplicate a successful cart or MyList | `src/workflow_runner.py:254-281`; `app.py:722-726` |
| High | Cleaned CSV regeneration failure escapes rather than being recorded | `src/workflow_runner.py:224-228` |
| Medium | Old PartsBox unmatched CSV is re-enabled without regeneration | `src/workflow_runner.py:246-252`; download map in `app.py` |
| Medium | Raw vendor responses and run artifacts lack retention/redaction policy | `_build_*_purchasing()`, `_write_run_summary()`, `runs/` |
| Medium | Unit comparison has no dimensional validation; live fields remain unverified | `src/engineering_units.py`; `src/component_lookup.py` |
| Low | Production-tag detection is duplicated in Inventory UI | `app.py:652-660`; `partsbox_project_builder._storage_has_tag()` |
| Low | Invalid range input is silently ignored | `app.py:466-482` |

## 21. Required Fixes Before Deployment Hardening

1. Preserve stale/disabled state for every artifact not successfully regenerated; never globally re-enable files after partial failure.
2. Keep the old multi-sheet workbook and old unmatched CSV unavailable after mutation unless regenerated correctly.
3. Derive purchasing readiness from required item counts and actual artifact creation, with explicit no-artifact-required, pending, partial, failed, and ready states.
4. Make regeneration catch every export failure, including cleaned CSV.
5. Preserve successful supplier artifacts across partial failure and make retry target only failed/missing suppliers to avoid duplicate cart/MyList creation.
6. Add tests for partial exports, vendor `created=False`, one-supplier success/one failure, retry after partial success, and workbook/unmatched-download state.

## 22. Deferrable Improvements

- Optimize PartsBox browse-all after measuring real inventory size.
- Expand engineering-value syntax based on observed live data.
- Validate invalid range text in the UI.
- Consolidate production-tag parsing into a public shared helper.
- Add richer vendor parametric extraction only after confirming schemas.

## 23. External Verification Items

- Mouser CartKey response envelope and any supported/private share mechanism.
- DigiKey MyLists share identifier and exact success/error response fields.
- PartsBox stock quantity, storage tag, project-entry, characteristic, and saved-filter schemas.
- Real supplier category/parameter structures and units.

No unsupported API endpoint should be inferred or added from this review.

## 24. Deployment Gates

- Durable, coordinated DigiKey refresh-token persistence, or hosted MyLists disabled with an accepted manual procedure.
- Live sandbox verification of Mouser cart and DigiKey MyList response handling.
- Safe regeneration/freshness fixes listed in section 21.
- Workbook/unmatched artifact policy after BOM mutation.
- Run-directory cleanup, retention, and access policy.
- Raw vendor payload allow-list/redaction decision.
- PartsBox live schema verification for inventory fields and production tags.

The workbook regeneration gap and raw payload retention are deployment-hardening work once the immediate unsafe re-enablement behavior is fixed. Durable token persistence and live identifier verification remain external/deployment gates, not Phase 4 architecture regressions.

## 25. Final Recommendation: GO WITH FIXES

Phase 4's shared functional architecture is suitable to retain. Correct purchasing readiness, partial-failure retry behavior, and artifact-specific freshness before beginning the broader deployment-hardening pass. After those targeted fixes and regression tests pass, proceed to deployment hardening; do not skip the separate durable-token and live-vendor verification gates.
