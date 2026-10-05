# AutoBOM Direct Cart Handoff — Change-Risk and Defect Audit

**Audience:** Claude Code implementation engineer  
**Repository:** `Arr03463/Bom-automation`  
**Branch:** `team_release`  
**Audit date:** 2026-09-28  
**Requested target:** DigiKey FastAdd cart link with CSV fallback; Mouser CSV; no DigiKey MyList in the normal purchasing flow  
**Mode:** Audit only; this report does not implement the feature

## 1. Target operator workflow

The approved normal handoff is one way. The operator must not leave AutoBOM, generate a key, then return to AutoBOM to paste it.

### DigiKey

- Generate a recipient-usable DigiKey FastAdd URL from current DigiKey-sourced rows.
- Show **Open DigiKey Cart**, **Copy DigiKey Cart Link**, and **Download DigiKey CSV**.
- If the encoded URL is too long for reliable GET use, suppress the link and make the CSV the supported fallback.
- Do not create a DigiKey MyList during normal purchasing regeneration.

### Mouser

- Generate a vendor-usable Mouser CSV.
- Do not create an API cart unless a recipient-usable URL or Access ID can be produced and verified directly by AutoBOM.

## 2. Executive findings

| ID | Severity | Defect or change blocker |
|---|---|---|
| H1 | Critical | Purchasing readiness is defined around `digikey_mylist`; removing it without redesign can produce false Ready status. |
| H2 | Critical | Supplier CSV exporters can include rows that are not successfully sourced. |
| H3 | Critical | DigiKey CSV omits `supplier_part_number`, the reliable DigiKey ordering identifier. |
| H4 | High | Four different builders apply different purchasing eligibility and aggregation rules. |
| H5 | High | Current quantity conversion can crash or accept purchasing-invalid values. |
| H6 | High | No artifact/state model exists for a generated FastAdd URL and its stale lifecycle. |
| H7 | High | MyList assumptions are spread through workflow, UI, configuration, preflight, CLI, tests, and documentation. |
| H8 | High | Existing CSVs are internal reports, not verified supplier-import schemas. |
| H9 | Medium | Old sessions and persisted run summaries will contain obsolete MyList-shaped state. |
| H10 | Medium | Current tests strongly protect MyList behavior but do not cover FastAdd encoding, limits, or recipient usability. |
| H11 | Critical | Live FastAdd validation shows AutoBOM can select a Tape & Reel variation that is not orderable at the requested quantity. |

## 3. H1 — Readiness would become incorrect after removing MyLists

**Severity: Critical**

`src/workflow_runner.py` currently defines:

```python
SUPPLIER_ARTIFACT_KEYS = ["digikey_mylist"]
```

`derive_purchasing_status()` decides Ready/Failed using only required entries from `SUPPLIER_ARTIFACT_KEYS`. Plain file artifacts such as `mouser_export_csv` and `digikey_list_csv` do not block Ready status when they fail.

If `digikey_mylist` is simply deleted, `required_keys` will normally be empty. After one regeneration attempt, AutoBOM will report `Ready for Handoff` even when:

- the DigiKey cart link failed to build;
- the DigiKey CSV failed to write;
- the Mouser CSV failed to write; or
- required supplier part numbers or quantities were rejected.

### Required correction

Replace the supplier-side-effect readiness model with a **required handoff artifact model** derived from current BOM contents:

```python
{
    "mouser_export_csv": mouser_item_count > 0,
    "digikey_cart_link": digikey_item_count > 0 and link_is_within_limit,
    "digikey_list_csv": digikey_item_count > 0,
}
```

For DigiKey, readiness should accept either:

- a current usable FastAdd link plus a current CSV; or
- a current CSV-only fallback when the URL exceeds the supported length.

Define the policy explicitly. Do not infer Ready merely because no live-vendor artifact remains.

## 4. H2 — CSV exporters can include unresolved or inconsistent rows

**Severity: Critical**

Both `export_digikey_list()` and `export_mouser_list()` filter only on `selected_supplier`. They do not require:

- `sourcing_status == sourced_digikey` or `sourced_mouser`;
- a valid supplier part number;
- a positive supplier order quantity; or
- `dnp != True`.

The cart/MyList builders are stricter and require the matching sourced status. This means the UI counts and live artifact can exclude a row while the downloadable supplier CSV includes it.

### Required correction

Create one canonical supplier-line selector and use it for:

- summary counts;
- DigiKey FastAdd URL;
- DigiKey CSV;
- Mouser CSV; and
- complete purchasing-package summary.

Eligibility must require matching supplier and sourced status, a usable supplier part number, a positive integer order quantity, and a non-DNP row.

Invalid rows must block handoff or return to Needs Review with a specific reason. They must not be silently dropped while the page reports Ready.

## 5. H3 — DigiKey CSV lacks the DigiKey supplier part number

**Severity: Critical**

`DIGIKEY_COLUMNS` currently includes MPN and manufacturer but omits `supplier_part_number`. The MyList builder uses `supplier_part_number` when present and falls back to MPN.

DigiKey FastAdd documents its `partN` fields as DigiKey part numbers. A manufacturer MPN fallback can be ambiguous, choose the wrong package, or fail to load.

### Required correction

- Add `supplier_part_number` to the DigiKey export.
- Require it for FastAdd link eligibility.
- Do not silently substitute manufacturer MPN in the direct cart link.
- If a sourced DigiKey row lacks a DigiKey part number, mark the handoff incomplete and surface the row for correction.

## 6. H4 — Purchasing logic is split across incompatible builders

**Severity: High**

Current selection/count/export behavior is spread among:

- `build_mouser_cart_items()`;
- `build_digikey_mylists_parts()`;
- `export_mouser_list()`; and
- `export_digikey_list()`.

They do not share the same validation or aggregation behavior. Mouser aggregates by `(part number, customer reference)`. DigiKey MyLists keeps every BOM row separate. CSV exporters output selected rows without sourced-status validation.

A FastAdd implementation added as a fifth independent loop will make these discrepancies worse.

### Required correction

Introduce a vendor-neutral normalized purchasing-line model, for example:

```python
PurchasingLine(
    supplier="digikey",
    supplier_part_number="311-...-ND",
    quantity=5,
    customer_reference="PRJ-ATH-DAB",
    source_row_ids=(...),
)
```

Generate every supplier handoff artifact from that model. Aggregate only on fields whose differences must remain visible; at minimum `(supplier, supplier_part_number, customer_reference)`.

## 7. H5 — Quantity validation is insufficient

**Severity: High**

Current builders use conversions such as:

```python
int(float(qty))
```

Problems include:

- fractional quantities are silently truncated;
- zero and negative quantities are not consistently rejected;
- malformed values are silently skipped in Mouser but can raise in DigiKey;
- non-finite values are not explicitly rejected; and
- skipping a bad line can still leave the overall handoff looking Ready.

### Required correction

Use one strict purchasing-quantity parser:

- integer only after normalized numeric parsing;
- greater than zero;
- no truncation;
- deterministic error carrying the row ID and field value.

Any invalid quantity must prevent a Ready status until corrected.

## 8. H6 — FastAdd link has no artifact lifecycle

**Severity: High**

The current artifact system knows files and a side-effecting MyList. It has no `digikey_cart_link` output or status. A direct cart link depends on:

- DigiKey supplier part number;
- supplier order quantity;
- customer reference;
- line aggregation; and
- link-length policy.

Every one of those can change after Retry, replacement, build-quantity change, customer-reference change, DNP, or merged upload.

### Required correction

- Add an explicit `digikey_cart_link` artifact and output field.
- Generate it only during explicit purchasing regeneration, or clearly define it as a pure live derivation. Do not mix the two models.
- Mark it stale on every canonical mutation affecting purchasing fields.
- Disable Open/Copy while stale or failed.
- Clear the old URL after a failed regeneration so a previous valid link is never shown beside a failed current status.
- Store the encoded URL length, fallback reason, and item count for operator diagnostics.

Recommended statuses:

- `current` — usable URL generated;
- `not_required` — no DigiKey purchasing lines;
- `csv_fallback` — current BOM is valid but encoded URL exceeds the supported limit;
- `failed` — invalid purchasing data or link-generation error;
- `stale` — BOM changed after generation.

## 9. H7 — MyList coupling is widespread

**Severity: High**

Removing only the API call will leave misleading behavior and dead configuration. MyList assumptions currently exist in:

- `app.py` labels, List ID, Share Identifier, and regeneration call;
- `src/workflow_runner.py` imports, artifact keys, requirements, readiness, response shape, initialization, and regeneration;
- `src/main.py` CLI behavior;
- `src/config_validation.py` and startup warnings;
- `src/deployment_preflight.py`;
- `.env.example` MyLists flags and durable token-store configuration;
- DigiKey OAuth setup and token-persistence documentation;
- purchasing, navigation, customer-reference, workflow-contract, and smoke tests; and
- implementation/operator/deployment documentation.

### Required correction

Treat this as a controlled migration:

1. Add the normalized purchasing-line and FastAdd-link implementation.
2. Replace UI and readiness usage.
3. Remove the normal-flow `run_digikey_mylist` parameter.
4. Remove MyList startup requirements from the Streamlit deployment path.
5. Retain legacy MyList modules only if an explicitly separate advanced tool still uses them; otherwise remove them after tests migrate.
6. Update documentation so operators are not told to configure unnecessary three-legged OAuth or durable refresh-token storage.

Product-search OAuth credentials remain required for DigiKey sourcing. The MyLists refresh-token flow is a separate concern and should not remain a normal deployment prerequisite.

## 10. H8 — Existing CSVs are not verified vendor import files

**Severity: High**

The current files are internal sourcing reports with AutoBOM column names. Neither exporter establishes a supplier-specific import contract, column order, required header names, or round-trip fixture.

Calling these files “upload directly to Mouser/DigiKey” without verification risks manual column mapping or rejected uploads.

### Required correction

- Confirm the current Mouser and DigiKey BOM import schemas using primary supplier documentation or a controlled live upload.
- Create supplier-specific export columns and headers.
- Preserve customer reference where supported.
- Add golden-file tests and at least one documented live validation for each supplier.
- Keep the richer internal sourcing report as a separate artifact.

## 11. H9 — State migration is undefined

**Severity: Medium**

Existing Streamlit sessions and serialized `run_summary.json` files can contain:

```python
artifact_status["digikey_mylist"]
purchasing["digikey"]["list_id"]
purchasing["digikey"]["share_id"]
```

After deployment, old in-memory sessions may survive a hot reload or tests may inject old response shapes. Direct indexing into new fields can cause exceptions or contradictory displays.

### Required correction

- Normalize response state at the workflow/UI boundary.
- Ignore legacy MyList fields for new handoff readiness.
- Default missing new fields safely.
- Add one compatibility test using an old MyList-shaped response.
- Do not claim an old MyList is the current FastAdd cart artifact.

## 12. H10 — Test migration and missing coverage

**Severity: Medium**

Current tests intentionally assert:

- MyList creation occurs only on explicit regeneration;
- `digikey_mylist` status transitions;
- List ID display;
- no duplicate live MyList call; and
- MyList token-persistence failure handling.

These tests will fail by design when the feature changes. Removing them without replacements would eliminate important side-effect and freshness safeguards.

### Required replacement tests

#### Pure FastAdd builder

- correct sequential `partN`, `qtyN`, and `crefN` fields;
- percent encoding of spaces, punctuation, `&`, `+`, `/`, and Unicode policy;
- `newcart=true` and approved tracking fields;
- exact encoded-length calculation;
- boundary immediately below, at, and above the configured limit;
- deterministic ordering;
- duplicate-line aggregation without losing distinct customer references;
- missing supplier part number blocks link generation;
- invalid quantity blocks handoff.

#### Workflow and status

- no MyList API call anywhere in normal search, upload, or purchasing regeneration;
- DigiKey link and both supplier CSVs are generated from the same normalized lines;
- stale link disabled after every purchasing-affecting mutation;
- CSV-only fallback is Ready only under the documented fallback policy;
- supplier export failure blocks Ready when that supplier has required items;
- suppliers with zero items do not block Ready;
- retry after one artifact failure does not corrupt successful artifacts.

#### UI

- Open and Copy controls appear only for a current usable link;
- no MyList ID or Share Identifier is shown;
- fallback explanation and DigiKey CSV appear for oversized links;
- Mouser shows its verified CSV handoff only;
- no paste-back fields exist.

## 13. Additional implementation cautions

### H11 — DigiKey packaging variation is not quantity-orderable

**Severity: Critical**

A live FastAdd URL generated by AutoBOM was opened at DigiKey on 2026-09-28. DigiKey accepted the URL and parsed the parts, proving the FastAdd route and query syntax work, but rejected two order lines with **“Quantity not available in Tape & Reel / Ordering Unavailable.”**

Observed failing selections:

- `311-10.0KHRTR-ND`, quantity 3 — Tape & Reel; DigiKey lists `311-10.0KHRCT-ND` as the Cut Tape variation for `RC0603FR-0710KL`.
- `445-173039-2-ND`, quantity 1 — Tape & Reel; DigiKey lists `445-173039-1-ND` as the Cut Tape variation for `VLS6045EX-100M`.

The middle line, `497-14907-ND`, did not appear in DigiKey's error table and is a tray-packaged part orderable at quantity 1.

The defect is in `src/digikey_client.py`: `_digikey_product_to_result()` uses `ProductVariations[0]` when the top-level DigiKey product number is absent. It does not evaluate `PackageType`, `MinimumOrderQuantity`, `QuantityAvailableforPackageType`, or the requested quantity. Top-level product stock also does not prove that the selected packaging variation is orderable.

DigiKey Product Information V4 exposes the necessary fields on each `ProductVariation`: DigiKey product number, package type, quantity available for that package type, minimum order quantity, standard package, and pricing. Variation order must not be treated as a purchasing preference.

#### Required correction

- Parse every `ProductVariations` entry.
- Select a variation orderable for the requested quantity and current locale.
- Prefer Cut Tape for small tape-based quantities; then use non-reel unit-orderable packaging such as tray, tube, bag, or bulk as appropriate.
- Select Tape & Reel only when the requested quantity satisfies that variation's minimum/order multiple requirements.
- Use variation-level availability and minimum quantity, not only top-level `QuantityAvailable`.
- Never transform DigiKey suffixes heuristically. Select the exact sibling variation supplied by the API.
- Store selected package type, minimum order quantity, and variation availability in the sourcing decision for review and diagnostics.
- If no variation can supply the requested quantity, keep the row in Needs Review rather than generating a known-invalid cart line.
- Revalidate an uploaded or cached DigiKey supplier part number against current variation data before treating it as purchasing-ready.

Add a live-validation fixture representing the observed variation sets and prove quantities 3 and 1 select the CT numbers above, while a full-reel quantity may select TR when valid.

### Copy control

Streamlit 1.64 is installed. Use a supported link/open control. If a custom clipboard component is added, test it under the deployed browser origin and HTTPS policy; do not use unsafe HTML injection. A visible `st.code()` value with its native copy affordance is an acceptable fallback.

### URL size

Apply the limit to the final percent-encoded URL, not the unencoded values. Make the limit a named constant and retain safety margin below general browser/proxy limits. DigiKey's published FastAdd guidance describes approximately 1,700 characters as the safe range.

### URL contents

Customer references and part numbers will appear in browser history, proxy logs, and copied messages. They are operational data rather than credentials, but documentation should state this plainly if references can contain internal project identifiers.

### No network call is needed to build the link

FastAdd URL generation should be a deterministic pure function. Do not require DigiKey MyLists OAuth, a refresh token, or a live vendor request to produce it.

## 14. Recommended implementation sequence

1. Create and test the normalized purchasing-line selector and strict quantity parser.
2. Refactor current counts and supplier CSVs to use those lines.
3. Correct the DigiKey supplier part number and supplier import schemas.
4. Implement and test the pure FastAdd URL builder and length fallback.
5. Replace readiness with required handoff-artifact rules.
6. Add `digikey_cart_link` freshness and output state.
7. Replace the Purchasing Handoff UI.
8. Remove MyList normal-flow calls and configuration dependencies.
9. Add old-state compatibility normalization.
10. Update operator/deployment documentation and run the full test suite.

## 15. Release acceptance criteria

The feature is ready only when:

1. Normal AutoBOM use makes zero DigiKey MyLists calls.
2. Every supplier count, CSV row, and cart-link item derives from the same validated purchasing-line set.
3. No unresolved, DNP, missing-part-number, zero/negative, fractional, or malformed-quantity line reaches a supplier handoff.
4. DigiKey FastAdd uses confirmed DigiKey supplier part numbers.
5. Every DigiKey supplier part number represents a packaging variation orderable at the requested quantity.
6. Oversized links reliably select CSV fallback and never show a truncated link.
7. Any required handoff artifact failure prevents `Ready for Handoff`.
8. Every purchasing-affecting BOM mutation invalidates the prior link and exports.
9. Mouser and DigiKey CSVs have verified supplier-import schemas.
10. Old MyList-shaped session data cannot crash or mislabel the new UI.
11. The complete relevant test suite passes, including the new encoding, packaging, boundary, stale-state, and failure tests.

## 16. Expected files to change

- `app.py`
- `src/workflow_runner.py`
- `src/digikey_list_export.py`
- `src/mouser_export.py`
- new shared purchasing-line module
- new DigiKey FastAdd link module
- `src/config_validation.py`
- `src/deployment_preflight.py`
- `.env.example`
- possibly `src/main.py`
- purchasing, export, workflow, UI, configuration, and deployment tests
- operator and deployment documentation

Legacy `src/digikey_mylists_client.py`, OAuth setup, and token-store code should only remain if another explicitly supported feature still requires them. They must not remain coupled to the normal Streamlit purchasing handoff.
