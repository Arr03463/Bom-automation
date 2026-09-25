# AutoBOM Front-Page Workflow Correction Report — Unified Parts Sourcer

## 1. What this pass corrects

The front page still modeled Search and Upload as if they had different
settings. Per the request, the whole top of AutoBOM is now one parts
sourcer: Search and Upload feed the same working BOM; one shared
Configuration section (not "Upload settings") governs the whole
sourcing job; the Sources checkboxes beside Search are authoritative for
both intake paths; redundant sourcing toggles are gone; and Mouser's
current-workflow output changed from an automatic cart to a downloadable
export.

## 2. Page composition

`render_autobom_workflow_page()` now composes, top to bottom:

1. **Add Parts** (`render_add_parts_section()`) -- Search (left) +
   Upload (right), unchanged in position from the prior pass.
2. **Configuration** (`render_configuration_section()`) -- now **always
   visible**, immediately below Add Parts, not gated behind a working
   BOM existing. This was a deliberate change from the prior pass's
   "BOM Configuration" (which only appeared once a working BOM existed):
   Upload's very first click needs build quantity/project name/PartsBox
   behavior before any working BOM exists yet, so Configuration has to
   be available from the start. Customer Reference remains nested
   inside, guarded on a working BOM actually existing (there's nothing
   to apply a reference to otherwise).
3. **Results / Needs Review**, **Purchasing Handoff** -- unchanged
   position, still gated on a working BOM existing.

## 3. Search stays the primary intake; Upload lost its own settings

`render_component_search_intake()`: unchanged search form, but the
Sources checkboxes (PartsBox/Mouser/DigiKey) now default to **all
three enabled** (previously Mouser/DigiKey defaulted off to avoid
incidental live-vendor calls from a default search). This is a
deliberate, requested trade-off: the request was explicit ("Default all
three to enabled unless there is an existing tested reason not to"),
and since these checkboxes are now also authoritative for sourcing
uploaded parts (see below), leaving Mouser/DigiKey off by default would
have silently broken "upload a BOM and get it sourced" as the default
experience. An operator who wants a cheap PartsBox-only search can still
uncheck Mouser/DigiKey first.

`render_upload_intake()`: the "Upload settings" expander (build
quantity, PartsBox project name/description, "Run PartsBox", "Run
supplier sourcing", "Use Mouser/DigiKey sourcing") is gone entirely.
Upload now has only the file dropzone and the Process Upload button.
Its handler reads build quantity / project name / project description /
"Update PartsBox Project" from the shared Configuration section's
`st.session_state` keys (`cfg_build_quantity`, `cfg_project_name`,
`cfg_project_description`, `cfg_update_partsbox_project`), and reads
which suppliers to source against directly from the Sources checkboxes
(`component_search_mouser`/`component_search_digikey`) -- there is no
second "use Mouser/DigiKey sourcing" toggle. `run_sourcing` is now
implicit: `use_mouser_sourcing or use_digikey_sourcing`, matching the
request's "the selected source checkboxes already tell AutoBOM where to
look" instruction directly, instead of a separate master switch.

This relies on Streamlit's ordinary widget/session-state behavior, not
new plumbing: `init_session_state()` seeds the four `cfg_*` keys with
defaults so they're readable even before Configuration has rendered a
single time (the very first upload in a fresh session), and Search's
column renders before Upload's in the same script pass, so its
checkboxes are always already set by the time Upload's handler reads
them.

## 4. Renamed fields, removed toggle, kept the write-vs-search PartsBox distinction

- "PartsBox project name" -> **Project Name** (operator doesn't need to
  know it's a backend PartsBox concept to name their job).
- "Run PartsBox" -> **Update PartsBox Project**, moved into
  Configuration, kept conceptually distinct from the PartsBox checkbox
  under Sources: the Sources checkbox only searches PartsBox (read-only,
  same as before); Update PartsBox Project is the one control that
  actually creates/reuses the PartsBox project + storage and adds BOM
  entries -- an intentional write, gated behind an explicit checkbox,
  never implied by merely searching.
- "Create Mouser cart" / "Create DigiKey MyList" -- already removed from
  intake in the prior pass; still not present here (Regenerate
  Purchasing remains the only trigger for either).

## 5. Mouser: cart automation replaced with a downloadable export

This is the one genuinely backend (not just UI-composition) change in
this pass. New `src/mouser_export.py` (`export_mouser_list()`) mirrors
`digikey_list_export.export_digikey_list()`'s exact pattern -- selects
`selected_supplier == "Mouser"` rows and writes a CSV, returning
`(path, count)`; produces an empty CSV rather than erroring when there's
nothing Mouser-sourced yet, same as the DigiKey exporter already does.

`workflow_runner.py` changes:

- `mouser_export_csv` joins `FILE_ARTIFACT_KEYS` (a plain, always
  re-exported file artifact, like `sourcing_report`/`digikey_list_csv`)
  -- `"mouser_cart"` is removed from `SUPPLIER_ARTIFACT_KEYS` entirely,
  since there's no vendor call left to protect with skip-if-current
  logic. `SUPPLIER_ARTIFACT_KEYS` now contains only `"digikey_mylist"`.
- `run_bom_workflow()` and `regenerate_purchasing()` no longer call
  `create_mouser_cart_from_bom()` at all (no `MOUSER_CART_ENABLED` check,
  no `run_mouser_cart` parameter -- removed from both signatures).
  Both now call `export_mouser_list()` unconditionally, in the same
  place the DigiKey list export already ran.
- `_extract_mouser_cart_key()` / `_build_mouser_purchasing()` deleted
  (no "cart created"/"CartKey" concept survives them).
  `build_purchasing_summary()`'s `"mouser"` sub-dict is now
  `{item_count, total_quantity, artifact_status}` -- no
  `cart_created`/`cart_key`/`required` fields.
- **`derive_purchasing_status()`'s "Ready for Handoff" gating now
  considers only DigiKey.** Mouser having sourced items never blocks or
  gates readiness -- it's just a file, exactly like a failed
  `sourcing_report` export already didn't block readiness before this
  pass. `"Partial — Generation Failed"` is consequently unreachable
  today (there's only one `SUPPLIER_ARTIFACT_KEYS` member left), but the
  branch is left in place since it's still generically correct if that
  list ever grows again -- not special-cased away.

`mouser_cart_client.py` (the Cart API client itself) is **completely
untouched** -- preserved per the request, for a possible future
supported Mouser sharing capability, just no longer invoked from the
normal app workflow. `src/main.py` (the separate CLI tool) still uses
it directly and is unaffected by any of this.

**Config-validation side effect found and fixed**: `collect_startup_warnings()`
(shown as an in-app banner) previously called `mouser_cart_config_status()`,
which would warn "MOUSER_CART_ENABLED is true, but required credentials
are missing" -- describing a code path the Streamlit app no longer
invokes at all. Removed that call from `collect_startup_warnings()` (the
function itself, and its own tests, are untouched/preserved for the CLI
path) so the app doesn't warn about a feature it doesn't use.

## 6. Purchasing Handoff UI

- **Mouser** column: "Cart created"/"CartKey" replaced with a **Download
  Mouser Export** button (reusing the existing `show_download()` helper,
  disabled when stale/failed like every other download) and a caption
  explaining the current manual-upload-to-Mouser workflow, that AutoBOM
  doesn't create a cart or place an order, and that the Cart API
  integration is preserved for a possible future capability.
- **DigiKey** column: unchanged (List ID + share identifier, both in
  copyable `st.code()` blocks, never inventing a share ID DigiKey
  doesn't return).
- `render_downloads()` (the bottom-of-page full outputs list) gained a
  `mouser_export_csv` entry alongside the existing file artifacts.
- The `Regenerate Purchasing` button's call site dropped
  `run_mouser_cart=True` (removed parameter).

## 7. What did not change

`ActiveBomState`, `apply_replacement()`/`retry_exact_sourcing()`,
sourcing engine, PartsBox integration, Customer Reference generator, the
inventory-location recommender, `digikey_mylists_client.py`, and the
merge-vs-replace Upload behavior from the prior pass are all unchanged.
The purchasing side-effect boundary is unchanged and, if anything,
narrower now: only DigiKey MyList creation is a live vendor call inside
`regenerate_purchasing()`; Mouser's export is a local file write with no
external effect at all.

## 8. Tests

- New `tests/test_mouser_export.py` (4 tests, mirrors
  `test_digikey_list_export.py`'s exact structure).
- `tests/test_purchasing_state.py`: substantially rewritten. Removed
  tests whose premise no longer holds (Mouser cart enable-flag gating,
  Mouser participating in "Partial — Generation Failed"); added
  `test_mouser_sourced_items_never_block_readiness`,
  `test_mouser_export_failure_does_not_block_ready_for_handoff_status`,
  `test_mouser_export_regeneration_records_failure_without_raising`,
  `test_mouser_export_reruns_on_every_regeneration_unlike_digikey`; kept
  and renamed the DigiKey-only versions of the retry/call-count tests
  (`test_retry_after_digikey_failure_does_not_recreate_it_once_current`,
  `test_one_explicit_regeneration_click_creates_digikey_mylist_at_most_once`).
- `tests/test_app_navigation.py` (`UnifiedIntakeTests`): added
  `test_configuration_section_is_shared_and_has_no_upload_specific_settings`,
  `test_project_name_field_is_operator_friendly_not_partsbox_labeled`,
  `test_source_checkboxes_control_upload_sourcing_too` (asserts
  unchecking Mouser under Sources actually turns off
  `use_mouser_sourcing` for an upload, via a mocked
  `workflow_runner.run_bom_workflow` call-kwargs inspection),
  `test_mouser_purchasing_handoff_exposes_downloadable_export`.
- `tests/test_workflow_runner_contract.py`,
  `tests/test_app_smoke.py`, `tests/test_customer_reference_ui.py`:
  updated call sites that passed the now-removed `run_mouser_cart`
  parameter, and patch targets that mocked
  `workflow_runner.create_mouser_cart_from_bom` (now unused).
- `tests/test_config_validation.py`: updated
  `test_multiple_problems_all_surface` to expect 2 startup warnings
  instead of 3, with a comment explaining `MOUSER_CART_ENABLED=true` is
  deliberately still set in that test to prove it produces no warning.

### A patch-target gotcha hit while writing the new AppTest

`patch("app.run_bom_workflow")` silently did nothing (the mock was
never invoked, no exception) in a new test. Root cause: nothing in this
test file ever does `import app` itself, so `mock.patch` triggers its
own fresh import of `app.py` as a side effect -- a different module
object than the one `streamlit.testing.v1.AppTest` executes internally.
Patching `workflow_runner.run_bom_workflow` instead works correctly,
because AppTest re-executes `app.py`'s top-level code (including its
`from workflow_runner import run_bom_workflow` statement) on every
`.run()`, picking up the patched attribute from the real, shared
`workflow_runner` module. Documented as a comment isn't added inline
(existing tests in this file already established the "patch at the
module that DEFINES a name" rule); this is a concrete instance of that
same rule catching `run_bom_workflow` specifically, worth remembering
for any future test that needs to mock it.

## 9. Test results

```
python -m py_compile app.py src/*.py tests/*.py   -> OK
python -m unittest discover -s tests -v           -> Ran 433 tests, OK
python src/deployment_preflight.py                -> PASS/WARN only (exit 0), no new FAILs
```

433 = the 424 tests from the immediately preceding pass, minus a handful
of retired Mouser-cart-specific tests, plus the new tests listed above.
Zero regressions elsewhere.

## 10. Documentation

`Documentation/AutoBOM_Operator_Guide.md`: "Add Parts" section rewritten
to describe Search/Upload/Sources as one parts sourcer; "BOM
Configuration" renamed "Configuration" and rewritten for the new
always-visible, shared-field design (Project Name, Project Description,
Update PartsBox Project); Purchasing Handoff's Mouser description
rewritten for the export workflow; a new "Not Required" purchasing
status bullet reflecting DigiKey-only readiness gating.

`.env.example`: added a comment on the `MOUSER_CART_ENABLED` block
clarifying it no longer affects the Streamlit app's normal workflow,
only the separate CLI tool.

## 11. Stop condition

Per the request: no unrelated features were added. The Mouser Cart API
client and CLI path are preserved, not deleted. Search and Upload share
one Configuration and one sourcing decision (the Sources checkboxes);
there is no `upload_settings`/`search_settings` duplication anywhere in
the code. All tests pass. Stopping here for operator testing.
