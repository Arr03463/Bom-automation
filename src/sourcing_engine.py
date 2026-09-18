from dataclasses import asdict, dataclass

import inspect

from supplier_lookup_cache import SupplierLookupCache, build_lookup_key


@dataclass
class SupplierResult:
    supplier: str
    manufacturer: str
    mpn: str
    stock: int
    unit_price: str = ""
    supplier_part_number: str = ""
    product_url: str = ""
    notes: str = ""


def parse_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def manufacturer_matches(expected, actual):
    expected = str(expected or "").strip().lower()
    actual = str(actual or "").strip().lower()

    if not expected:
        return True

    return expected == actual or expected in actual or actual in expected



def mpn_matches(expected, actual):
    from manufacturer_aliases import part_numbers_equivalent

    return part_numbers_equivalent(expected, actual)


def decide_no_split_supplier(row, mouser_result=None, digikey_result=None):
    required_qty = parse_int(row.get("required_qty"))
    manufacturer = str(row.get("manufacturer", "")).strip()
    mpn = str(row.get("mpn", "")).strip()
    qty_per_board = parse_int(row.get("qty_per_board"))
    build_quantity = parse_int(row.get("build_quantity"))

    if qty_per_board is not None and build_quantity is not None:
        order_qty = qty_per_board * build_quantity
    else:
        order_qty = required_qty
    if not mpn:
        return {
            "selected_supplier": "",
            "supplier_order_qty": "",
            "mouser_stock": "",
            "digikey_stock": "",
            "sourcing_status": "manual_review",
            "sourcing_notes": "Missing MPN; cannot source.",
        }

    if required_qty is None:
        return {
            "selected_supplier": "",
            "supplier_order_qty": "",
            "mouser_stock": "",
            "digikey_stock": "",
            "sourcing_status": "manual_review",
            "sourcing_notes": "Missing or invalid required_qty.",
        }

    mouser_stock = mouser_result.stock if mouser_result else 0
    digikey_stock = digikey_result.stock if digikey_result else 0

    if mouser_result and mouser_stock >= required_qty:
        notes = ["Mouser can cover full required quantity."]
        if mouser_result.notes:
            notes.append(mouser_result.notes)
        return {
            "selected_supplier": "Mouser",
            "supplier_part_number": mouser_result.supplier_part_number,
            "unit_price": mouser_result.unit_price,
            "supplier_order_qty": order_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_mouser",
            "sourcing_notes": "; ".join(notes),
        }

    if digikey_result and digikey_stock >= required_qty:
        notes = ["Mouser could not cover full quantity; DigiKey can."]
        if digikey_result.notes:
            notes.append(digikey_result.notes)
        return {
            "selected_supplier": "DigiKey",
            "supplier_part_number": digikey_result.supplier_part_number,
            "unit_price": digikey_result.unit_price,
            "supplier_order_qty": order_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_digikey",
            "sourcing_notes": "; ".join(notes),
    }

    return {
        "selected_supplier": "",
        "supplier_order_qty": "",
        "mouser_stock": mouser_stock,
        "digikey_stock": digikey_stock,
        "sourcing_status": "check_wall_inventory",
        "sourcing_notes": "Neither Mouser nor DigiKey can cover full required quantity.",
    }


SOURCING_DECISION_COLUMNS = [
    "selected_supplier",
    "supplier_part_number",
    "unit_price",
    "supplier_order_qty",
    "mouser_stock",
    "digikey_stock",
    "sourcing_status",
    "sourcing_notes",
]

EMPTY_SOURCING_DECISION = {column: "" for column in SOURCING_DECISION_COLUMNS}


def source_row(row, mouser_lookup, digikey_lookup, persistent_cache=None, run_cache=None):
    """
    Sources exactly one row using the same Mouser-first/DigiKey-fallback/
    no-split decision logic apply_sourcing_decisions() uses for a whole
    BOM: DigiKey is only queried when Mouser did not already cover the
    required quantity. This is the single shared seam Retry Exact and
    replacement re-sourcing call for one row, instead of each
    reimplementing (or partially duplicating) this orchestration.

    Returns a dict with every key in SOURCING_DECISION_COLUMNS always
    present as a string, so a caller overwriting a row's existing
    sourcing fields with this result can never leave a stale value from
    a previous decision behind.

    persistent_cache/run_cache may be shared across many calls (a full
    BOM pass) or omitted for one ad hoc row (Retry/replacement), in which
    case a persistent cache is loaded and saved just for this call.
    """
    owns_cache = persistent_cache is None
    persistent_cache = persistent_cache if persistent_cache is not None else SupplierLookupCache()
    run_cache = run_cache if run_cache is not None else {}

    mpn = str(row.get("mpn", "")).strip()
    manufacturer = str(row.get("manufacturer", "")).strip()

    mouser_result = None
    digikey_result = None
    lookup_notes = []

    if mpn:
        required_qty = parse_int(row.get("required_qty"))

        try:
            mouser_result = _cached_supplier_lookup(
                "mouser",
                row,
                persistent_cache,
                run_cache,
                lambda: mouser_lookup(row),
            )
        except Exception as exc:
            mouser_result = None
            lookup_notes.append(f"Mouser lookup failed: {exc}")

        try:
            if not mouser_result or required_qty is None or mouser_result.stock < required_qty:
                digikey_result = _cached_supplier_lookup(
                    "digikey",
                    row,
                    persistent_cache,
                    run_cache,
                    lambda: _call_digikey_lookup(
                        digikey_lookup,
                        row,
                        mpn,
                        manufacturer,
                    ),
                )
        except Exception as exc:
            digikey_result = None
            lookup_notes.append(f"DigiKey lookup failed: {exc}")

    decision = decide_no_split_supplier(row, mouser_result, digikey_result)

    if lookup_notes:
        existing = decision.get("sourcing_notes", "")
        decision["sourcing_notes"] = "; ".join([existing] + lookup_notes) if existing else "; ".join(lookup_notes)

    full_decision = dict(EMPTY_SOURCING_DECISION)
    full_decision.update(decision)
    full_decision = {key: str(value) for key, value in full_decision.items()}

    if owns_cache:
        persistent_cache.save()

    return full_decision


def apply_sourcing_decisions(clean_bom, mouser_lookup, digikey_lookup):
    updated = clean_bom.copy().astype(object)
    persistent_cache = SupplierLookupCache()
    run_cache = {}

    for column in SOURCING_DECISION_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    for index, row in updated.iterrows():
        decision = source_row(
            row, mouser_lookup, digikey_lookup, persistent_cache=persistent_cache, run_cache=run_cache
        )

        for key, value in decision.items():
            updated.at[index, key] = value

    persistent_cache.save()
    return updated


def _cached_supplier_lookup(supplier_name, row, persistent_cache, run_cache, lookup_fn):
    key = build_lookup_key(supplier_name, row)

    if key in run_cache:
        return run_cache[key]

    cached_value = persistent_cache.get(key)
    if cached_value:
        result = _supplier_result_from_cache(cached_value)
        run_cache[key] = result
        return result

    result = lookup_fn()
    run_cache[key] = result

    if result:
        persistent_cache.set(key, _supplier_result_to_cache(result))

    return result


def _supplier_result_to_cache(result):
    return asdict(result)


def _supplier_result_from_cache(value):
    try:
        return SupplierResult(**value)
    except TypeError:
        return None


def _call_digikey_lookup(digikey_lookup, row, mpn, manufacturer):
    signature = inspect.signature(digikey_lookup)
    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if len(positional_parameters) == 1:
        return digikey_lookup(row)

    return digikey_lookup(mpn, manufacturer)
