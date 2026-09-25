# AutoBOM Customer Reference + Smart Inventory Placement — Implementation Report

Scope: the final normal-workflow feature pass before operator click-through
testing. Extends the existing canonical BOM state, PartsBox integration,
supplier adapters, Results Workspace, artifact-freshness model, and
Purchasing Handoff to support Yank's real Customer Reference / Customer
Part Number naming convention (YT-SOP-00-01-A) on every ordered line item.
No new subsystem, no redesign. AutoBOM's boundary is unchanged: it still
never places, pays for, or submits an order.

## 1. Files changed

**New:**
- `config/customer_reference_registry.json` — the approved Project/PCB code registry (data, not code).
- `src/atomic_file.py` — shared atomic JSON write, extracted from `supplier_lookup_cache.py`.
- `src/customer_reference_registry.py` — registry load/validate/add.
- `src/customer_reference.py` — reference generation + validation (INV-/PRJ-/RND-).
- `src/inventory_location_recommender.py` — Inventory location recommendation engine.
- `tests/test_customer_reference.py`, `tests/test_customer_reference_registry.py`, `tests/test_inventory_location_recommender.py`, `tests/test_mouser_cart_client.py`, `tests/test_digikey_mylists_client.py`, `tests/test_sourcing_report.py`, `tests/test_customer_reference_ui.py`.

**Modified:**
- `src/supplier_lookup_cache.py` — delegates atomic JSON writes to `atomic_file.py` (no behavior change).
- `src/workflow_runner.py` — initializes the canonical `customer_reference` column when `ActiveBomState` is constructed.
- `src/mouser_cart_client.py` — `build_mouser_cart_items()` maps `customer_reference` → `CustomerPartNumber`; aggregation key changed to (part number, reference) so different references on the same part stay separate cart lines.
- `src/digikey_mylists_client.py` — `build_digikey_mylists_parts()` maps `customer_reference` → `CustomerReference` per part.
- `src/sourcing_report.py`, `src/digikey_list_export.py` — `customer_reference` added to their exported columns.
- `app.py` — new Customer Reference section on the Purchasing page.
- `tests/test_digikey_list_export.py`, `tests/test_workflow_runner_contract.py` — extended with Customer Reference coverage.

## 2. Canonical Customer Reference model

`customer_reference` is a real column on the canonical BOM `DataFrame`
`ActiveBomState` wraps — initialized to `""` for every row in
`run_bom_workflow()`, right where `ActiveBomState` is constructed. No
change was needed to `ActiveBomState` itself: `rows()`/`review_items()`/
`get_row()` already serialize every column generically
(`to_records()`), and `update_row()` already accepts any column name —
so `customer_reference` flows through the existing one shared mutation
seam exactly like every other canonical field (`selected_supplier`,
`sourcing_status`, ...). One field, vendor-independent; supplier adapters
translate it, never the canonical model.

## 3. Naming generator

`src/customer_reference.py`:
- `build_inventory_reference(location)` → `INV-<LOCATION>`
- `build_project_reference(project_code, pcb_codes)` → `PRJ-<PROJECT>-<PCB>[_<PCB>...]`, preserving the caller's PCB selection order (no invented ordering rule)
- `build_rnd_reference(project_code, owner)` → `RND-<PROJECT>-<OWNER>`
- `validate_customer_reference(value)` — shape/length only (uppercase, no spaces, allowed characters, recognized prefix, ≤30 characters). Never silently shortens or invents an abbreviation; a too-long value is returned as invalid with the original value intact, for the caller to show and let the operator fix.

Format/rules are stable and encode zero fixed project/PCB values — a
never-before-seen registry code round-trips through the generator with
no code change (proven by
`test_new_project_does_not_require_generator_changes`).

## 4. Registry implementation

`config/customer_reference_registry.json` — one plain, human-readable
JSON file (`{"projects": {...}, "pcb_codes": {...}}`), overridable via
`CUSTOMER_REFERENCE_REGISTRY_PATH`. `src/customer_reference_registry.py`:
- `load_registry()`/`get_projects()`/`get_pcb_codes()` — validate on load (code shape, non-empty descriptions); **raises `RegistryError` on anything malformed**, deliberately not the lenient "corrupt file → empty" pattern `SupplierLookupCache` uses for its cache — a corrupted approved-code registry must never silently read as "nothing is restricted" or "no approved codes exist."
- `add_project()`/`add_pcb_code()` — atomic write (`atomic_file.atomic_write_json()`), rejects invalid codes/descriptions/duplicates, never silently overwrites an existing entry.
- Adding a code is a config edit; no generator/supplier-adapter/sourcing-engine change is required (see §3).

## 5. DAB / BUZZ additions

Added to the initial approved PCB registry per instruction:
`"DAB": "Dual Active Bridge"`, `"BUZZ": "Bus Bar"`. Every other
SOP-approved PCB code (BOOST, AMP, TXCTR, MINI, TXTER, RXTER, REC, BUCK,
PDU, RXCTR, MISC) and project code (ARM, ALD, COL, SPAR, ATH, TBCA, SNAP,
MOM) is preserved unchanged.

## 6. R&D free-text owner

`build_rnd_reference()`'s `owner` argument is plain operator-typed text
(uppercased, trimmed), never drawn from a fixed registry — staff/owners
change over time and are not an "approved code" concept, per instruction.
The UI (`_render_rnd_reference()`) uses `st.text_input`, not a dropdown.

## 7. Project/PCB UI

`app.py`'s Purchasing page, new **Customer Reference** section
(`render_customer_reference_section()`), reference-type radio (Project /
PCB, Inventory, R&D):
- Project/PCB: registry-backed `selectbox` (Project) + `multiselect` (one
  or more PCB codes), live-generated preview, length/shape validation
  shown inline, **Apply to All BOM Lines** button (disabled while the
  preview is invalid).
- R&D: registry-backed Project `selectbox` + free-text Owner
  `text_input`, same preview/validate/apply pattern.
- **Override individual lines**: an expander listing every BOM row with
  its current reference and a per-row text input + Save button, so a
  mixed-use BOM (mostly one project, a couple of inventory-restock lines)
  never requires re-touching every line.
- **+ Add Approved Project or PCB Code**: a minimal expander form
  (Code + Description + Save) calling `add_project()`/`add_pcb_code()`
  directly — no admin/permissions system, per instruction ("if an in-app
  editor introduces unnecessary complexity, the simple shared registry is
  sufficient"). This is exactly that: the simple registry, with a thin
  optional UI convenience on top.

## 8. Inventory UI

Reference Type → Inventory: a `selectbox` of BOM lines (labelled with
MPN/manufacturer/current reference) → **Get Recommendation** →
`inventory_location_recommender.recommend_location()` is called (read-only,
no PartsBox write) → shows Recommended Location / Match / Reason → a
`selectbox` of real PartsBox storage locations (recommended one first) to
Accept or override → **Save Reference for This Line** writes
`INV-<chosen location>` to that one row only. Never auto-finalizes; the
operator always makes the actual choice.

## 9. Inventory recommendation logic

`src/inventory_location_recommender.py`, reusing
`component_lookup.search_components()`/`PartsBoxClient` — no second
PartsBox matching engine:

- **Priority 1 (Exact Part):** `PartsBoxClient.find_part_by_mpn_and_manufacturer()`
  for the exact Manufacturer+MPN. If found, sums the part's
  `part/stock` **transaction ledger** by `stock/storage-id`
  (`stock/quantity` is signed; a storage-id's net is its current holding)
  — this is the standard ledger interpretation, not a guess. Exactly one
  storage netting positive → confident **Exact Part** recommendation.
  Zero storages netting positive (fully depleted/relocated, or no ledger
  at all) → falls through to Priority 2/3 rather than guessing. Multiple
  storages simultaneously netting positive → still surfaces the
  highest-quantity one, but at a lower **Strong Similarity** tier so the
  operator double-checks, per instruction not to silently pick "the"
  answer when it's genuinely ambiguous.
- **Priority 2/3 (Similarity):** gathers a manufacturer-scoped (or
  browse-all, reusing `search_components()`'s existing empty-query
  support) candidate pool, then scores each candidate using whatever
  signal PartsBox actually has for it — structured `category`/`package`/
  `characteristics` when present, degrading to description-token overlap
  + manufacturer match when they aren't (confirmed live: this account's
  real PartsBox data has neither `category` nor `package` populated).
  Groups the winning tier's candidates by their own current storage
  (same ledger-summing logic) and recommends the majority location, or
  **Low Confidence** when candidates split with no clear majority, or
  **Manual Selection Required** when there's no usable signal at all.
- A transparent, rule-based scorer — not machine learning, per
  instruction.

## 10. Exact-part behavior

Tested explicitly (`tests/test_inventory_location_recommender.py`):
single positive-net storage → Exact Part; a ledger with a large positive
entry followed by enough negative entries to net negative at that
storage, plus a smaller genuinely-current balance elsewhere → correctly
recommends the SECOND (genuinely current) location, proving the
recommender never takes the first or last ledger entry blindly; multiple
simultaneously-positive storages → Strong Similarity with the
highest-quantity one, not a blind first-match.

## 11. Similarity behavior

Tested: structured category+package match → Strong Similarity;
description+manufacturer-only overlap (this account's real-data
scenario) still reaches Strong/Similar Family, not a dead end; candidates
split across unrelated locations with no majority → Low Confidence; no
usable signal at all → Manual Selection Required, never a fabricated
guess.

## 12. Manual override behavior

Every recommendation path (Project/PCB, R&D, Inventory) ends in an
operator-controlled Apply/Save action — nothing is written to canonical
state automatically. The Inventory flow's storage-location selector
defaults to the recommendation but is a full `selectbox` over real
PartsBox storage locations, so choosing a different one is a first-class,
equally-easy action, not a hidden escape hatch.

## 13. PartsBox reuse

No second PartsBox client, matching engine, or parsing path was created.
`recommend_location()` calls `PartsBoxClient.find_part_by_mpn_and_manufacturer()`
and `component_lookup.search_components()` — the exact same functions
Component Search, Find Replacement, and PartsBox Inventory already use.
`list_storage_locations()` (already used by PartsBox Inventory's Storage
Locations view) is reused for the Inventory UI's location selector.

## 14. Mouser mapping

`build_mouser_cart_items()` maps `customer_reference` → the Cart API's
per-item `CustomerPartNumber` field. **Confirmed via Mouser's official
Cart API schema** (`CartItemRequest.CustomerPartNumber`, optional string)
and **live** (2026-09-25, one disposable test cart line): sending it
produced zero `Errors`, and Mouser's response echoed the value back under
`CartItemCustPartNumber` (a differently-named response field; not
currently read by this codebase, which only extracts `CartKey`). The
aggregation key `build_mouser_cart_items()` groups by changed from plain
`MouserPartNumber` to `(MouserPartNumber, customer_reference)`, so two
BOM rows for the same Mouser part but different references (e.g. one
project line, one inventory-restock line) become two separate cart
lines, each carrying its own reference, instead of silently merging and
dropping one.

## 15. DigiKey mapping

`build_digikey_mylists_parts()` maps `customer_reference` → the MyLists
`AddPartsToListId` request's per-part `CustomerReference` field.
**Confirmed via DigiKey's official MyLists v1 OpenAPI spec**
(`RequestedPart.CustomerReference`, optional string) and **live**
(2026-09-26, one disposable test MyList): sending it was accepted with no
error. This client has no "get list contents" endpoint to read the value
back and confirm storage directly (unlike Mouser's cart, whose response
did echo it), so that last confirmation step rests on the official schema
rather than an observed echo — documented plainly in code, not glossed
over. DigiKey MyList parts were never aggregated by part number (each BOM
row is already its own entry), so no merge-key change was needed to keep
references per-line.

## 16. Export mapping

`customer_reference` added to `sourcing_report.py`'s `SOURCING_COLUMNS`
and `digikey_list_export.py`'s `DIGIKEY_COLUMNS` (both already use an
"only include columns actually present" pattern, so this is
backward-compatible with any BOM state that somehow lacks the column).
The cleaned BOM CSV/workbook already export every column, so
`customer_reference` appears there with zero code change.
`export_partsbox_import_csv()` was deliberately left unchanged — the
feature spec's Supplier Exports section names Mouser/DigiKey exports
specifically, and the PartsBox import CSV is a different (PartsBox
project-entry) handoff, not a purchasing/supplier order artifact.

## 17. Artifact-staleness behavior

No new staleness mechanism was built. Every Customer Reference mutation
path (Apply to All, per-line override, Inventory Save) calls
`active_bom_state.update_row()` followed by
`workflow_runner.refresh_response_snapshot()` — the exact same shared
mutation seam Retry Exact Part/Find Replacement already use. That
function already marks every `STATUS_CURRENT` regeneratable artifact
(including `mouser_cart`/`digikey_mylist`) `STATUS_STALE` and recomputes
the derived `stale_after_mutation` flag (Phase 4 pass). Changing a
Customer Reference after purchasing artifacts were generated therefore
makes them stale automatically, requiring the existing explicit
**Regenerate Purchasing** action — proven by
`test_editing_reference_marks_purchasing_stale`. Editing a reference
itself makes zero vendor-side calls
(`test_assigning_reference_creates_no_vendor_calls` patches
`create_mouser_cart_from_bom`/`create_digikey_mylist_from_bom` and
asserts neither is called).

## 18. Documentation updates

- This report.
- The Yank naming-convention SOP (`YT-SOP-00-01-A`) itself was **not**
  modified — it is not maintained in this repository, per instruction.
  Recommended future wording (not applied anywhere): *"The listed
  Project and PCB codes represent the currently approved registry. New
  approved codes may be added while preserving the Customer Reference
  format and naming rules."*
- `config/customer_reference_registry.json` is the maintained,
  expandable registry; the format/rules in `customer_reference.py` are
  the stable part. This distinction is stated directly in
  `customer_reference_registry.py`'s module docstring and in the UI's
  "+ Add Approved..." caption.

## 19. Tests/results

```
python -m unittest discover -s tests -v
Ran 373 tests in 17.696s
OK

python -m py_compile app.py src/*.py tests/*.py
(clean, no output)
```

Net new this pass: 71 tests (302 → 373) across
`test_customer_reference.py` (18), `test_customer_reference_registry.py`
(19), `test_inventory_location_recommender.py` (11),
`test_mouser_cart_client.py` (5), `test_digikey_mylists_client.py` (4),
`test_customer_reference_ui.py` (10), plus additions to
`test_sourcing_report.py` (2, new file), `test_digikey_list_export.py`
(+1), `test_workflow_runner_contract.py` (+1). No existing test was
deleted or weakened.

Naming-engine tests cover every example from the spec (`INV-A1`,
`PRJ-ARM-RXCTR`, `PRJ-ATH-DAB`, `PRJ-ATH-BUZZ`, `PRJ-ATH-DAB_BUZZ`,
`RND-ARM-AARON`), uppercase normalization, space rejection, underscore-
only-for-multi-PCB, the 30-character limit (both at-limit-valid and
over-limit-invalid, never truncated), invalid/missing values, and registry
additions requiring zero generator changes. Per-line/bulk tests cover
apply-to-all, single-line override, R&D free-text owner, multi-PCB
selection, per-line Inventory references, staleness-on-edit, and
zero-vendor-calls-on-edit. Inventory recommendation tests cover exact
match, similar-family match, ambiguous/split-location, insufficient-data,
manual override, and the PartsBox ledger safety property explicitly
(never take the first/last ledger entry blindly). Supplier-mapping tests
prove `customer_reference` reaches both the Mouser cart payload and the
DigiKey MyList payload, per-line, without being overwritten by sourcing.

## 20. Live vendor verification completed

- Mouser Cart API `CustomerPartNumber`: official schema + live disposable
  cart line, response echo confirmed (§14).
- DigiKey MyLists API `CustomerReference`: official OpenAPI schema + live
  disposable test MyList, accepted with no error (§15).
- PartsBox `part/stock` ledger semantics (signed transactions, sum by
  storage-id): already confirmed live in the prior predeployment pass,
  reused here as the basis for the recommender's Priority 1 logic.

## 21. Live vendor verification still pending

- Whether DigiKey's MyLists API actually **persists and later exposes**
  `CustomerReference` on a subsequent read -- this client has no "get
  list contents" endpoint, so only the accept-without-error behavior was
  confirmed, not a round-trip read-back.
- Real-world quality of the Inventory recommendation engine against the
  full, real Yank PartsBox catalog with actual mixed BOMs -- only tested
  against synthetic fixtures here, since exercising it broadly against
  live data risks the same kind of unintentional full-record exposure
  flagged in the predeployment pass; this is exactly the kind of thing
  operator click-through testing (§37) is for.

## 22. Limitations requiring operator click-through

- The per-line override list renders one row of widgets per BOM line
  (matching the existing Needs Review UI's own pattern) -- untested at
  real-world BOM sizes for perceived responsiveness.
- The Inventory recommendation confidence tiers (Strong Similarity vs.
  Similar Family) are a first, transparent rule-based cut; whether the
  thresholds "feel right" against Yank's actual inventory patterns can
  only be judged by using it.
- Two disposable test carts/MyLists/PartsBox artifacts from this and the
  prior predeployment pass remain in real vendor accounts (not deleted,
  per standing instruction not to test delete behavior).

Full test suite passes (373/373); compile checks clean. Per the stop
condition, this pass ends here -- the next phase is Aaron running AutoBOM
himself and identifying real operator-workflow issues, not further
unrelated AutoBOM expansion.
