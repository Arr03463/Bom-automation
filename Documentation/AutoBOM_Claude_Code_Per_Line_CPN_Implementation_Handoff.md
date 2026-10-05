# Claude Code Implementation Handoff — Per-Line Customer Part Numbers

**Repository:** `https://github.com/Arr03463/Bom-automation.git`  
**Required branch:** `team_release`  
**Prepared:** 2026-09-28  
**Mode:** Implement, test, document, and report  
**Primary requirement:** Every functional line in the AutoBOM Working Parts List can have its own Customer Part Number (CPN). Different uses of the same manufacturer part can retain different CPNs.

## 1. Instruction authority

This document is the implementation assignment. Read the following audit as supporting evidence:

- `Documentation/AutoBOM_Per_Line_Customer_Part_Number_Audit.md`

Older reports and implementation documents are context only. Where they describe one BOM-wide Customer Reference, first-row summaries, unrestricted Apply to All behavior, or DigiKey MyLists, this handoff supersedes them.

## 2. Required outcome

Implement a per-functional-line CPN model.

The operator must be able to:

- assign a valid CPN to one Working Parts List line;
- select multiple lines and assign one CPN to only those lines;
- apply a generated CPN to blank lines without overwriting exceptions;
- explicitly replace all existing line CPNs after confirmation;
- split a consolidated line when separate designators or quantities require different CPNs;
- see whether the current BOM has one CPN, several CPNs, blanks, or invalid legacy/imported values;
- preserve distinct CPNs through sourcing, DigiKey FastAdd, DigiKey CSV, and Mouser CSV.

Example required result:

| Manufacturer part | Designators | Quantity | CPN |
|---|---|---:|---|
| `RC0603FR-0710KL` | R1, R2 | 2 | `PRJ-ATH-DAB` |
| `RC0603FR-0710KL` | R19 | 1 | `RND-ARM-AARON` |
| `GRM188R71C105KA12D` | C1, C2 | 2 | `INV-A12` |

The first two rows intentionally remain separate even though their manufacturer part is identical.

## 3. Working-tree safety

1. Confirm the current branch is `team_release` before editing.
2. Inspect `git status` and the complete existing diff before changing files.
3. The working tree contains uncommitted direct-cart, supplier-export, sourcing-cache, tests, and documentation changes. Preserve them. Do not reset, restore, overwrite, or reimplement them from an older commit.
4. Integrate CPN work with the current `purchasing_lines.py`, `digikey_fastadd.py`, and revised exporter contracts.
5. The current focused baseline has eight older DigiKey/Mouser export-test failures caused by an in-progress contract migration. Update those tests to the final validated purchasing-line contract. Do not weaken source-status, supplier-part-number, or quantity validation to make old fixtures pass.
6. Do not commit secrets, supplier tokens, real BOM data, generated purchasing artifacts, or local runtime files.

## 4. Domain terminology

Use **Customer Part Number (CPN)** as the AutoBOM business concept.

Canonical field:

```text
customer_part_number
```

Supplier mappings:

| AutoBOM | DigiKey | Mouser |
|---|---|---|
| `customer_part_number` | FastAdd `crefN` / CSV Customer Reference | CSV Customer Reference or vendor-supported Customer Part Number field |

`customer_reference` is a legacy compatibility field. Do not continue using both fields as independent sources of truth.

The existing Project/PCB, R&D, and Inventory builders remain valid CPN generators:

```text
PRJ-<PROJECT>-<PCB>
RND-<PROJECT>-<OWNER>
INV-<LOCATION>
```

Preserve the existing company validation rules unless the governing SOP is explicitly changed.

## 5. Canonical data model

### 5.1 Stable functional-line identity

Add immutable fields to canonical working rows:

```text
line_id
parent_line_id
customer_part_number
```

Requirements:

- `line_id` is generated once and stored in the DataFrame; it must not depend on DataFrame index or current row position.
- `parent_line_id` is blank for an original line and identifies the source line for split children.
- UI selection, widget keys, row lookup, mutation, and source traceability use `line_id`.
- Keep temporary compatibility with `run_id:index` row IDs where required by existing callers, but do not base the new feature on them.
- Adding, merging, filtering, sorting, pagination, and regenerating outputs must not change existing line IDs.

### 5.2 CPN assignment boundary

One functional line has zero or one CPN. One MPN may appear on several functional lines with different CPNs.

Do not store a designator-to-CPN dictionary inside one cell. Split the canonical line when one row contains multiple uses requiring different CPNs.

### 5.3 Blank policy

Use this policy unless a later explicit business rule supersedes it:

- A CPN may remain blank while preparing and sourcing a BOM.
- Blank CPNs do not block sourcing or purchasing regeneration.
- The UI must prominently report the blank count before handoff.
- Supplier outputs preserve blanks consistently; they must not invent a value.
- Invalid nonblank CPNs block purchasing regeneration until corrected.

This distinguishes an intentional or unfinished blank from malformed data.

## 6. Compatibility normalization

At the workflow/state boundary:

1. If `customer_part_number` is absent and legacy `customer_reference` exists, copy the legacy value into the canonical field.
2. If both fields exist and differ, do not guess. Mark the line for CPN review and expose both values in a migration diagnostic.
3. Validate migrated nonblank values.
4. Invalid migrated values remain visible and reviewable; never silently uppercase, truncate, discard, or replace them.
5. New runs, exports, snapshots, and summaries write `customer_part_number` as the canonical value.
6. During the compatibility period, supplier adapters may fall back to `customer_reference` only when the canonical column is absent. They must never prefer it when the canonical field exists.
7. Do not reinterpret old DigiKey MyList fields as CPN data.

Implement normalization in one shared function and test it directly.

## 7. One validated mutation service

Create a domain service rather than letting UI code call `ActiveBomState.update_row()` directly for CPN edits.

Suggested interface:

```python
assign_customer_part_number(
    active_bom_state,
    line_ids,
    value,
    mode="selected",  # selected | blanks | replace_all
)
```

Requirements:

- normalize and validate the proposed nonblank value once;
- resolve all target line IDs before modifying anything;
- reject unknown or duplicate IDs;
- calculate which rows would change;
- apply all changes atomically only after complete validation;
- return a structured result with changed IDs, unchanged IDs, replaced-value count, and errors;
- mark response snapshots and affected artifacts stale exactly once after a successful mutation;
- leave canonical data and artifact status unchanged after a failed validation;
- ignore DNP rows for bulk operations by default, while allowing direct per-line editing if needed.

Route every CPN edit through this service:

- Working Parts List cell editing;
- selected-line bulk assignment;
- apply-to-blank;
- confirmed replace-all;
- Project/PCB generator;
- R&D generator;
- Inventory recommendation assignment;
- individual override editor;
- imported-value correction.

Do not leave a second UI path that writes unvalidated text directly.

## 8. Import and consolidation

### 8.1 Import aliases

Add a canonical mapping target for CPN and carefully scoped aliases such as:

```text
Customer Part Number
Customer P/N
Customer PN
CPN
Customer Reference
Customer Ref
```

Do not confuse Reference, RefDes, Designator, or Reference Designator with CPN. Ambiguous mappings must be reported for review.

### 8.2 Consolidation rules

CPN must be available before duplicate consolidation.

- Same normalized manufacturer + MPN + same normalized CPN may consolidate when all other existing consolidation rules allow it.
- Same manufacturer + MPN + different CPN must remain separate.
- A blank CPN and a nonblank CPN must remain separate.
- Invalid CPN values must remain traceable and enter review; they must not be discarded.

Update consolidation warnings so operators can see whether rows were combined or intentionally kept separate because of CPN.

## 9. Safe line splitting

Add an explicit **Split for Different CPNs** operation for a canonical functional line.

### 9.1 Designator-based split

When designators exist:

- parse the original designators into discrete tokens using one shared parser;
- require every original designator to appear in exactly one child;
- reject missing, duplicated, or invented designators;
- derive each child's `qty_per_board` from its assigned designator count unless the current quantity model requires an explicit verified value;
- ensure child quantities sum to the original.

### 9.2 Quantity-only split

When no designators exist:

- accept positive integer child quantities;
- require the sum to equal the original `qty_per_board`;
- reject zero, negative, fractional, blank, malformed, and nonconserving allocations.

### 9.3 Atomic mutation

The split must:

1. Validate all children, CPNs, quantities, and designators.
2. Generate unique immutable child `line_id` values.
3. Set each child's `parent_line_id` to the original line's ID.
4. Preserve source-file/source-row ancestry and component identity.
5. Replace the original row only after the complete split is valid.
6. Recompute `required_qty` from child `qty_per_board` and the current build quantity.
7. Clear quantity-dependent supplier sourcing data from children.
8. Re-source children or mark them Needs Review until refreshed.
9. Never copy the original `supplier_order_qty` to every child.
10. Mark cleaned outputs, sourcing reports, purchasing CSVs, and DigiKey FastAdd stale.

If PartsBox project updates have already occurred, do not silently duplicate entries. Surface the need to regenerate or reconcile the PartsBox artifact under the existing project-write policy.

## 10. Replacement and new-line rules

- Replacing a component on an existing functional line preserves its CPN because the functional purpose remains attached to the line.
- The replacement confirmation UI must display the retained CPN.
- A new line added from Search starts with a blank CPN unless the operator explicitly chose a default or assignment target.
- Merged uploads retain imported canonical CPN values and receive new unique line IDs without changing existing IDs.
- DNP does not delete a CPN; it excludes the line from purchasing under existing DNP behavior.

Add direct tests for these rules.

## 11. Purchasing behavior

Update the current canonical purchasing-line implementation to read `customer_part_number`.

Purchasing aggregation remains:

```text
(supplier, supplier_part_number, customer_part_number)
```

Therefore:

- same supplier part + same CPN may aggregate;
- same supplier part + different CPN must remain separate;
- customer part numbers must remain attached to the correct quantities;
- invalid nonblank CPN blocks the relevant supplier artifact;
- blank CPN follows the documented optional policy consistently for both suppliers.

Verify:

- DigiKey FastAdd writes the correct CPN into each `crefN` parameter;
- DigiKey CSV writes it into the verified corresponding field;
- Mouser CSV writes it into the verified corresponding field;
- URL length and CSV fallback are recalculated after every CPN change;
- no purchasing artifact reads a detached, first-row, or BOM-wide CPN value.

## 12. Streamlit user experience

### 12.1 Working Parts List

- Rename the visible column to **Customer Part Number (CPN)**.
- Keep per-line editing, with shared validation and atomic mutation.
- Show an inline/operator-visible error for a rejected value.
- Do not commit invalid drafts into canonical state.
- Add row selection based on immutable `line_id`.
- Preserve selection across filtering and pagination when the selected line remains in the same run.
- Clear selection safely when a selected line is deleted or replaced by a split.

### 12.2 Summary

Replace the first-row proxy with an aggregate summary.

Examples:

```text
CPN: PRJ-ATH-DAB · applied to all 12 active lines
CPNs: 3 distinct · 11 of 12 active lines assigned · 1 blank · 0 invalid
```

Count DNP separately or exclude it from the active denominator and label the behavior clearly.

### 12.3 Assignment actions

Provide:

- **Apply to selected lines**;
- **Apply to blank lines**;
- **Replace all line CPNs**.

The replace-all action must show a confirmation containing:

- total affected lines;
- number of existing nonblank values being replaced;
- number of distinct existing CPNs.

Do not make destructive replacement the default action.

### 12.4 Split editor

For a selected line, show:

- component and manufacturer;
- original designators and quantity;
- allocation rows containing designators/quantity and CPN;
- live conservation validation;
- final confirmation.

Do not save a partially valid split.

## 13. Artifact and readiness behavior

Every successful CPN assignment, import correction, or split must make affected generated artifacts stale under the existing artifact-state model.

At minimum consider:

- cleaned CSV;
- cleaned workbook;
- sourcing report;
- DigiKey CSV;
- DigiKey cart link;
- Mouser CSV;
- run summary;
- PartsBox import/project artifacts when line structure or quantities change.

A simple CPN edit does not require a vendor lookup, but it does require purchasing-artifact regeneration. A split changes quantities and requires sourcing reconciliation.

Invalid nonblank CPNs must appear in Needs Review or an equally blocking canonical validation state. They must prevent `Ready for Handoff`.

## 14. Required automated tests

### 14.1 Validation and mutation

- valid single-line assignment;
- blank assignment under the documented optional policy;
- lowercase, spaces, bad prefix, disallowed characters, and overlength rejected;
- invalid assignment changes no row and no artifact state;
- selected assignment changes only selected IDs;
- apply-to-blank preserves nonblank exceptions;
- replace-all reports and changes the correct values;
- unknown or duplicate line IDs fail atomically;
- DNP bulk behavior matches the stated policy.

### 14.2 Stable identity

- line IDs survive filter, sort, pagination, build-quantity update, sourcing refresh, and output regeneration;
- merged rows receive unique IDs;
- split children receive unique IDs and correct parent identity;
- a page-position change cannot redirect an edit.

### 14.3 Import and migration

- every approved CPN alias maps correctly;
- reference-designator headers never map to CPN;
- legacy-only `customer_reference` migrates;
- matching legacy and canonical values normalize cleanly;
- conflicting values become reviewable;
- invalid legacy values remain visible and block handoff;
- new serialization uses the canonical field.

### 14.4 Consolidation

- same MPN/same CPN consolidates correctly;
- same MPN/different CPN remains separate;
- blank and nonblank remain separate;
- quantities, designators, and source rows remain correct.

### 14.5 Split operation

- valid designator split;
- valid quantity-only split;
- missing, duplicated, or invented designator rejected;
- nonconserving quantity rejected;
- fraction, zero, negative, blank, and malformed allocation rejected;
- failure leaves the original line untouched;
- success removes/replaces the original atomically;
- children recompute required quantities;
- supplier quantity decisions are cleared/re-sourced correctly;
- relevant artifacts become stale.

### 14.6 Replacement and additions

- replacement preserves CPN;
- replacement UI exposes retained CPN;
- new Search-added line starts blank by default;
- merged upload preserves imported CPNs.

### 14.7 Purchasing

- same supplier part/same CPN aggregates;
- same supplier part/different CPN stays separate;
- DigiKey FastAdd uses correct `crefN` for every line;
- DigiKey and Mouser CSVs preserve CPN and quantity pairing;
- invalid CPN blocks relevant artifacts;
- blanks behave identically across supplier adapters;
- CPN edit invalidates and regenerates URL-length fallback correctly.

### 14.8 UI

- mixed summary never displays only the first row's value;
- rejected inline edit does not reach canonical state;
- selected-line assignment remains correct across filters/pages;
- apply-to-blank preserves exceptions;
- replace-all requires confirmation;
- split editor validates before save;
- purchasing download/open controls are disabled while stale or invalid.

## 15. Verification procedure

Run focused domain tests first, then the complete suite. At minimum include the current customer-reference, active-state, workflow, purchasing, supplier-export, and Streamlit UI suites.

Resolve the known exporter contract failures by migrating tests and callers to the current `PurchasingLineResult` contract. Do not restore unsafe old filtering behavior.

Perform manual Streamlit scenarios:

1. Assign one CPN to one line.
2. Assign another CPN to a different line.
3. Assign one CPN to a selected subset spanning multiple pages.
4. Apply a default only to blanks.
5. Attempt replace-all and verify confirmation/counts.
6. Enter an invalid value through the main grid.
7. Split a multi-designator row into two CPNs.
8. Split a quantity-only row.
9. Replace a component and verify CPN preservation.
10. Regenerate mixed DigiKey/Mouser handoff and inspect every CPN/quantity pairing.
11. Load a BOM containing an imported CPN column.
12. Exercise a legacy `customer_reference`-only state.

Do not place an order or use production purchasing data during validation.

## 16. Implementation sequence

1. Stabilize and understand the current uncommitted direct-cart/export contract.
2. Add immutable line identity and compatibility normalization.
3. Add canonical `customer_part_number` and migration behavior.
4. Implement the validated atomic assignment service.
5. Route every current editor/generator through the service.
6. Add aggregate CPN summary and stable selected-line assignment.
7. Map imported CPN columns and update consolidation rules.
8. Implement safe line splitting and sourcing reconciliation.
9. Update replacement/add/merge behavior.
10. Update canonical purchasing lines and supplier adapters.
11. Update artifact readiness and stale behavior.
12. Add all required tests and resolve current contract drift.
13. Update operator/deployment documentation.
14. Review the final diff against every acceptance criterion.

## 17. Release acceptance criteria

Implementation is complete only when:

1. Any individual functional line can receive its own valid CPN.
2. Bulk assignment changes only the intended stable line IDs.
3. Apply-to-blank preserves existing per-line exceptions.
4. Replace-all cannot occur without explicit confirmation and impact counts.
5. Same MPN with different CPNs remains representable and exportable.
6. Consolidated lines can be safely split with designator and quantity conservation.
7. Invalid CPNs cannot enter canonical state through editing or clean imports.
8. Legacy invalid/conflicting state is visible and reviewable rather than silently repaired.
9. The summary accurately reports uniform, mixed, blank, and invalid states.
10. Replacement preserves the functional line's CPN.
11. Split children receive recomputed quantities and safe sourcing state.
12. DigiKey FastAdd, DigiKey CSV, and Mouser CSV preserve distinct CPN/quantity pairs.
13. Every CPN mutation invalidates the correct prior artifacts.
14. Known supplier-export contract test drift is resolved without weakening validation.
15. The full relevant automated suite passes and manual scenarios are documented.

## 18. Expected files to change

Inspect dependencies before finalizing the list. Expected work includes:

- `app.py`
- `src/active_bom_state.py`
- `src/customer_reference.py` or a new `src/customer_part_number.py`
- `src/bom_cleaner.py`
- `src/purchasing_lines.py`
- `src/digikey_fastadd.py`
- `src/digikey_list_export.py`
- `src/mouser_export.py`
- `src/review_actions.py`
- `src/workflow_runner.py`
- customer-reference/CPN tests
- active-state and cleaner tests
- workflow and purchasing tests
- supplier-export/FastAdd tests
- Streamlit UI tests
- operator and implementation documentation

## 19. Required completion report

Create:

```text
Documentation/AutoBOM_Per_Line_CPN_Implementation_Report.md
```

Include:

- implementation summary;
- exact files changed;
- final data model and compatibility behavior;
- blank-CPN policy;
- consolidation and split rules;
- replacement/add/merge behavior;
- supplier mapping behavior;
- automated commands and exact results;
- manual scenarios and results;
- known limitations or deferred risks;
- confirmation that unrelated working-tree changes were preserved;
- final `git status` and commit hash if a commit was requested.

Before declaring completion, explicitly account for every release acceptance criterion and review the final diff for direct writes that bypass the CPN mutation service.
