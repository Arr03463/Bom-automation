# AutoBOM UI Correction Report — Continuous Workspace, Not Tabs

## 1. What this pass corrects

The immediately preceding pass replaced four top-level pages with a
tabbed single page (`st.tabs(["1. Run BOM", ..., "5. Purchasing
Handoff"])`). Per this correction, tabs still separate functionality
that is supposed to work together as one continuous operator workspace.
This pass removes those tabs and recomposes the same five stages as
plain vertical sections on one page, in the order an operator actually
works through a BOM. Top-level navigation is unchanged: **AutoBOM** /
**PartsBox Inventory**.

## 2. New page composition (`render_autobom_workflow_page()`)

No `st.tabs()` at the top level anymore. Vertical order:

1. Run BOM (upload + configuration + run button + run messages)
2. Customer Reference (only once a BOM exists)
3. Working BOM / Results, including Needs Review (only once a BOM
   exists)
4. Search Components (an `st.expander`, always visible regardless of
   whether a BOM has been run -- it is a general-purpose tool
   independent of any specific run, not a workflow stage gated on Run
   BOM)
5. Purchasing Handoff (only once a BOM exists)

Sections 2, 3, and 5 are skipped entirely (not merely disabled) until
`current_run`/`_active_bom_state` exist, matching the operator's actual
flow: there is nothing to configure a Customer Reference for, or hand
off to purchasing, before a BOM has been uploaded and run.

The pre-existing nested "All Results" / "Needs Review (N)" tabs *inside*
the results table are unrelated to this correction and were left as-is
-- the request's objection was to top-level workflow-stage tabs, not
this inner split.

## 3. Customer Reference is part of BOM configuration, not purchasing prep

`render_customer_reference_section()` now sits directly after Run BOM
and before the results table (previously it lived inside the Purchasing
Handoff tab). Its docstring was updated to describe it as a
configuration step, not purchasing-only. No internal logic changed.

## 4. Customer Reference is now visible in the working BOM table

`RESULTS_DISPLAY_COLUMNS` (used by `render_results_table()`) gained a
`"customer_reference": "Customer Reference"` entry, positioned right
after Source, matching the requested `Part | MPN | Qty | Source |
Customer Reference | Status | Actions` shape. No other column or the
underlying data changed -- `ActiveBomState.to_records()` already
serialized this field; it just wasn't in the display allowlist before.

## 5. Inventory Customer Reference: per-part table, not one-at-a-time

`_render_inventory_reference()` was rewritten. Previously: pick one BOM
line from a dropdown, click "Get Recommendation", get one result, save.
Now: click **Get Recommendations for All Parts** once, and
`recommend_location()` (unchanged -- same PartsBox-ledger exact-match-
first, similarity-fallback recommender) is called once per BOM line;
results render as a table (Part / Match / Reason / Location / Save) the
operator can accept or override per row.

This is still explicit-trigger-only (never runs merely from selecting
"Inventory" as the reference type) -- it's one extra PartsBox read per
BOM line instead of one for a single row, so it stays behind a button
rather than firing automatically. It still only ever writes
`customer_reference` -- never a PartsBox stock/location mutation.

## 6. Mouser/DigiKey identifiers get a copy affordance

CartKey, DigiKey List ID, and (if the API ever returns one) DigiKey's
share identifier now render via `st.code(...)`, which Streamlit gives a
built-in copy-on-hover icon, instead of plain inline text. Nothing was
invented: the DigiKey share identifier still only shows the sanitized
"Not provided by the DigiKey MyLists API" message when absent, exactly
as before -- confirmed live that the API does not return one.

## 7. What did not change

- `ActiveBomState`, artifact freshness, supplier adapters, `PartsBoxClient`,
  `component_lookup`, `record_filter`, the Customer Reference generator,
  and the inventory-location recommender are all unchanged.
- The side-effect boundary is unchanged: only an explicit **Regenerate
  Purchasing** click can create a live Mouser cart or DigiKey MyList.
  Uploading, configuring, searching, changing Customer Reference (bulk
  or per-line), and getting inventory recommendations remain
  vendor-call-free actions on the purchasing side (inventory
  recommendations do call `PartsBoxClient` for reads, same as before,
  never PartsBox writes).
- PartsBox Inventory remains a separate top-level page, unchanged.
- Component Search's underlying implementation
  (`render_component_search_section()`) is untouched -- only where it's
  mounted (inside an expander on the main page instead of a tab) changed.

## 8. Tests

- `tests/test_app_navigation.py`: replaced the tab-composition tests
  with section-composition tests --
  `test_default_page_has_no_top_level_workflow_tabs` (asserts none of
  the five old tab labels exist, and that the only tabs anywhere are the
  pre-existing "Needs Review (N)" style tab),
  `test_component_search_is_embedded_and_visible_without_any_bom_run`,
  `test_customer_reference_column_is_visible_in_the_working_bom_table`,
  `test_sections_appear_top_to_bottom_in_workflow_order` (Customer
  Reference before Results before Purchasing Handoff), plus the
  pre-existing state-preservation and PartsBox Inventory tests updated
  for the new wording (renamed
  `test_switching_between_workflow_stages...` to
  `test_repeated_reruns_preserve_canonical_bom_state` since there is no
  longer anything to "switch" between).
- `tests/test_app_smoke.py`: `test_navigating_to_component_search_has_no_exceptions`
  now checks for the `"🔍 Search Components"` expander instead of a tab
  label.
- `tests/test_customer_reference_ui.py`: `test_inventory_recommendation_flow`
  rewritten for the bulk per-line flow -- asserts `recommend_location()`
  is called once per BOM line (not once total), and saves via that row's
  own `cref_inv_save_{row_id}` button instead of a single shared "Save
  Reference for This Line" button.

## 9. Test results

```
python -m py_compile app.py src/*.py tests/*.py   -> OK
python -m unittest discover -s tests -v           -> Ran 406 tests, OK
```

406 = the 404 tests from the immediately preceding (tabbed) pass, minus
the tab-specific assertions that were replaced, plus 2 net-new tests in
`test_app_navigation.py`. Zero regressions elsewhere.

## 10. Documentation

`Documentation/AutoBOM_Operator_Guide.md` reordered to match the actual
page flow (Navigation → Run BOM → Customer Reference → Results/Needs
Review → Component Search → Purchasing Handoff → Downloads → PartsBox
Inventory → What NOT to do), replacing the "five tabs" description with
"one continuous workspace," and documenting the new bulk inventory-
recommendation table and the CartKey/List ID copy affordance.

## 11. Stop condition

Per the request: no functionality was added beyond what was required to
correctly compose the existing system as one continuous workspace (the
per-line-table inventory-recommendation view and the `st.code()` copy
affordance are presentation changes over existing, reused functions —
`recommend_location()` and the already-computed CartKey/List ID/share-id
values — not new backend capability). All tests pass. Stopping here for
operator click-through testing.
