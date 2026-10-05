"""
Canonical, vendor-neutral purchasing-line selection shared by every
DigiKey/Mouser purchasing handoff artifact: item/quantity counts, the
DigiKey FastAdd cart link, the DigiKey supplier CSV, and the Mouser
supplier CSV. One selection/validation/aggregation implementation, not
four independent loops with different rules (see
Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md, H2/H4).

A row is eligible for a given supplier only when ALL of the following are
true:
  - selected_supplier matches that supplier;
  - sourcing_status confirms it was actually sourced by that supplier
    (not merely selected -- the two are normally set together by
    sourcing_engine, but this does not assume that always holds);
  - it is not marked DNP (an explicit operator "don't populate this
    line" decision, not a data problem -- excluded silently, same as
    Needs Review/Purchasing already treat DNP elsewhere);
  - it has a nonblank supplier part number;
  - its order quantity passes parse_purchasing_quantity().

A row that matches supplier+sourced-status and is NOT DNP, but fails the
part-number or quantity check, is a genuine data problem for a line the
operator explicitly expects to purchase from this supplier -- it becomes
a PurchasingLineError, never a silent omission (see H2's "must not
silently omit an invalid row and report the package Ready").
"""

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuantityParseResult:
    """
    One strict purchasing-quantity parser, used everywhere a purchasing
    artifact needs a quantity (see H5) -- replaces the several
    `int(float(qty))` unchecked conversions previously scattered across
    mouser_cart_client.py/digikey_mylists_client.py, each of which
    truncated fractions and handled malformed/zero/negative values
    inconsistently.
    """

    value: int = None
    error: str = None

    @property
    def is_valid(self):
        return self.error is None


def parse_purchasing_quantity(raw):
    """
    Accepts an integer, or a string/numeric that represents a whole
    number (e.g. "5", "5.0", 5.0, "1,000") -- never truncates a
    fraction. Rejects fractions, zero, negative, blank, malformed, NaN,
    and infinite values.
    """
    if raw is None or isinstance(raw, bool):
        return QuantityParseResult(error=f"missing or invalid quantity: {raw!r}")

    text = str(raw).strip().replace(",", "")
    if not text:
        return QuantityParseResult(error="missing quantity")

    try:
        numeric = float(text)
    except (TypeError, ValueError):
        return QuantityParseResult(error=f"malformed quantity: {raw!r}")

    if math.isnan(numeric) or math.isinf(numeric):
        return QuantityParseResult(error=f"non-finite quantity: {raw!r}")

    if numeric != int(numeric):
        return QuantityParseResult(error=f"fractional quantity not allowed: {raw!r}")

    int_value = int(numeric)
    if int_value <= 0:
        return QuantityParseResult(error=f"quantity must be a positive integer: {raw!r}")

    return QuantityParseResult(value=int_value)


@dataclass(frozen=True)
class PurchasingLine:
    """
    One aggregated purchasing line for a single supplier. Aggregated by
    (supplier, supplier_part_number, customer_reference) -- two BOM rows
    for the same part but different customer references stay separate
    lines (merging them would silently drop one reference; see
    mouser_cart_client.py's identical existing reasoning, now shared).
    `source_row_ids` preserves every canonical BOM row_id that
    contributed to this line, for traceability back to Results/Needs
    Review.

    `mpn`/`manufacturer` are descriptive only (from the FIRST
    contributing row) -- never part of the aggregation key or any
    eligibility/ordering decision, since the supplier part number is
    what every purchasing artifact (FastAdd link, both supplier CSVs)
    actually orders against. Included so a human-readable CSV export
    doesn't need a second lookup back into the canonical BOM.
    """

    supplier: str
    supplier_part_number: str
    quantity: int
    customer_reference: str
    source_row_ids: tuple = field(default_factory=tuple)
    mpn: str = ""
    manufacturer: str = ""


@dataclass(frozen=True)
class PurchasingLineError:
    """A specific row's purchasing data that blocks handoff, with enough
    detail for the operator to find and fix it."""

    row_id: str
    field: str
    value: str
    reason: str


@dataclass(frozen=True)
class PurchasingLineResult:
    lines: tuple = field(default_factory=tuple)
    errors: tuple = field(default_factory=tuple)

    @property
    def is_valid(self):
        return not self.errors

    @property
    def item_count(self):
        return len(self.lines)

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines)


def _row_id(index, run_id):
    return f"{run_id}:{index}" if run_id else str(index)


def build_purchasing_lines(clean_bom, supplier, run_id=""):
    """
    Selects, validates, and aggregates every canonical BOM row assigned
    to `supplier` ("mouser" or "digikey") into PurchasingLine objects.
    Every purchasing artifact for that supplier (counts, DigiKey FastAdd
    URL, DigiKey CSV, Mouser CSV) must be built from this SAME result,
    not a second independent selection.

    Returns a PurchasingLineResult. When `errors` is non-empty, the
    caller must treat this supplier's handoff as blocked/incomplete --
    never silently drop the bad row and report Ready (H2).
    """
    supplier = str(supplier or "").strip().lower()
    sourced_status = f"sourced_{supplier}"

    # dict preserves insertion order (first-seen row order in clean_bom,
    # itself deterministic) -- deterministic, stable ordering without an
    # arbitrary extra sort key.
    aggregated = {}
    errors = []

    for index, row in clean_bom.iterrows():
        row_selected_supplier = str(row.get("selected_supplier", "")).strip().lower()
        row_sourcing_status = str(row.get("sourcing_status", "")).strip().lower()

        if row_selected_supplier != supplier or row_sourcing_status != sourced_status:
            continue

        if row.get("dnp") is True:
            continue

        row_id = _row_id(index, run_id)

        supplier_part_number = str(row.get("supplier_part_number", "") or "").strip()
        if not supplier_part_number:
            errors.append(
                PurchasingLineError(
                    row_id=row_id,
                    field="supplier_part_number",
                    value=str(row.get("supplier_part_number", "")),
                    reason=f"Row is sourced from {supplier.title()} but has no {supplier.title()} supplier part number.",
                )
            )
            continue

        quantity_result = parse_purchasing_quantity(row.get("supplier_order_qty"))
        if not quantity_result.is_valid:
            errors.append(
                PurchasingLineError(
                    row_id=row_id,
                    field="supplier_order_qty",
                    value=str(row.get("supplier_order_qty", "")),
                    reason=quantity_result.error,
                )
            )
            continue

        customer_reference = str(row.get("customer_reference", "") or "").strip()
        key = (supplier, supplier_part_number, customer_reference)

        if key in aggregated:
            existing = aggregated[key]
            aggregated[key] = PurchasingLine(
                supplier=supplier,
                supplier_part_number=supplier_part_number,
                quantity=existing.quantity + quantity_result.value,
                customer_reference=customer_reference,
                source_row_ids=existing.source_row_ids + (row_id,),
                mpn=existing.mpn,
                manufacturer=existing.manufacturer,
            )
        else:
            aggregated[key] = PurchasingLine(
                supplier=supplier,
                supplier_part_number=supplier_part_number,
                quantity=quantity_result.value,
                customer_reference=customer_reference,
                source_row_ids=(row_id,),
                mpn=str(row.get("mpn", "") or "").strip(),
                manufacturer=str(row.get("manufacturer", "") or "").strip(),
            )

    return PurchasingLineResult(lines=tuple(aggregated.values()), errors=tuple(errors))
