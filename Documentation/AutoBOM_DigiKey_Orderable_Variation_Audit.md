# AutoBOM DigiKey Orderable-Variation Audit

**Repository:** `Arr03463/Bom-automation`  
**Branch reviewed:** `team_release`  
**Audit date:** 2026-09-28  
**Mode:** Audit only  
**Trigger:** A live AutoBOM FastAdd link reached DigiKey but DigiKey rejected two low-quantity Tape & Reel lines.

## 1. Terminology correction

The values sent in FastAdd `partN` are supposed to be **DigiKey supplier part numbers**, not manufacturer part numbers.

| Manufacturer part number | DigiKey supplier part number | Packaging |
|---|---|---|
| `RC0603FR-0710KL` | `311-10.0KHRTR-ND` | Tape & Reel |
| `RC0603FR-0710KL` | `311-10.0KHRCT-ND` | Cut Tape |
| `RC0603FR-0710KL` | `311-10.0KHRDKR-ND` | Digi-Reel |
| `VLS6045EX-100M` | `445-173039-2-ND` | Tape & Reel |
| `VLS6045EX-100M` | `445-173039-1-ND` | Cut Tape |
| `VLS6045EX-100M` | `445-173039-6-ND` | Digi-Reel |
| `STM32F411CEU6` | `497-14907-ND` | Tray |

Therefore, the FastAdd builder is correct to send `supplier_part_number`. The defect is that sourcing chose supplier part numbers representing packaging that was not orderable at the requested quantity.

## 2. Live result

The observed URL contained three supplier numbers. DigiKey displayed errors for:

- `311-10.0KHRTR-ND`, quantity 3;
- `445-173039-2-ND`, quantity 1.

Both were recognized as Tape & Reel and rejected as unavailable for those quantities. `497-14907-ND` was absent from the error table, which strongly indicates DigiKey accepted it into the cart; the screenshot alone does not prove final cart contents.

This confirms:

- the FastAdd endpoint and `partN`/`qtyN` structure work;
- the supplier numbers are recognized;
- selection/orderability validation is defective before URL generation.

## 3. Findings

| ID | Severity | Finding |
|---|---|---|
| DK1 | Critical | `_digikey_product_to_result()` selects `ProductVariations[0]` rather than an orderable variation for the quantity. |
| DK2 | Critical | Exact lookup by a supplied DigiKey part number can collapse back to a different first variation and fail matching or change packaging. |
| DK3 | Critical | Sourcing uses top-level product stock instead of selected-variation availability. |
| DK4 | High | Price is taken from the first variation and first break, not the selected variation at requested quantity. |
| DK5 | High | `SupplierResult` and canonical sourcing rows do not retain package type, MOQ, variation availability, or validation status. |
| DK6 | High | Purchasing validates only that the supplier part number is nonblank; it cannot prove the number is orderable. |
| DK7 | High | Cached results preserve invalid packaging choices for up to four hours and the cache key omits locale/account context. |
| DK8 | High | A row's explicit DigiKey supplier number is tried only after a fresh MPN result, so operator/import packaging intent can be silently replaced. |
| DK9 | Medium | Marketplace, maximum-distribution, backorder, stocking, and lifecycle constraints are not incorporated into orderability. |
| DK10 | Medium | Current tests contain no representative multi-variation or quantity-aware DigiKey fixtures. |

## 4. DK1 — First variation is not a purchasing rule

Current code:

```python
variations = product.get("ProductVariations", []) or []
if not supplier_part_number and variations:
    supplier_part_number = variations[0].get("DigiKeyProductNumber", "")
```

DigiKey's API documents each variation separately with package type, availability, MOQ, standard package, pricing, marketplace status, and supplier number. Response order is not documented as a recommendation for the requested quantity.

### Required correction

Use DigiKey's quantity-aware `PricingOptionsByQuantity` endpoint as the authoritative selection input when possible:

```text
GET /products/v4/search/{productNumber}/pricingbyquantity/{requestedQuantity}
```

It returns `Exact`, `MinimumOrderQuantity`, `MaxOrderQuantity`, and `BetterValue` options with the actual supplier number, quantity priced, MOQ, package, availability, and price.

Default AutoBOM selection should use a non-Marketplace `Exact` option that supplies the full requested quantity. Prefer Cut Tape for small tape-based orders. Do not automatically increase order quantity to an MOQ or BetterValue amount without an explicit operator policy and visible approval.

## 5. DK2 — Explicit supplier-number lookup is not exact

`find_best_match_by_supplier_part_number()` requests details for the exact supplied number, but converts the returned product into one `SupplierResult` using variation zero. It then compares the requested supplier number to that possibly different variation.

Example failure:

```text
requested: 311-10.0KHRCT-ND
variation zero: 311-10.0KHRTR-ND
comparison: no match
```

The fallback keyword path repeats the same collapsing behavior.

### Required correction

When lookup input is a DigiKey supplier number:

- select the matching variation by normalized `DigiKeyProductNumber` first;
- validate that exact variation for the requested quantity;
- if it is not orderable, identify valid sibling packaging choices and surface the change;
- never represent one requested supplier number with another variation's stock or price.

## 6. DK3 — Stock is attached to the product, not selected packaging

Current conversion uses top-level `QuantityAvailable`. Sourcing then treats `SupplierResult.stock` as availability for `supplier_part_number`.

This can claim that a TR number has enough stock because the product family has stock in CT, or the reverse.

### Required correction

`stock` used for supplier selection must mean availability for the selected supplier number and package. Use `QuantityAvailableforPackageType` or the quantity-aware response. Preserve top-level availability only as separate informational data if needed.

## 7. DK4 — Price does not correspond to the selected order

`_first_unit_price()` returns the first price break from the first variation. It is independent of the chosen supplier number and requested quantity.

Consequences:

- the displayed unit price may belong to TR while the intended order is CT;
- it may use a price break the requested quantity does not reach;
- candidate ranking can compare unrelated prices;
- subtotal estimates can be wrong.

### Required correction

Use the selected quantity-aware option's `UnitPrice` and `ExtendedPrice`. If only variation pricing is available, select the highest break not exceeding the order quantity from the selected variation. Never price one package using another package's break table.

## 8. DK5 — Required metadata is discarded

`SupplierResult` carries supplier number, stock, and unit price, but lacks:

- supplier package type;
- minimum order quantity;
- quantity priced/orderable quantity;
- package-specific availability;
- marketplace flag/supplier;
- orderability validation status and timestamp.

The sourcing decision columns discard this information again.

### Required correction

Add normalized fields through `SupplierResult`, cache serialization, sourcing decisions, working rows, sourcing reports, and review UI. At minimum:

```text
supplier_package_type
supplier_minimum_order_qty
supplier_available_qty
supplier_quantity_priced
supplier_is_marketplace
supplier_orderability_status
supplier_orderability_checked_at
```

## 9. DK6 — Purchasing-ready does not mean cart-ready

`build_purchasing_lines()` checks sourced status, nonblank supplier part number, and positive quantity. A stale or TR-only number passes.

### Required correction

For DigiKey, require a current quantity-specific orderability assertion matching:

- supplier part number;
- supplier order quantity;
- locale/site;
- selected package variation.

If any differs, the line must be revalidated or returned to Needs Review before FastAdd/CSV generation.

## 10. DK7 — Cache correctness is incomplete

The cache includes required quantity, which is good, but cached `SupplierResult` currently contains the bad collapsed variation. Its four-hour TTL allows the error to persist after code/data changes.

The key also omits DigiKey locale site, currency, account context, and packaging policy even though availability, restrictions, pricing, and MyPricing depend on them.

### Required correction

- Increment `SUPPLIER_CACHE_SCHEMA_VERSION` when variation metadata is added.
- Include supplier site/locale and packaging-policy version in DigiKey cache identity.
- Include account identity only as a non-secret stable discriminator if account pricing/orderability affects cached output.
- Do not serialize access tokens or sensitive account data.
- Reject cached results without current orderability metadata.

## 11. DK8 — Explicit BOM packaging intent can be overridden

`find_best_match_for_row()` performs MPN lookup first and returns it when stock appears sufficient. An uploaded DigiKey supplier part number is only tried afterward.

### Required correction

Define precedence:

1. If an explicit DigiKey supplier number exists, validate it first.
2. If it is orderable, preserve it.
3. If not, propose/select a valid sibling variation according to documented policy and record the change.
4. If no explicit supplier number exists, choose a quantity-aware variation from the MPN.

Do not silently replace operator/import intent without a note visible in the working list or sourcing report.

## 12. DK9 — Other orderability constraints

The code gives active lifecycle only a ranking bonus. It does not make an unorderable candidate fail. It also ignores variation Marketplace status, maximum distribution quantity, and product stocking/backorder fields.

### Required correction

- Default to DigiKey-fulfilled, non-Marketplace results unless the operator enables Marketplace purchasing.
- Reject quantities above maximum distribution limits.
- Treat discontinued/EOL/obsolete/ordering-unavailable results according to an explicit policy, with Needs Review for ambiguity.
- Do not treat aggregate stock as proof of immediate orderability.

## 13. Correct selection model

For each DigiKey row:

```text
MPN or explicit DigiKey number
  → verify manufacturer/MPN identity
  → query quantity-aware pricing/orderability
  → select exact full-quantity option
  → apply package policy (CT for small tape orders)
  → exclude Marketplace by default
  → retain exact DigiKey supplier number and package metadata
  → cache with quantity + locale + policy identity
  → write sourcing decision
  → purchasing rechecks validation identity
  → generate FastAdd and CSV
```

Do not infer packaging by editing part-number suffixes.

## 14. Required tests

- multi-variation product does not select list position zero blindly;
- quantity 3 selects `311-10.0KHRCT-ND` rather than TR;
- quantity 1 selects `445-173039-1-ND` rather than TR;
- tray `497-14907-ND` remains valid at quantity 1;
- explicit CT lookup matches that exact variation;
- invalid explicit TR lookup yields a visible sibling-package correction;
- package-level stock is used instead of top-level stock;
- selected variation's applicable price break is used;
- Exact is preferred over automatic MOQ/BetterValue increases;
- full reel quantity may select TR when orderable;
- Marketplace is excluded by default;
- no valid option produces Needs Review;
- cache schema invalidates old collapsed results;
- locale/policy change misses the old cache entry;
- changed quantity invalidates orderability and purchasing artifacts;
- purchasing rejects missing/stale/mismatched orderability proof;
- FastAdd still uses DigiKey supplier numbers, never MPNs.

## 15. Conclusion

The observed problem is not limited to two bad Tape & Reel suffixes. It is a broader quantity-aware supplier-variation defect affecting supplier-number identity, stock, price, explicit part-number validation, caching, and purchasing readiness.

The FastAdd builder should continue using DigiKey supplier part numbers. The correction belongs primarily in DigiKey sourcing and orderability validation, with a final guard at the purchasing boundary.
