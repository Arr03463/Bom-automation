# AutoBOM Search / Filter / Inventory Implementation Report

Implements the architecture audit's four preconditions and the accompanying
36-section implementation prompt/mockup, in the order the prompt specified
(pagination → PartsBox snapshot → ledger aggregation → location
classification → source-selection model → filters/facets → Streamlit
upgrade → Enter-event adapter → main live Search → compact responsive
tables → automatic Upload → PartsBox Inventory → Needs Review reuse →
Customer Reference/config integration → UI styling → Yank/Arro badges →
regression testing).

## Files changed

New:
- `src/pagination.py` -- shared 20/page paginator (`paginate`, `clamp_page`,
  `total_pages_for`, `result_signature`).
- `src/storage_space_classifier.py` + `config/storage_space_rules.json` --
  Development / Project / Mechanical / Other classification.
- `src/partsbox_inventory.py` -- the shared PartsBox inventory snapshot:
  join of `part/all` + `storage/all` + `project/all`, signed-ledger
  netting, storage classification, process-wide TTL cache.
- `src/search_events.py` -- the minimal Custom Components v2 Enter-event
  adapter (`search_event_input`).
- `tests/_apptest_helpers.py`, `tests/test_pagination.py`,
  `tests/test_partsbox_inventory.py`, `tests/test_storage_space_classifier.py`,
  `tests/test_search_events.py`.
- `assets/yank_mark.png`, `assets/arro_mark.png` -- processed ownership
  marks (see "Badge implementation" below).

Modified:
- `app.py` -- Main Search, Upload, PartsBox Inventory, and Needs Review's
  replacement lookup all rewritten; new shared helpers
  (`_pagination_controls`, `_render_paginated_table`,
  `_membership_facet_filters`, `_authoritative_sources`,
  `render_selected_part_details`); header/badges.
- `src/record_filter.py` -- membership-filter kind + list-valued facet
  flattening.
- `src/inventory_location_recommender.py` -- Development-over-Project
  preference fix.
- `src/review_actions.py` -- `sources` parameter threaded through
  `retry_exact_sourcing`/`apply_replacement`.
- `requirements.txt`, `requirements-lock.txt` -- Streamlit 1.62.0 → 1.64.0.
- `tests/test_app_smoke.py`, `tests/test_app_navigation.py`,
  `tests/test_customer_reference_ui.py`, `tests/test_record_filter.py`,
  `tests/test_inventory_location_recommender.py`, `tests/test_review_actions.py`
  -- updated for the new UI/behavior, plus new coverage.

## Streamlit upgrade

1.62.0 → 1.64.0 (confirmed available via `pip index versions`, installed,
full 433-test baseline re-run with zero regressions before any further
code changes). Needed for `st.components.v2.component` (Custom Components
v2, used by `search_events.py`) and the native `live=` text-input
parameter's debounce semantics were evaluated but NOT used directly --
see "Search events" below for why a purpose-built component was still
necessary.

## PartsBox snapshot, TTL, and cache behavior

`partsbox_inventory.build_partsbox_inventory_snapshot()` fetches
`storage/all`, `project/all`, and `part/all` exactly once each, classifies
every storage location (`storage_space_classifier.classify_storage`), nets
each part's signed stock ledger per storage-id
(`net_quantities_by_storage` -- positive-only current balances), and joins
all of it into `InventoryPart` records with a `locations` list (never
collapsed to one field -- a part can be simultaneously in Development
storage and one or more Projects).

`get_snapshot(ttl_seconds=300)` is a process-wide cache (module-level dict
+ lock, deliberately not `st.cache_data` inside `PartsBoxClient`): serves
the cached snapshot while fresh, fetches once when cold/expired/forced,
and re-serves the last-good snapshot on a failed refresh rather than
blanking Search/Inventory during a transient PartsBox outage.
`invalidate()` drops the cache without fetching; called after Upload runs
with "Update PartsBox Project" on, since that write can change the joined
view. `refresh(force_refresh=True)` is exposed as an explicit "Refresh
PartsBox data" button on the Inventory page. 22 tests in
`tests/test_partsbox_inventory.py` cover the join, multi-location parts,
classification, ledger netting, `to_dict()`'s flat shape, and every cache
transition (TTL reuse/expiry, force refresh, generation increment,
invalidate, peek-without-fetch, failed-refresh-serves-stale,
refresh-raises-without-touching-cache).

## Source-selection model

The Sources checkboxes beside Search (`component_search_partsbox/_mouser/_digikey`)
are the one authoritative selection, read via `_authoritative_sources()`
in `app.py` and threaded as `sources=` into every seam that can query a
supplier: Main Search's Enter-triggered query, Upload's
`use_mouser_sourcing`/`use_digikey_sourcing`, Add to BOM
(`_add_search_result_to_working_bom` → `apply_replacement`), Retry Exact,
and Find Replacement/Check PartsBox. `review_actions._lookup_functions()`
substitutes a no-op `lambda row: None` for any unselected supplier -- the
same pattern `run_bom_workflow()` already used for
`use_mouser_sourcing=False`. `tests/test_review_actions.py`'s
`SourceSelectionGatingTests` (5 tests) confirm an unselected supplier is
never called via either function, and that `sources=None` stays backward
compatible (both enabled).

## Search events (the Enter-vs-typing boundary)

`search_events.search_event_input()` is a from-scratch Custom Components
v2 component (`st.components.v2.component`, inline HTML/CSS/JS -- no
build step, no legacy v1 `declare_component`/postMessage protocol). Its
JS debounces `oninput` (default 350ms) into `setStateValue("value", ...)`
for live PartsBox filtering, and on Enter clears the pending debounce and
fires both `setStateValue("value", ...)` and a one-shot
`setTriggerValue("submitted", ...)`. Python reads `.value` every render
and `.submitted` only on the one render where it's non-None.

**Verification limitation, disclosed explicitly**: `streamlit.testing.v1.AppTest`
does not execute a custom component's frontend JS (confirmed directly
against Streamlit's own bundled testing docs and by observation -- no
error, but no JS side effects either). `tests/test_search_events.py`
verifies everything that CAN be verified without a browser: the component
mounts with zero exceptions, `.value` defaults to the seeded value (not
`None`) before any real interaction, and `.submitted` is `None` on
initial mount. **The actual debounce timing and Enter-vs-typing
distinction have not been verified in a real browser from this
environment** (no browser-automation tool was available) and need a
manual operator check: type into the Main Search box and confirm PartsBox
results update after you stop typing, and that Mouser/DigiKey are not
queried until you press Enter.

## Main Search (live PartsBox, Enter-only suppliers, pagination)

`render_component_search_intake()`: PartsBox side filters the shared
snapshot locally via `record_filter.search_and_filter()` as `.value`
changes -- no PartsBox network call per keystroke once the snapshot is
warm. **Blank-startup guard**: the snapshot fetch itself is gated behind
`bool(live_text.strip()) or peek_snapshot() is not None` -- a completely
cold app with an empty search box does not fetch the full catalog just
because the section rendered; the first keystroke (or an already-warm
cache from a prior PartsBox Inventory visit) triggers it. Mouser/DigiKey
are queried only when `.submitted is not None` (a real Enter press),
written into `component_search_supplier_results`; typing, filter changes,
pagination, and row selection never touch that key.

Source-responsive width: PartsBox-only and suppliers-only each render
full-width via `_render_paginated_table`; PartsBox+suppliers render as two
`st.columns(2)` panels, the supplier side showing Mouser+DigiKey combined
in one table (`Source` column) rather than separate tabs.

Filters: `render_dynamic_facet_filters()` (existing, reused) for
categorical/range facets, plus new `_membership_facet_filters()` for
PartsBox-only Storage Space / Location / Project multiselects (a part can
be in several at once).

Pagination: `_render_paginated_table()` (20/page, `src/pagination.py`)
wraps a `st.dataframe(..., on_select="rerun", selection_mode="single-row")`
scoped to the current page's rows only (filter-before-paginate). The page
number resets to 1 via `_pagination_controls()`'s
`pagination.result_signature(...)` comparison whenever the query text,
filters, source selection, or snapshot generation changes -- but not on
quantity or row-selection changes, since none of those feed the
signature.

Selection from either table (or Needs Review's replacement table, or
PartsBox Inventory) populates `render_selected_part_details()`, the one
shared quantity-stepper + "Add to BOM" panel -- there is no per-row
quantity input or Add button anywhere anymore.

**Known simplification vs. the mockup**: filters render inline within
the Search section (stacked rows), not as a persistent left-hand
"Filters" rail with a "Filters (N)" popover button and "Clear all" -- the
underlying filter/facet logic matches the mockup's intent (Stock,
Manufacturer, Storage Space, Location, Category, Package, and range
facets including value/tolerance-style fields are all present and
functional), but the exact rail layout was not reproduced pixel-for-pixel
given the scope of this pass.

## Upload (automatic processing)

`render_upload_intake()` no longer has a "Process Upload" button.
Processing is keyed off Streamlit's own stable per-upload
`UploadedFile.file_id` (changes on a new file selection, even a same-named
re-drop; stable across unrelated reruns of the same file) stored in
`upload_intake_processed_file_id` -- a file is processed exactly once,
never reprocessed on an unrelated rerun. Sourcing uses
`_authoritative_sources()` (no separate upload-specific toggle). If
"Update PartsBox Project" was on, `partsbox_inventory.invalidate()` runs
immediately after, so Search/Inventory don't keep serving a pre-write
snapshot for up to 5 minutes.

## PartsBox Inventory

Lazy-loads the complete shared snapshot as soon as the page renders (no
Browse-All click) via the same `get_snapshot()`/`_render_paginated_table()`/
`_membership_facet_filters()` machinery Main Search uses -- not a second
PartsBox browse implementation. Empty search text shows every part. A
header caption shows part/storage counts and snapshot age; a "Refresh
PartsBox data" button forces `get_snapshot(force_refresh=True)`. Its own
Selected Part Details variant (`render_inventory_selected_part_details()`)
shows the full location breakdown but has no quantity/Add-to-BOM control,
since this page is read-only by design (unchanged from the prior pass;
Storage Locations sub-section and its own write-boundary caption are
untouched).

## Storage-space classification and the stock ledger

`storage_space_classifier.classify_storage()` applies the ONE confirmed
live PartsBox convention (production tag + same-name project/storage →
Project) first, then configured `mechanical_tags`/`development_tags` from
`config/storage_space_rules.json` (both start empty -- no tag is
confirmed live beyond the Project rule, so nothing is fabricated), then
falls back to `default_classification` ("Development", since most
ordinary storage is general Development stock). `net_quantities_by_storage()`
(moved to `partsbox_inventory.py`, imported back into
`inventory_location_recommender.py`) is the single signed-ledger netting
implementation shared by Inventory display, Main Search's PartsBox
enrichment, and the recommender -- summed per storage-id, only positive
totals kept.

## Inventory location recommendation fix

`inventory_location_recommender.py`'s exact-part and similarity paths now
partition candidate storages by Development-vs-not *before* ranking by
quantity/frequency. A Development location, even with less quantity, wins
over Project storage; Project/Mechanical/Other-only evidence is capped at
`CONFIDENCE_LOW` (never `CONFIDENCE_EXACT_PART`/`CONFIDENCE_STRONG_SIMILARITY`),
so the UI never silently claims exact-part confidence for a
Project-only match. `tests/test_inventory_location_recommender.py`'s new
`DevelopmentVsProjectPreferenceTests` (4 tests) cover the worked example
from the audit (Development C1=10 beats Project DAB=100) plus the
low-confidence-when-Project-only and prefer-Development-in-similarity
cases. All 11 pre-existing tests pass unchanged.

## Needs Review reuse

`render_needs_review()`/`render_replacement_lookup()` are otherwise
unchanged in structure (per-row expander, Retry Exact / Find Replacement /
Check PartsBox), but the replacement-candidate list now renders through
the same `_render_paginated_table()` (namespaced `replacement_{row_id}`,
so each open row keeps independent page/selection state) plus a "Use
Selected Replacement" button reading the selected row, replacing the old
per-candidate "Select" button. **Check PartsBox now filters the shared
snapshot** (`get_snapshot()`) instead of calling
`component_lookup.search_components(sources={"partsbox"})` -- this was a
real gap found and fixed during this pass (the audit's "one shared
PartsBox snapshot" precondition applies to Needs Review too, not just
Main Search); covered by
`test_check_partsbox_search_uses_the_shared_snapshot_not_a_live_search`.
Find Replacement (Mouser/DigiKey) is unchanged: still an explicit-button,
live `search_components()` call -- there's no snapshot for live supplier
data, and this box was never a live-as-you-type field, so it isn't
subject to the Enter-vs-typing boundary Main Search has.

## Customer Reference / Configuration

Unchanged from the prior pass (exact INV-/PRJ-/RND- generation, DAB/BUZZ
registry codes, "Project Name" field, "Update PartsBox Project" checkbox)
-- the mockup's Configuration card layout is a visual reference only, not
a request to alter the generator, and none of this pass's changes touch
`customer_reference.py`/`customer_reference_registry.py`.

## Purchasing / read-write boundaries

Unchanged and re-verified: `PurchasingPageSmokeTests` (regeneration only
on explicit click, never from a bare rerun) and the Customer Reference
vendor-call tests all still pass. No code path added in this pass creates
a Mouser cart, DigiKey MyList, or PartsBox write outside the existing
"Update PartsBox Project" (Upload) and "Regenerate Purchasing" actions.
PartsBox Inventory remains read-only by construction (snapshot reads
only); `test_opening_and_browsing_partsbox_inventory_performs_zero_write_calls`
confirms no `project/create`/`storage/create`/`project/add-entries` call
happens from loading the page or loading storage locations.

## Badge implementation

`assets/yank_mark.png` and `assets/arro_mark.png` are cropped directly
from the two supplied wordmark images (`1.jpg`/Yank, `3.png`/Arro) --
just the icon glyph, with the "YANKTECH"/"ARRO" text cropped away
entirely, not redrawn. Processed to replace near-white background pixels
with transparency and render the remaining linework at ~60% opacity in a
single dark slate tone (`#1e293b`-family), i.e. small, semi-transparent,
monochrome, symbol-only -- no brand text anywhere near them. Rendered at
28px width in the app header's upper-right, beside the "AutoBOM / Parts
Sourcing · Inventory · BOM Management" title/subtitle
(`render_app_header()`).

## Mockup alignment (styling)

Background/text/accent colors come from `.streamlit/config.toml`'s new
`[theme]` block (`base="light"`, blue `primaryColor`, white/soft-blue
`backgroundColor`/`secondaryBackgroundColor`, navy `textColor`) -- native
Streamlit theming, not CSS fighting generated DOM class names, per the
instruction to avoid brittle selectors. **This file is gitignored in this
repo** (pre-existing, unrelated to this pass -- see the file's own header
comment) and was already the deployment convention: copy it to
`<production checkout>\.streamlit\config.toml` per
`Documentation/AutoBOM_Deployment_Guide.md`. This pass's `[theme]`
addition needs that same manual copy to reach a production checkout; it
will not appear from a plain `git pull`. Two small CSS rules (in
`app.py`'s `_HEADER_CSS`) style the title/subtitle text, since
`st.title()` has no size variant matching the mockup. No React
rebuild; native Streamlit components + this minimal CSS only.

**Not attempted in this pass**: pixel-level reproduction of the mockup's
card borders/spacing, the left Filters rail (see "Main Search" above),
and verification across the 1920×1080 / 1440×900 / 1366×768 breakpoints
in a real browser (no browser-automation tool was available in this
environment -- Streamlit's own responsive `st.columns` behavior is relied
on, not explicitly tuned or tested at those widths).

## Performance safeguards

Shared snapshot with 5-minute TTL and process-wide cache (not per-session);
explicit refresh/invalidate; 350ms debounce on live PartsBox typing;
Mouser/DigiKey queried only on Enter; 20-result pagination everywhere;
`result_signature()`-gated page resets so unrelated reruns (quantity,
selection) don't recompute pagination; blank-startup guard so opening the
app doesn't fetch the full PartsBox catalog before the operator does
anything.

## Test results

`python -m py_compile app.py src/*.py tests/*.py` -- clean.
`python -m unittest discover -s tests` -- **509 tests, all passing**
(baseline 433 → 496 after the backend-primitives phase → 509 after the
app.py wiring, UI test rewrites, and the Check-PartsBox-snapshot fix's
regression test). New coverage added this pass: `test_pagination.py` (20),
`test_storage_space_classifier.py` (12), `test_partsbox_inventory.py`
(22, including `InventoryPartToDictTests`), `test_search_events.py` (4),
plus additions to `test_record_filter.py` (+8), `test_inventory_location_recommender.py`
(+4), `test_review_actions.py` (+5), and `test_app_smoke.py` (+1, the
Check PartsBox snapshot regression).

`tests/test_app_smoke.py`, `tests/test_app_navigation.py`, and
`tests/test_customer_reference_ui.py` were updated (not just left broken)
wherever the rewritten UI changed a button label, removed a button
("Process Upload", per-row "Select"/"Add to BOM"), or replaced a plain
`st.text_input` with the custom search component -- every rewritten
assertion still exercises real app.py code paths, using the same
"inject the post-interaction state directly" pattern the suite already
used for `replacement_results_{row_id}` wherever AppTest cannot itself
drive the interaction (custom-component JS, `st.dataframe` row
selection -- both documented as AppTest limitations in Streamlit's own
testing guide, not something specific to this codebase).

A registration issue surfaced and was fixed as part of this pass, purely
in the test suite: `streamlit.testing.v1.AppTest` runs without a real
Streamlit `Runtime`, so `st.components.v2`'s component registry is a
fresh, empty instance per `AppTest` object rather than the shared
singleton a real deployment has -- meaning a second, independently
created `AppTest.from_file("app.py")` in the same test process would
raise "Component ... is not registered" once `search_events` was already
imported by an earlier test. `tests/_apptest_helpers.fresh_app_test()`
resets `sys.modules["search_events"]` (forcing re-registration) and the
process-wide PartsBox snapshot cache before constructing each `AppTest`;
confirmed via direct reproduction that this is an AppTest/bare-mode
artifact only -- a real `streamlit run` process has exactly one
`Runtime`, so every session/rerun shares the same registry the component
registered against on first import, unaffected by this.

The app was also started directly (`streamlit run app.py`) and confirmed
to serve HTTP 200 with a clean startup log; this is not a substitute for
an operator clicking through the UI in a real browser.

## Remaining operator-test issues (please verify these manually)

1. **Live PartsBox search and the Enter boundary** (see "Search events"
   above) -- type into Main Search and confirm PartsBox results update
   after typing stops (not while typing continues), and that Mouser/
   DigiKey are only queried after pressing Enter, never from typing
   alone.
2. **Row selection** -- click a row in any results table (Main Search,
   PartsBox Inventory, Needs Review's replacement list) and confirm the
   Selected Part Details panel updates; this also could not be exercised
   by AppTest.
3. **Responsive layout** at 1920×1080 (primary), 1440×900, and 1366×768 --
   confirm the two-panel Search layout and filters remain usable, not
   just "present," at the smaller widths.
4. **Badge rendering** -- confirm the two marks in the header read as
   subtle/intentional at actual screen size, not distracting or
   mistakable for a clickable button; adjust the 28px width in
   `render_app_header()` if it reads too large or too small in practice.
5. **Theme rollout** -- copy the updated `.streamlit/config.toml`'s
   `[theme]` block to the production checkout per the file's own
   deployment note; it will not arrive via `git pull`.
6. **Live snapshot correctness against the real ~3,450-part catalog** --
   this pass's snapshot/classification/ledger logic is fully unit-tested
   against fakes, but has not been re-verified against a live PartsBox
   pull in this session (the original architecture audit's live
   verification predates this pass).

Per the original instruction, this stops here -- no unrelated AutoBOM
functionality was added. The application is ready for operator testing.
