# Claude Code Handoff — DigiKey Orderable Packaging Variation Correction

**Repository:** `https://github.com/Arr03463/Bom-automation.git`  
**Branch:** `team_release`  
**Assignment:** Implement and test the complete correction described in `Documentation/AutoBOM_DigiKey_Orderable_Variation_Audit.md`.

## Required result

AutoBOM must choose an exact DigiKey supplier part number whose packaging is orderable for the requested quantity. FastAdd must continue receiving DigiKey supplier part numbers, not manufacturer part numbers.

Use DigiKey Product Information V4 `PricingOptionsByQuantity` as the preferred quantity-aware source. Select a non-Marketplace `Exact` option that covers the full requested quantity. Prefer Cut Tape for small tape-based orders. Do not silently increase quantities to MOQ or BetterValue options.

## Required implementation

1. Add a DigiKey quantity-aware pricing/orderability client method.
2. Parse all returned options and package-level fields defensively.
3. Preserve explicit DigiKey supplier numbers by validating their exact variation first.
4. For MPN lookup, select an exact, full-quantity, non-Marketplace orderable option.
5. Never convert supplier-number suffixes heuristically.
6. Use selected-variation availability and price.
7. Extend `SupplierResult` and sourcing decision fields with package, MOQ, priced quantity, variation availability, Marketplace, orderability status, and check time.
8. Bump the supplier cache schema and include DigiKey locale/site and packaging-policy version in cache identity.
9. Add a purchasing-boundary check proving the orderability assertion matches the supplier number and order quantity.
10. Send missing, stale, conflicting, or unorderable lines to Needs Review with an operator-readable reason.
11. Surface packaging and MOQ in the Working Parts List/sourcing report where the operator can verify them.
12. Keep the direct-cart link pure; it consumes already validated supplier numbers.

## Regression fixtures

Include representative API fixtures proving:

```text
RC0603FR-0710KL, qty 3
  reject: 311-10.0KHRTR-ND (TR)
  select: 311-10.0KHRCT-ND (CT)

VLS6045EX-100M, qty 1
  reject: 445-173039-2-ND (TR)
  select: 445-173039-1-ND (CT)

STM32F411CEU6, qty 1
  select: 497-14907-ND (Tray)
```

Also test full-reel quantities, insufficient package-level stock, explicit CT input, explicit invalid TR input, Marketplace exclusion, cache invalidation, locale changes, pricing breaks, and absence of any orderable option.

## Working-tree rule

Inspect and preserve all current uncommitted work. Integrate with the in-progress direct-cart and `PurchasingLineResult` changes. Do not reset files or restore older MyList behavior.

## Completion gates

- The three observed regression fixtures select orderable supplier variations.
- FastAdd and DigiKey CSV contain the same validated supplier number and quantity.
- No source or purchasing path treats top-level stock as selected-package stock.
- No price is taken from an unrelated package or inapplicable break.
- Exact supplier-number input is not collapsed to variation zero.
- Old cached collapsed results cannot survive the schema migration.
- Invalid orderability prevents Ready for Handoff.
- Relevant focused and full test suites pass.

Create `Documentation/AutoBOM_DigiKey_Orderable_Variation_Correction_Report.md` with files changed, API contract used, selection policy, tests/results, live validation limitations, and final git status.
