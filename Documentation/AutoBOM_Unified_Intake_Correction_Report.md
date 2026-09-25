# AutoBOM Intake + BOM Configuration UI Correction Report

## 1. What this pass corrects

Upload and the general Component Search tool were still modeled as
separate workflow sections. Per the request, they are now two
alternative ways to populate the **same** canonical working BOM
(`ActiveBomState`), with Search as the default/primary intake method and
Upload as the secondary option beside it. Cart/MyList creation was also
removed from intake entirely -- it now only happens from an explicit
Purchasing Handoff action, as it already did, but the checkboxes that
used to expose it at intake time are gone.

## 2. New page composition

`render_autobom_workflow_page()` now composes, top to bottom:

1. **Add Parts** (`render_add_parts_section()`) -- Search (left, larger)
   and Upload (right, smaller), always visible regardless of BOM state.
2. **BOM Configuration** (`render_bom_configuration_section()`, only
   once the working BOM has at least one part) -- build quantity (with
   an Apply action), PartsBox project display, and Customer Reference
   nested inside.
3. **Results / Needs Review** (unchanged `render_results_workspace()`).
4. **Purchasing Handoff** (unchanged `render_purchasing_handoff_section()`).

## 3. Search is now a BOM-intake action, not just a lookup tool

`render_component_search_intake()` (evolved from the previous
`render_component_search_section()`, which is now retired -- there is no
duplicate search implementation) keeps the exact same search form/
filters (PartsBox default, optional Mouser/DigiKey, manufacturer filter,
dynamic facets) but renders results as a row list with a quantity input
and an **Add to BOM** button per result
(`render_add_to_bom_results()`), instead of a read-only table.

`_add_search_result_to_working_bom()`:
- If no working BOM exists yet, starts one via the new
  `workflow_runner.start_manual_bom_workflow()` -- an empty,
  schema-correct `ActiveBomState` (same `bom_cleaner.STANDARD_COLUMNS`
  an uploaded file's cleaned BOM has, so it can always be merged with
  one later). No PartsBox project, no sourcing, no exports -- there's
  nothing to process yet.
- Appends a blank row via the new `ActiveBomState.add_row()`, setting
  only the operator-entered quantity.
- Reuses `review_actions.apply_replacement()` **unchanged** to set the
  component identity and run it through the exact same Mouser-first/
  DigiKey-fallback sourcing decision (and PartsBox match recording, if
  discovered via PartsBox) Find Replacement already uses. There is no
  second "manually added part" sourcing implementation.

## 4. Upload merges into an existing working BOM instead of replacing it

`render_upload_intake()` still calls the unmodified `run_bom_workflow()`
to process an uploaded file (full cleaning, sourcing, PartsBox handling
-- unchanged). What changed is what happens with the result:

- **No working BOM exists yet** (fresh session, or Search never added
  anything): behaves exactly as before -- this becomes `current_run`.
- **A working BOM already exists** (started via Search, or an earlier
  upload): the new file's rows are merged into the *existing*
  `ActiveBomState` via the new `ActiveBomState.add_rows()` bulk-append
  method, instead of discarding what's already there. Messages/
  warnings/errors are appended; `refresh_response_snapshot()` recomputes
  summaries and marks regeneratable purchasing artifacts stale.

Both new `ActiveBomState` methods are covered directly in
`tests/test_active_bom_state.py` (`AddRowTests`, `AddRowsTests`),
including the pandas mechanics relied on (auto-vivifying new columns via
`.at[]`, reindexing to avoid row_id collisions, tolerating mismatched
columns via `reindex`+union).

**Known, documented limitation**: there is no "sync to PartsBox now" for
a Search-only-started working BOM -- PartsBox project/storage creation
still only happens as part of processing an uploaded file. This is
called out in the Operator Guide's "What NOT to do" list rather than
silently left undiscoverable. Building an on-demand PartsBox sync action
was judged out of scope for this pass (not part of the required test
list, and a genuinely new capability rather than composing existing
ones).

## 5. Cart/MyList creation removed from intake

The "Create Mouser cart" / "Create DigiKey MyList" checkboxes that used
to appear at Upload time are gone entirely. `render_upload_intake()`
always calls `run_bom_workflow(..., run_mouser_cart=False,
run_digikey_mylist=False)`. The only way to create either is still the
existing, unchanged **Regenerate Purchasing** button in Purchasing
Handoff.

## 6. BOM Configuration: build quantity re-apply

`_apply_build_quantity()` recomputes `required_qty` using the exact same
pure function (`bom_cleaner.apply_project_quantities()`) Upload's
initial processing uses, then writes each row's recomputed fields back
through `ActiveBomState.update_row()`. It deliberately **skips** rows
with no `qty_per_board` (i.e. added manually via Search, whose
`required_qty` was entered directly at Add time) so re-applying a build
quantity can never silently overwrite a manually-set quantity that
multiplier doesn't apply to.

## 7. A real bug found and fixed while wiring this up: `st.rerun()` position

While testing the merge flow, `results_search` (Results' search text
box) was observed resetting to `""` after clicking **Process Upload**,
even though nothing in the new code touches that key. Root cause: an
explicit `st.rerun()` call positioned *above* a keyed widget's first
render in page order aborts the script before that widget is
instantiated in that pass; Streamlit's widget-state bookkeeping treats
it as "not present this run" and the widget's session-state value is
lost when the automatic restart re-registers it fresh. This was
reproduced directly against `app.py` (not just a test artifact) via a
standalone repro script, both with directly-injected session state and
with a real simulated widget interaction.

This risk pre-dates this pass structurally (an earlier pass moved
Customer Reference from its own tab to a position before Results, where
its existing `st.rerun()` calls were *already* susceptible) but wasn't
exercised by any existing test until this pass's Search/Upload
intake-then-Process-Upload flow surfaced it. Fixed by removing
`st.rerun()` from the handlers positioned before Results in page order,
where it was unnecessary anyway (nothing rendered *above* those buttons
in the same pass depends on the mutation, so simply letting the script
continue to completion already shows the change on this same pass):
`render_add_to_bom_results()`'s Add to BOM button, `render_upload_intake()`'s
Process Upload button, `_render_customer_reference_preview_and_apply()`'s
Apply to All BOM Lines button, `_render_inventory_reference()`'s
per-line Save button, and `render_bom_configuration_section()`'s Apply
Build Quantity button. Two Customer Reference `st.rerun()` calls were
deliberately left as-is (Override Individual Lines' Save, and Add
Approved Project/PCB Code) because they refresh a widget that already
rendered *above* them in the same pass (the just-edited text box; the
Project/PCB dropdowns) and removing them would trade a display
correctness bug for a session-state-reset bug -- this narrow case
(editing a per-line Customer Reference override, or adding a new
approved code, while an unrelated Results filter is also set) is called
out as a known limitation rather than silently left broken or
over-engineered around.

## 8. What did not change

`ActiveBomState.rows()/review_items()/update_row()/summary_counts()`,
`review_actions.apply_replacement()/retry_exact_sourcing()`,
`sourcing_engine`, `run_bom_workflow()`, `regenerate_purchasing()`,
`build_purchasing_summary()`, the Customer Reference generator, the
inventory-location recommender, and PartsBox integration are all
unchanged. The purchasing side-effect boundary is unchanged: only an
explicit **Regenerate Purchasing** click can create a live Mouser cart
or DigiKey MyList -- confirmed by test (`test_no_vendor_artifact_created_by_search_or_upload`)
that adding parts via Search and processing an Upload never call
`create_mouser_cart_from_bom`/`create_digikey_mylist_from_bom`.

## 9. Tests

- `tests/test_active_bom_state.py`: new `AddRowTests` (4) and
  `AddRowsTests` (4) covering `add_row()`/`add_rows()` directly,
  including the empty-dataframe and column-enlargement/mismatch cases.
- `tests/test_workflow_runner_contract.py`: new `StartManualBomWorkflowTests`
  (4) covering `start_manual_bom_workflow()`'s response shape, schema
  compatibility with an uploaded run (for merging), distinct run IDs,
  and that it creates no output files.
- `tests/test_app_navigation.py`: new `UnifiedIntakeTests` (5) covering
  exactly the required section-12 scenarios: Search-add with no prior
  upload, Search-add after an upload, Upload after manual Search
  additions, Customer Reference configurable from BOM Configuration, and
  zero vendor-artifact calls from Search/Upload.
- `tests/test_app_smoke.py`: replaced the now-inapplicable
  `test_new_run_resets_run_scoped_session_state` (its premise -- a
  second upload always replaces the run -- is no longer true) with
  `test_first_upload_with_no_existing_run_creates_a_fresh_run` and
  `test_uploading_while_a_working_bom_exists_merges_instead_of_replacing`
  (the latter is also the regression test for the `st.rerun()` bug in
  §7 -- it asserts `results_search` survives the merge).

## 10. Test results

```
python -m py_compile app.py src/*.py tests/*.py   -> OK
python -m unittest discover -s tests -v           -> Ran 424 tests, OK
```

424 = the pre-existing 412 tests (392 baseline + 20 from the two prior
UI-architecture passes) minus 1 replaced test plus 13 net-new tests
across the four files above. Zero regressions.

## 11. Documentation

`Documentation/AutoBOM_Operator_Guide.md` reworked: "Run BOM" ->
"Add Parts" (Search + Upload, with the merge-vs-replace behavior spelled
out), new "BOM Configuration" section, "Component Search" folded into
Add Parts (no longer a separate section), and the PartsBox-sync
limitation from §4 added to "What NOT to do".

## 12. Stop condition

Per the request: no backend architecture was rebuilt -- `ActiveBomState`,
`run_bom_workflow()`, `apply_replacement()`, sourcing, PartsBox
integration, Customer Reference, artifact freshness, and Purchasing
Handoff are all reused unchanged. The two new `ActiveBomState` methods
and one new `workflow_runner` function are the only new backend surface,
and each is a small, directly-tested, single-purpose addition needed to
let Search and Upload write to the same canonical state. All tests pass.
Stopping here for operator click-through testing.
