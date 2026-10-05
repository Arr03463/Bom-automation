# Claude Code Implementation Handoff — Direct Supplier Purchasing

**Repository:** `https://github.com/Arr03463/Bom-automation.git`  
**Required branch:** `team_release`  
**Prepared:** 2026-09-28  
**Authority:** This document is the implementation assignment. Supporting reports are evidence and context, not additional instructions.

## Assignment

Implement the revised AutoBOM purchasing handoff in the current repository.

The normal operator workflow must become:

- **DigiKey:** provide a direct DigiKey FastAdd cart-loading link and a verified DigiKey-import CSV fallback.
- **Mouser:** provide a verified Mouser-import CSV.
- Do not create a DigiKey MyList during normal application use.
- Do not require the operator to leave AutoBOM, obtain a cart/list key, return, and paste it into AutoBOM.

Read this report before changing code:

- `Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md`
- `Documentation/AutoBOM_DigiKey_Orderable_Variation_Audit.md`
- `Documentation/AutoBOM_Claude_Code_DigiKey_Orderable_Variation_Correction_Handoff.md`

Also consult current implementation and deployment reports where they explain existing behavior, but follow this handoff when older documents describe the MyList workflow.

## Working rules

1. Work only on branch `team_release`. Confirm the branch before editing.
2. Inspect `git status` before editing. The working tree may already contain changes from other work. Preserve them, identify which changes are yours, and do not reset, overwrite, or discard unrelated work.
3. Implement the complete feature, tests, and documentation. Do not stop after adding UI controls or a URL builder.
4. Do not commit secrets, OAuth tokens, refresh tokens, customer BOMs, generated purchasing files, or local runtime state.
5. Use primary supplier documentation to verify the current DigiKey and Mouser CSV import formats. Record the URLs and validation date in the relevant documentation. If a supplier contract cannot be verified, state that limitation and do not label an internal report as a vendor-import file.
6. Preserve product-search authentication. Removing MyLists from the normal flow must not disable the DigiKey product-search integration.
7. Do not commit until tests pass and the diff has been reviewed for unrelated changes.

## Required design

### 1. Canonical purchasing lines

Create a shared module for selecting and normalizing purchasing rows. Use a typed model such as:

```python
@dataclass(frozen=True)
class PurchasingLine:
    supplier: str
    supplier_part_number: str
    quantity: int
    customer_reference: str
    source_row_ids: tuple[str, ...]
```

Use the canonical lines for all of the following:

- supplier item and quantity counts;
- DigiKey FastAdd URL generation;
- DigiKey supplier CSV;
- Mouser supplier CSV;
- artifact requirements;
- purchasing summary and readiness.

A row is eligible only when all conditions are true:

- it is assigned to the matching supplier;
- its sourcing status confirms it was sourced by that supplier;
- it is not marked DNP;
- it has a nonblank supplier part number;
- its order quantity is a positive integer.

Do not silently omit an invalid row and report the package Ready. Return a structured validation error containing the source row identity, field, invalid value, and operator-facing reason.

Aggregate by at least:

```text
(supplier, supplier_part_number, customer_reference)
```

Keep lines with different customer references separate. Preserve stable, deterministic ordering.

### 2. Strict quantity parsing

Provide one parser used by every purchasing artifact.

It must:

- accept normalized integer values and integer-equivalent numeric values;
- reject fractions instead of truncating them;
- reject zero, negative, blank, malformed, NaN, and infinite values;
- return a deterministic validation result;
- never use `int(float(value))` as an unchecked conversion.

### 3. DigiKey FastAdd link

Add a pure, deterministic DigiKey FastAdd URL builder. It must perform no vendor API call and require no MyLists OAuth token.

Requirements:

- use the DigiKey `supplier_part_number` for every `partN` field;
- never substitute the manufacturer part number in the link;
- produce sequential `partN`, `qtyN`, and `crefN` values;
- set the appropriate new-cart behavior and only approved tracking fields;
- encode query parameters with a standard URL encoder;
- calculate the length from the final encoded URL;
- use a named, documented safe-length constant, initially **1700 characters** unless current primary DigiKey documentation establishes another limit;
- return structured output including URL, encoded length, item count, status, and fallback reason;
- never truncate a URL or omit lines to fit the limit.

When the complete encoded URL exceeds the safe limit, return `csv_fallback`. Do not expose an incomplete link.

### 3A. Select an orderable DigiKey packaging variation

Live FastAdd validation on 2026-09-28 confirmed that URL construction works, but exposed a critical upstream selection defect. AutoBOM generated:

```text
311-10.0KHRTR-ND × 3
445-173039-2-ND × 1
```

DigiKey parsed both lines but rejected them as unavailable Tape & Reel quantities. The correct small-quantity sibling variations are:

```text
311-10.0KHRCT-ND
445-173039-1-ND
```

Do not fix this by rewriting `TR` or `-2-ND` suffixes. DigiKey numbering patterns are not a safe universal conversion rule.

Correct `src/digikey_client.py` so sourcing evaluates every Product Information V4 `ProductVariations` entry using:

- `DigiKeyProductNumber`;
- `PackageType.Name`;
- `QuantityAvailableforPackageType`;
- `MinimumOrderQuantity`;
- `StandardPackage` and applicable pricing/order multiples;
- the current required quantity.

Selection policy:

1. Candidate must be orderable in the requested quantity and have enough variation-level availability.
2. Prefer Cut Tape for small tape-based orders.
3. Permit tray, tube, bag, bulk, box, or other unit-orderable packaging when valid.
4. Choose Tape & Reel only when its minimum/order-multiple requirements are satisfied.
5. Use the exact product number returned for the selected variation.
6. If no variation is orderable, return the row to Needs Review with package, requested quantity, MOQ, and availability details.

Persist selected package type and ordering constraints in the sourcing result. Revalidate explicit/cached supplier part numbers so stale TR selections cannot bypass this rule. FastAdd and DigiKey CSV must consume the validated selected variation.

### 4. Supplier CSVs

Create supplier-import CSVs from the same canonical lines used by the link and counts.

For DigiKey:

- include the DigiKey supplier part number;
- use the currently documented DigiKey import header names and column order;
- include quantity and customer reference where supported.

For Mouser:

- use the currently documented Mouser BOM import header names and column order;
- include the Mouser supplier part number, quantity, and customer reference where supported.

If the existing rich CSVs are useful as internal sourcing reports, keep them as distinctly named report artifacts. Do not confuse them with supplier-import CSVs.

### 5. Artifact state and readiness

Replace MyList-centered readiness with handoff artifact requirements derived from current canonical supplier counts.

Add an explicit `digikey_cart_link` artifact. Supported statuses are:

- `current`
- `not_required`
- `csv_fallback`
- `failed`
- `stale`

The required artifacts are determined from current BOM contents:

- DigiKey has lines: DigiKey supplier CSV is required; FastAdd must be `current` or validly `csv_fallback` because of encoded length.
- Mouser has lines: Mouser supplier CSV is required.
- Supplier has no lines: its artifacts are `not_required` and do not block readiness.

`Ready for Handoff` is allowed only when every required supplier artifact is current and valid under this policy. Invalid purchasing data or an export failure must block readiness.

Store useful diagnostics for the DigiKey link:

- encoded URL length;
- configured safe limit;
- item count;
- fallback or failure reason.

Clear obsolete outputs when regeneration fails. A link from an older BOM must never remain actionable beside a failed or stale status.

### 6. Freshness and invalidation

Mark the cart link and relevant supplier exports stale whenever purchasing content can change, including:

- BOM upload or merge;
- build quantity;
- supplier selection;
- supplier part number;
- replacement or Retry result;
- DNP state;
- sourcing status;
- customer reference;
- any quantity used for purchasing.

Disable Open and Copy actions for stale or failed links. Regeneration must rebuild all required purchasing artifacts from one canonical snapshot.

### 7. Streamlit purchasing UI

Replace the normal DigiKey MyList presentation.

For a current DigiKey link, show:

- **Open DigiKey Cart**;
- a copyable DigiKey cart URL using a safe supported Streamlit control;
- **Download DigiKey CSV**;
- item count and total quantity.

If no reliable dedicated clipboard API is available, render the complete URL with `st.code()` so its native copy affordance can be used. Do not inject unsafe HTML or JavaScript.

For DigiKey CSV fallback, show:

- a clear explanation that the cart URL exceeded the supported encoded length;
- **Download DigiKey CSV**;
- the encoded length and limit in an optional diagnostic area;
- no Open or Copy control.

For Mouser, show:

- **Download Mouser CSV**;
- item count and total quantity.

Remove from the normal workflow:

- MyList created status;
- MyList List ID;
- Share Identifier;
- paste-back inputs;
- instructions suggesting that AutoBOM creates a shareable DigiKey MyList or Mouser cart.

### 8. Remove normal-flow MyList coupling

Remove the normal-flow `run_digikey_mylist` behavior and its readiness dependency from:

- `app.py`;
- `src/workflow_runner.py`;
- `src/main.py`, if exposed there;
- configuration validation;
- deployment preflight;
- `.env.example`;
- tests;
- operator and deployment documentation.

Retain legacy MyLists code only if another clearly separate and supported function still uses it. If retained, isolate and label it as legacy/advanced functionality. It must not run during search, upload, sourcing, regeneration, or ordinary purchasing handoff.

Do not remove DigiKey product-search credentials that are still required for sourcing.

### 9. Backward-compatible state normalization

Old sessions and run summaries may contain:

```python
artifact_status["digikey_mylist"]
purchasing["digikey"]["list_id"]
purchasing["digikey"]["share_id"]
```

Normalize state at the workflow/UI boundary:

- tolerate missing new fields;
- ignore legacy MyList state when deriving new readiness;
- do not reinterpret an old List ID as a FastAdd link;
- prevent old state from crashing or creating contradictory UI;
- ensure new runs serialize the new schema consistently.

## Expected file work

Inspect dependencies before choosing exact names, but expect to update:

- `app.py`
- `src/workflow_runner.py`
- `src/digikey_list_export.py`
- `src/mouser_export.py`
- `src/config_validation.py`
- `src/deployment_preflight.py`
- `src/main.py`, if applicable
- `.env.example`
- purchasing, workflow, export, UI, configuration, and deployment tests
- `Documentation/AutoBOM_Operator_Guide.md`
- `Documentation/AutoBOM_Deployment_Guide.md`

Add focused modules for canonical purchasing lines and DigiKey FastAdd generation rather than adding more independent selection loops to `workflow_runner.py`.

## Required tests

### Canonical purchasing lines

- includes only matching, successfully sourced supplier rows;
- excludes DNP rows;
- rejects missing supplier part numbers;
- rejects invalid quantities with row-specific errors;
- aggregates matching lines;
- preserves distinct customer references;
- produces deterministic ordering;
- drives counts, links, and CSVs consistently.

### Quantity parser

- accepts positive integers and integer-equivalent normalized numerics;
- rejects fraction, zero, negative, blank, malformed, NaN, and infinity;
- never truncates.

### FastAdd builder

- sequential `partN`, `qtyN`, and `crefN` fields;
- correct encoding of spaces, punctuation, `&`, `+`, `/`, and the documented Unicode policy;
- correct new-cart behavior;
- exact final encoded-length calculation;
- boundary cases below, exactly at, and above the limit;
- no MPN fallback;
- no line truncation;
- stable output ordering.

### DigiKey packaging selection

- does not assume `ProductVariations[0]` is orderable;
- quantity 3 selects `311-10.0KHRCT-ND`, not `311-10.0KHRTR-ND`, from an observed representative variation fixture;
- quantity 1 selects `445-173039-1-ND`, not `445-173039-2-ND`;
- tray part `497-14907-ND` remains orderable at quantity 1;
- full-reel quantity can select TR when MOQ, multiple, and availability allow it;
- insufficient variation stock is rejected even when top-level product stock is sufficient;
- uploaded/cached TR supplier number is revalidated;
- no suffix-based conversion is used;
- no orderable variation produces Needs Review rather than a cart line.

### Workflow and freshness

- zero MyLists API calls during normal use and purchasing regeneration;
- required artifacts depend on supplier counts;
- export failure blocks Ready;
- an oversized DigiKey link permits Ready only when a valid current DigiKey CSV exists;
- zero-item suppliers do not block Ready;
- every purchasing mutation marks affected artifacts stale;
- failed regeneration clears old actionable outputs;
- retry cannot corrupt other successfully regenerated artifacts;
- legacy MyList-shaped state is accepted safely but ignored for readiness.

### UI

- current link exposes Open, copyable URL, and DigiKey CSV;
- oversized link exposes CSV fallback and no Open/Copy control;
- Mouser exposes its CSV;
- no List ID, Share Identifier, MyList-created, or paste-back controls remain;
- stale and failed links cannot be opened.

### CSV contracts

- golden-file test for DigiKey supplier import;
- golden-file test for Mouser supplier import;
- correct headers, order, quoting, line endings, quantities, part numbers, and customer references;
- no unresolved or invalid row reaches either file.

## Verification commands

Use the repository's actual environment and test runner. At minimum run:

```powershell
python -m unittest tests.test_purchasing_state tests.test_digikey_list_export tests.test_mouser_export tests.test_workflow_runner_contract -q
```

Then run the complete test suite. Run relevant configuration/deployment preflight checks and launch the Streamlit application for a focused UI smoke test.

Perform manual scenarios with:

1. DigiKey-only BOM within the URL limit.
2. DigiKey-only BOM exceeding the URL limit.
3. Mouser-only BOM.
4. Mixed DigiKey and Mouser BOM.
5. Missing supplier part number.
6. Fractional or zero purchasing quantity.
7. DNP row.
8. Customer-reference change after generation.
9. Failed CSV write followed by retry.
10. Old MyList-shaped session or response data.

Do not use real purchasing credentials or submit an order during tests.

## Completion gates

Implementation is complete only when all are true:

1. Normal AutoBOM use makes no DigiKey MyLists call.
2. DigiKey FastAdd uses confirmed DigiKey supplier part numbers.
3. Every DigiKey supplier part number is an orderable packaging variation for the requested quantity.
4. Counts, URL contents, and supplier CSVs originate from the same validated lines.
5. Invalid or unresolved lines block a Ready state with a useful reason.
6. Oversized URLs select a complete CSV fallback without truncation.
7. Required artifact failures block Ready.
8. Purchasing mutations invalidate old links and exports.
9. Supplier CSV formats are supported by documented evidence and golden tests.
10. Old MyList-shaped state cannot crash or mislabel the UI.
11. The full relevant test suite passes.
12. Operator and deployment documents describe the new workflow and no longer require MyLists OAuth/token persistence for normal deployment.

## Required completion report

When finished, create:

```text
Documentation/AutoBOM_Direct_Cart_Handoff_Implementation_Report.md
```

The report must include:

- implementation summary;
- exact files changed;
- key design decisions;
- verified DigiKey and Mouser supplier-format sources;
- state migration behavior;
- tests added and exact test commands/results;
- manual validation results;
- remaining limitations or risks;
- confirmation that no unrelated working-tree changes were overwritten;
- final `git status` summary and commit hash, if a commit was requested and created.

Before declaring completion, review the final diff against this handoff and the audit, then explicitly account for every completion gate.
