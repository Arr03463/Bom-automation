# AutoBOM UI / PartsBox Architecture Correction Report

## 1. What this pass was

An information-architecture correction, not a rewrite or a feature pass.
Before this pass, `app.py`'s sidebar exposed four top-level pages ("Run
BOM", "Component Search", "PartsBox Inventory", "Purchasing"), which made
one continuous BOM workflow feel like four unrelated applications.
Per the request, top-level navigation is now exactly two destinations,
and the previous four "pages" are recomposed as stages/tabs of one
workflow.

## 2. New navigation

- **AutoBOM** (default page) -- one page, five tabs, all sharing the
  same `st.session_state.current_run` / `_active_bom_state`:
  1. Run BOM
  2. Results / Needs Review
  3. Component Search
  4. Customer Reference
  5. Purchasing Handoff
- **PartsBox Inventory** -- unchanged as a separate top-level page.

`st.tabs()` renders every tab's widgets on every script rerun regardless
of which tab is visually selected (verified empirically before this pass
began). Combined with Streamlit's session-state model (one shared dict
for the whole script execution), this means there is no server-side
"switch" between stages to get wrong -- the canonical BOM state is
simply the same object read/written by whichever tab's widgets the
operator happens to interact with.

## 3. Code changes (`app.py`)

No workflow logic was rewritten. Existing render functions were renamed
and recomposed; only two small structural changes were made beyond that:

- `render_run_bom_page()` -> `render_run_bom_section()`: unchanged
  upload/options/run logic; its old direct calls to
  `render_results_workspace()` and `render_downloads()` were removed
  (those now belong to their own stages) and replaced with a caption
  pointing to them.
- New `render_results_section()`: guard + `render_results_workspace()`
  call, extracted out of the old Run BOM page so Results/Needs Review is
  its own stage.
- `render_component_search_page()` -> `render_component_search_section()`:
  signature/name only; body untouched.
- `render_partsbox_inventory_page()`: unchanged as the top-level PartsBox
  Inventory page; its docstring/caption were corrected (see §4) to stop
  describing AutoBOM's PartsBox integration as read-only.
- New `render_customer_reference_tab()`: guard wrapper around the
  existing, unmodified `render_customer_reference_section()`.
- `render_purchasing_page()` -> `render_purchasing_handoff_section()`:
  the `render_customer_reference_section()` call (and its following
  divider) was removed from the top of this function, since Customer
  Reference is now its own tab -- everything else in the function
  (status derivation, per-supplier summary, Regenerate Purchasing,
  downloads) is unchanged.
- New `render_autobom_workflow_page()`: composes the five stages above
  into `st.tabs([...])`. This is the only new orchestration code in this
  pass.
- Bottom-of-file navigation: `st.sidebar.radio(...)` options changed from
  `["Run BOM", "Component Search", "PartsBox Inventory", "Purchasing"]`
  to `["AutoBOM", "PartsBox Inventory"]`, dispatching to
  `render_autobom_workflow_page()` / `render_partsbox_inventory_page()`.

Nothing in `src/` changed. `ActiveBomState`, artifact freshness,
supplier adapters, Customer Reference, the inventory-location
recommender, and PartsBox integration are all exactly as they were
before this pass.

## 4. PartsBox write-capability correction

Per the explicit clarification in the request, the PartsBox Inventory
page's docstring and on-screen caption previously read as though
AutoBOM's PartsBox integration were permanently read-only. Both were
rewritten to state the accurate distinction:

- This **browsing page** is read-only by design -- opening it,
  searching, or filtering never writes anything, and no button on it
  performs a write.
- AutoBOM's PartsBox integration as a whole is **not** read-only --
  confirmed, intentional writes (project/storage creation, BOM-entry
  sync) already exist and run as part of the Run BOM stage
  (`partsbox_project_builder.py`), gated behind an explicit **Run BOM
  Automation** click, never from merely viewing/searching/filtering.

The same correction was carried into `Documentation/AutoBOM_Operator_Guide.md`.

## 5. Documentation updated

`Documentation/AutoBOM_Operator_Guide.md`:
- Added a "Navigation" section describing the two top-level
  destinations and the five AutoBOM tabs.
- Corrected the PartsBox Inventory section per §4.
- Added a "Customer Reference" section (this had no operator-facing
  documentation before this pass, despite the feature already existing
  and being covered by tests -- added here since the navigation section
  now needs to describe all five tabs accurately).
- Renamed "Purchasing" -> "Purchasing Handoff" and its downloads-section
  heading, to match the tab names.

No screenshots exist in this repository to update. Other dated
completion reports under `Documentation/` describing prior phases were
left as historical records, not living documentation.

## 6. Tests

- Updated `tests/test_app_smoke.py` and `tests/test_customer_reference_ui.py`:
  removed `at.sidebar.radio[0].set_value("Component Search" / "Purchasing")`
  navigation calls -- both stages are now tabs rendered by the default
  "AutoBOM" page, so there is nothing left to navigate to. The
  `PartsBox Inventory` sidebar navigation (still a real top-level page)
  was left unchanged.
- Added `tests/test_app_navigation.py` (12 tests) covering exactly the
  properties named in the request:
  - Top-level navigation is exactly `["AutoBOM", "PartsBox Inventory"]`;
    "Run BOM"/"Component Search"/"Purchasing" are not top-level options.
  - The default AutoBOM page renders all five tabs in order.
  - Run BOM's upload widget, Component Search, Customer Reference, and
    Purchasing Handoff are all reachable without a separate top-level
    page.
  - Canonical BOM state (the same `_active_bom_state` object, and a
    row's data) survives repeated reruns of the same page.
  - PartsBox Inventory remains independently accessible as a top-level
    page.
  - "Browse All" queries `search_components()` with an empty
    MPN/keywords query scoped to `sources={"partsbox"}` -- i.e. the full
    accessible catalog, not a BOM-derived subset.
  - Opening PartsBox Inventory, clicking Browse All, and loading storage
    locations make zero calls to any of `PartsBoxClient`'s write
    operations (`project/create`, `storage/create`,
    `project/add-entries`).

Existing intentional PartsBox write workflows (project/storage/entry
creation during a BOM run) were not touched by this pass and continue to
be covered by the unchanged `tests/test_partsbox_lifecycle.py` suite.
Purchasing side-effect boundaries (Regenerate Purchasing is the only
action that can create a live cart/MyList) are unchanged and continue to
be covered by the unchanged `tests/test_purchasing_state.py` and
`PurchasingPageSmokeTests` suites.

## 7. Test results

```
python -m py_compile app.py src/*.py tests/*.py   -> OK
python -m unittest discover -s tests -v           -> Ran 404 tests, OK
```

404 = the pre-existing 392 tests (zero regressions, zero changes to
their assertions beyond the sidebar-navigation lines described in §6)
plus the 12 new tests in `tests/test_app_navigation.py`.

## 8. Stop condition

Per the request: the information architecture is fixed, all existing
capabilities (canonical `ActiveBomState`, Results Workspace, Needs
Review, shared Component Search, Customer Reference, smart inventory
recommendation, artifact freshness, PartsBox integration, supplier
adapters, explicit Regenerate Purchasing) are preserved and unmodified
in behavior, documentation is updated, and all tests pass. No unrelated
feature work was added. Stopping here -- the next step is the user's own
operator click-through testing of the restructured navigation.
