# AutoBOM Per-Line Customer Part Number Audit

**Repository:** `Arr03463/Bom-automation`  
**Branch reviewed:** `team_release`  
**Audit date:** 2026-09-28  
**Mode:** Audit only; no application code is implemented by this report  
**Requested outcome:** An operator can assign a specific Customer Part Number (CPN) to particular parts in the Working Parts List. Different parts, including separate uses of the same manufacturer part, may have different CPNs because they serve different projects, inventory locations, or purposes.

## 1. Executive conclusion

AutoBOM already stores `customer_reference` on each canonical working-BOM row and offers two per-row editing surfaces. That is a useful foundation, but it does not fully satisfy the requested CPN behavior.

The main blockers are:

1. Duplicate manufacturer parts are consolidated before the operator assigns CPNs. Several designators can become one row, making different CPNs for those uses impossible.
2. The inline Working Parts List editor writes unvalidated text directly into canonical state.
3. The Configuration summary shows only the first row's value and can falsely imply that a mixed-CPN BOM has one common CPN.
4. **Apply to All** overwrites existing per-line assignments without protecting intentional exceptions.
5. The code and UI conflate the business term **Customer Part Number** with the supplier field **Customer Reference**.
6. CPN preservation rules are undefined for replacement, duplicate consolidation, line splitting, merged uploads, and future persisted-run restoration.

The recommended model is one CPN per canonical functional BOM line, with an explicit line-splitting operation when a consolidated row contains uses that need different CPNs. Supplier purchasing lines should continue to aggregate by supplier part number and CPN so distinct CPNs never collapse into one order line.

## 2. Current behavior confirmed in code

### Canonical storage

`src/workflow_runner.py` initializes a `customer_reference` column on every working row. `ActiveBomState.update_row()` writes changes to the canonical DataFrame.

### Existing per-row editing

`app.py` currently supports:

- an editable **Customer Reference** cell in the Working Parts List;
- an **Override individual lines** expander;
- per-line inventory-location assignment;
- generated Project/PCB and R&D references applied to all lines.

### Supplier handoff

`src/purchasing_lines.py` reads the row's `customer_reference` and aggregates on:

```text
(supplier, supplier_part_number, customer_reference)
```

This correctly keeps the same supplier part on separate purchasing lines when its CPN differs. DigiKey FastAdd maps it to `crefN`; both supplier CSVs include it.

### Duplicate consolidation

`src/bom_cleaner.py` consolidates input rows with the same normalized manufacturer and MPN. It combines designators and quantities into one row. `customer_reference` is not an input/mappable standard column and is assigned only after this consolidation.

## 3. Target behavior

The Working Parts List should support this example:

| Working line | Manufacturer part | Designators/use | Quantity | CPN |
|---|---|---:|---:|---|
| 1 | RC0603FR-0710KL | R1, R2 | 2 | `PRJ-ATH-DAB` |
| 2 | RC0603FR-0710KL | R19 | 1 | `RND-ARM-AARON` |
| 3 | GRM188R71C105KA12D | C1, C2 | 2 | `INV-A12` |

Lines 1 and 2 intentionally use the same manufacturer and supplier part but remain separate because their CPNs differ.

The operator should be able to:

- assign or change one line's CPN from the Working Parts List;
- select several lines and assign one CPN to that selection;
- assign a default CPN only to blank lines;
- deliberately replace all CPNs after an explicit confirmation;
- split one consolidated line into two or more allocations when its designators or quantity need different CPNs;
- see mixed, missing, and invalid CPN counts;
- regenerate supplier artifacts only after changed CPNs are saved and validated.

## 4. Findings

### CPN-1 — Duplicate consolidation destroys the required allocation boundary

**Severity: Critical**

`_consolidate_duplicate_parts()` groups rows only by normalized manufacturer and MPN, then combines designators and quantities. It has no CPN at that stage.

This means two source rows such as:

```text
R1,R2 / RC0603FR-0710KL / PRJ-ATH-DAB
R19    / RC0603FR-0710KL / RND-ARM-AARON
```

become one working row before a CPN can be represented. One scalar `customer_reference` cannot describe both uses.

#### Required correction

Support an explicit functional-line identity and a line-splitting operation.

A split must allow the operator to allocate:

- designators;
- quantity per board;
- resulting required/order quantity;
- CPN;
- source-row traceability.

The total quantity of all children must equal the original line. A designator may appear in only one child. The original row must be replaced atomically only after validation succeeds.

If uploaded BOMs can contain a CPN column, map it before duplicate consolidation and include normalized CPN in the consolidation key. Rows with different source CPNs must never be merged.

### CPN-2 — The Working Parts List bypasses validation

**Severity: Critical**

The inline `st.data_editor` path strips the value and writes it through `update_row()` without calling `validate_customer_reference()`.

The separate override form validates and uppercases values, so the two editing surfaces enforce different rules. A user can enter lowercase, spaces, an unsupported prefix, illegal characters, or a value over 30 characters in the main list. Supplier artifacts then receive that unvalidated value.

#### Required correction

Create one domain mutation function, for example:

```python
assign_customer_part_number(active_bom_state, row_ids, value, mode="replace")
```

It must normalize and validate once, update only after the whole request is valid, and mark purchasing artifacts stale once. Every UI path must use it.

Invalid edits must remain visible as a draft/error and must not silently become canonical purchasing data.

### CPN-3 — “Customer Reference” and “Customer Part Number” are conflated

**Severity: High**

The internal field is `customer_reference`. The UI alternates between Customer Reference and Customer Part Number. Mouser calls its corresponding field `CustomerPartNumber`; DigiKey FastAdd calls it `cref`.

This creates ambiguity between:

- AutoBOM's company-controlled CPN;
- a supplier order-line reference;
- a project/build reference;
- an internal inventory-location label.

#### Required correction

Define the domain term explicitly:

> `customer_part_number` is AutoBOM's per-functional-line business identifier. Supplier adapters map it to each vendor's corresponding order-line field.

Prefer a canonical `customer_part_number` field and retain `customer_reference` as a temporary backward-compatible alias during migration. Do not rename only the label while leaving competing meanings undocumented.

The project, R&D, and inventory generators may continue producing CPN values if the Yank SOP defines those formats as valid CPNs.

### CPN-4 — The summary is false for a mixed-CPN BOM

**Severity: High**

`render_customer_reference_summary()` displays the first row's reference as the BOM's reference. When rows contain different CPNs, it still shows that first value and labels it as the current Customer Reference.

#### Required correction

Calculate a complete assignment summary:

- total active lines;
- assigned lines;
- blank lines;
- invalid lines;
- distinct CPN count;
- selected-line count when bulk editing.

Examples:

```text
CPNs: 3 distinct · 11 of 12 lines assigned · 1 blank
CPN: PRJ-ATH-DAB · applied to all 12 lines
```

Never use the first row as a proxy for the entire BOM.

### CPN-5 — Apply to All can erase intentional exceptions

**Severity: High**

`_apply_customer_reference_to_all()` unconditionally overwrites every working row. After operators assign different CPNs, selecting another generated value and clicking Apply to All destroys those assignments.

#### Required correction

Provide separate actions with explicit semantics:

- **Apply to selected lines**;
- **Apply to blank lines**;
- **Replace all line CPNs** with confirmation showing how many existing values will change.

The common/default workflow should preserve existing per-line assignments. Bulk actions should ignore DNP lines by default, with an explicit option if the operator needs to update them.

### CPN-6 — No first-class line selection exists for bulk assignment

**Severity: High**

The current override expander renders one text input and Save button for every row. This becomes difficult to use on large BOMs and does not support assigning one CPN to a chosen subset.

#### Required correction

Add persistent row selection in the Working Parts List. Selection must be based on stable line IDs, not current page positions, so filtering, searching, sorting, and pagination cannot redirect an edit to another row.

The assignment panel should show the selected MPNs/designators and the number of affected rows before saving.

### CPN-7 — Row IDs are runtime index addresses, not durable functional identities

**Severity: High**

`ActiveBomState.row_id_for_index()` returns `run_id:index`. Index-based IDs work within the current DataFrame but are unsuitable as durable identities for line splits, saved selections, reordering, reconsolidation, or restored runs.

#### Required correction

Add an immutable `line_id` stored in the canonical DataFrame. Generate child IDs when splitting and retain explicit ancestry such as `parent_line_id` and source-row IDs. UI widget keys and selections should use `line_id`.

Keep the existing row-ID interface temporarily if needed, but do not build the new allocation model on DataFrame position.

### CPN-8 — Source CPN columns are not imported

**Severity: High**

`STANDARD_COLUMNS`, `MAPPABLE_COLUMNS`, and `COLUMN_ALIASES` do not include Customer Part Number/Customer Reference. If an uploaded BOM already contains per-line CPNs, AutoBOM drops them and later consolidates rows without them.

#### Required correction

Add controlled aliases for intended CPN fields, including likely variations such as:

```text
Customer Part Number
Customer P/N
CPN
Customer Reference
Customer Ref
```

Do not map reference designator columns to CPN. Ambiguous headers must appear in the mapping/review output rather than being guessed.

Validate imported values and keep differently assigned duplicate parts separate.

### CPN-9 — Blank CPN policy is undefined

**Severity: Medium**

Current validation rejects an empty reference when called, but both the main editor and purchasing-line builder allow a blank value. DigiKey then omits `crefN`, while CSVs contain an empty field.

#### Required decision

Choose and document one rule:

- **Recommended:** CPN is optional per purchasing line. Blank lines are visibly counted and require an operator acknowledgement before handoff, but they do not block sourcing. This supports parts that legitimately have no internal CPN.
- **Strict alternative:** every externally purchased line requires a CPN and blanks block Ready for Handoff.

Do not accidentally make blanks optional in one supplier and required in the other.

### CPN-10 — Replacement preservation is implicit

**Severity: Medium**

`apply_replacement()` replaces component identity and sourcing data but leaves `customer_reference` unchanged. This is often correct because the CPN describes the functional use, but the rule is undocumented and untested.

#### Required correction

Define that a replacement on the same functional line preserves its CPN. Show the retained CPN during replacement confirmation. A newly added line starts blank unless the operator selected a default or explicit CPN.

If the operator changes the line's business purpose, that should be an explicit CPN edit rather than an accidental consequence of replacement.

### CPN-11 — Split-line quantity and purchasing behavior can drift

**Severity: High**

Splitting a line affects `qty_per_board`, `required_qty`, supplier order quantity, stock coverage, sourcing decisions, purchase aggregation, and possibly PartsBox project entries. Copying the old sourcing result onto children could over-order or claim stock coverage twice.

#### Required correction

Treat a split as a sourcing-affecting canonical mutation:

1. Validate designator and quantity conservation.
2. Create child functional lines.
3. Recompute required quantities using the current build quantity.
4. Clear quantity-dependent sourcing decisions on the children.
5. Re-run sourcing or mark the children Needs Review until sourcing is refreshed.
6. Mark all purchasing and cleaned-output artifacts stale.

Never duplicate the original `supplier_order_qty` across split children.

### CPN-12 — State freshness does not make invalid data safe

**Severity: Medium**

Calling `refresh_response_snapshot()` correctly marks current artifacts stale after a CPN edit. It does not validate the edit, and the inline editor currently saves first.

#### Required correction

The mutation order must be:

```text
parse/normalize → validate entire requested assignment → update canonical rows atomically → refresh snapshots/stale artifacts
```

Failed validation must leave canonical data and artifact state unchanged.

### CPN-13 — Test coverage proves only the simplest per-row case

**Severity: Medium**

Existing tests cover one valid override and Apply to All. They do not cover:

- mixed CPNs in the summary;
- invalid inline edits;
- bulk assignment to selected or blank lines;
- preservation of exceptions;
- duplicate parts with different imported CPNs;
- splitting a consolidated line;
- quantity/designator conservation;
- replacement preservation;
- same supplier part with different CPNs through both current exporters and FastAdd;
- selection stability across filters and pages;
- old `customer_reference` state migration.

## 5. Recommended data model

Use a functional BOM line as the assignment boundary:

```python
FunctionalBomLine(
    line_id="...",                     # immutable
    parent_line_id="...",              # populated after split
    source_row_ids=(...),
    designators=("R1", "R2"),
    qty_per_board=2,
    build_quantity=10,
    required_qty=20,
    manufacturer="Yageo",
    mpn="RC0603FR-0710KL",
    customer_part_number="PRJ-ATH-DAB",
    ...
)
```

One line has zero or one CPN. One MPN may appear on multiple functional lines. Purchasing aggregation may combine lines only when supplier, supplier part number, and CPN are equal.

Do not store a dictionary of designator-to-CPN assignments inside one DataFrame cell. That would complicate filters, validation, exports, replacement, and quantity calculations. Split canonical lines are easier to inspect and safer to export.

## 6. Recommended user experience

### Working Parts List

- Rename the column to **Customer Part Number (CPN)**.
- Keep direct per-line editing, but route it through the shared validator.
- Show an error beside the affected line without committing invalid data.
- Add row selection that persists by `line_id` across pages and filters.
- Add **Assign CPN to Selected**.

### CPN assignment panel

- Generate Project/PCB, R&D, or Inventory values using the existing builders.
- Offer **Apply to selected lines** and **Apply to blank lines**.
- Put **Replace all line CPNs** behind an explicit confirmation.
- Show how many existing values will be replaced.
- Show distinct, blank, and invalid counts.

### Split action

For a line containing multiple designators, offer **Split for different CPNs**.

The editor should let the operator create allocations and prove:

- all original designators are assigned exactly once;
- child quantities sum to the original quantity;
- every child has a valid or intentionally blank CPN;
- no purchasing action occurs until sourcing is refreshed.

For a quantity-only line without designators, split by positive integer quantities whose sum equals the original.

## 7. Compatibility and migration

1. On load, if `customer_part_number` is absent and `customer_reference` exists, copy the old value into the new canonical field.
2. During one compatibility period, exporters may read the canonical field first and fall back to the legacy field.
3. New runs and summaries should serialize `customer_part_number` and stable `line_id`.
4. Legacy values must be revalidated. Invalid old values should be shown as Needs CPN Review; do not silently rewrite them.
5. Old MyList data is unrelated and must not be treated as CPN state.

## 8. Required tests for implementation

### Domain and mutation tests

- valid single-line assignment;
- invalid assignment is atomic and does not stale artifacts;
- assigning selected rows does not modify unselected rows;
- apply-to-blank preserves existing exceptions;
- replace-all reports and changes the expected rows;
- DNP behavior follows the documented bulk-assignment policy;
- replacement preserves CPN;
- new line default behavior is deterministic.

### Import and consolidation tests

- recognized CPN input headers map correctly;
- reference designator is not mistaken for CPN;
- identical MPN plus identical CPN can consolidate;
- identical MPN plus different CPN remains separate;
- invalid imported CPN is reviewable, not discarded.

### Split tests

- designators are conserved exactly once;
- quantity-only splits conserve quantity;
- invalid totals are rejected atomically;
- child IDs are stable and unique;
- sourcing quantities are recomputed rather than copied;
- outputs and purchasing artifacts become stale.

### Purchasing tests

- same supplier part and same CPN aggregates;
- same supplier part and different CPN remains separate;
- DigiKey FastAdd emits the correct `crefN` per line;
- DigiKey and Mouser CSVs preserve each CPN;
- blank policy is identical across suppliers;
- URL-length fallback is recalculated after CPN changes.

### UI tests

- mixed summary reports distinct CPNs instead of displaying the first row;
- invalid direct edit does not reach canonical state;
- selection remains attached to line IDs through search/filter/page changes;
- Apply to All cannot erase exceptions without confirmation;
- split editor shows and validates all allocations.

## 9. Implementation sequence

1. Decide and document the blank-CPN policy.
2. Introduce `customer_part_number` compatibility normalization and immutable `line_id`.
3. Create one validated, atomic CPN assignment service.
4. Route every existing editing surface through that service.
5. Replace the first-row summary with aggregate assignment status.
6. Add stable row selection and selected/blank-line bulk assignment.
7. Import CPN columns before consolidation and make consolidation CPN-aware.
8. Implement canonical line splitting with quantity/designator conservation.
9. Define replacement and new-line inheritance rules.
10. Update purchasing lines and adapters to use the canonical field with legacy fallback.
11. Add migration, domain, UI, split, and export tests.
12. Update operator and deployment documentation.

## 10. Release acceptance criteria

The feature is ready only when:

1. Any individual Working Parts List line can receive its own valid CPN.
2. Different lines using the same MPN can retain different CPNs.
3. A consolidated line can be safely split when its uses need different CPNs.
4. Invalid CPNs cannot enter canonical state through any UI or import path.
5. Bulk actions preserve exceptions unless replacement is explicitly confirmed.
6. The summary accurately reports uniform, mixed, blank, and invalid states.
7. Filters and pagination cannot apply a CPN to the wrong row.
8. Replacement preserves the functional line's CPN.
9. Split quantities/designators are conserved and sourcing is recomputed safely.
10. DigiKey FastAdd, DigiKey CSV, and Mouser CSV preserve distinct CPNs.
11. Every CPN-affecting mutation invalidates prior purchasing artifacts.
12. Legacy `customer_reference` data remains readable without being mislabeled or silently corrupted.

## 11. Expected files affected by implementation

- `app.py`
- `src/active_bom_state.py`
- `src/customer_reference.py` or a new `customer_part_number.py`
- `src/bom_cleaner.py`
- `src/purchasing_lines.py`
- `src/digikey_fastadd.py`
- `src/digikey_list_export.py`
- `src/mouser_export.py`
- `src/review_actions.py`
- `src/workflow_runner.py`
- relevant export/state/UI tests
- operator and implementation documentation

## 12. Material limitation

This audit determines how AutoBOM should preserve and assign CPNs. The business decision about whether blank CPNs are allowed on externally purchased lines must be confirmed before implementation is considered complete. The recommended default is optional-with-visible-acknowledgement because the requested behavior allows different reasons and does not establish that every part must carry a CPN.

## 13. Current baseline test condition

The following focused command was run during the audit:

```powershell
python -m unittest tests.test_customer_reference tests.test_customer_reference_registry tests.test_customer_reference_ui tests.test_active_bom_state tests.test_digikey_list_export tests.test_mouser_export -q
```

Result on the reviewed working tree:

```text
Ran 83 tests
FAILED (failures=8)
```

All eight failures are in the DigiKey/Mouser export tests. The in-progress supplier exporters now return `PurchasingLineResult` and require sourced status, supplier part number, and supplier order quantity, while the older tests still expect an integer count and use minimally populated rows. The customer-reference and active-state portions of this focused run did not fail.

These are pre-existing uncommitted implementation/test contract differences. Resolve the supplier-export baseline before or as part of the direct-cart implementation, then build the CPN tests against the final canonical purchasing-line contract. Do not weaken the new purchasing validation merely to satisfy the old fixtures.
