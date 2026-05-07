from dataclasses import dataclass


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
    expected = str(expected or "").strip().lower()
    actual = str(actual or "").strip().lower()

    return expected == actual


def decide_no_split_supplier(row, mouser_result=None, digikey_result=None):
    required_qty = parse_int(row.get("required_qty"))
    manufacturer = str(row.get("manufacturer", "")).strip()
    mpn = str(row.get("mpn", "")).strip()

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
        return {
            "selected_supplier": "Mouser",
            "supplier_order_qty": required_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_mouser",
            "sourcing_notes": "Mouser can cover full required quantity.",
        }

    if digikey_result and digikey_stock >= required_qty:
        return {
            "selected_supplier": "DigiKey",
            "supplier_order_qty": required_qty,
            "mouser_stock": mouser_stock,
            "digikey_stock": digikey_stock,
            "sourcing_status": "sourced_digikey",
            "sourcing_notes": "Mouser could not cover full quantity; DigiKey can.",
        }

    return {
        "selected_supplier": "",
        "supplier_order_qty": "",
        "mouser_stock": mouser_stock,
        "digikey_stock": digikey_stock,
        "sourcing_status": "check_wall_inventory",
        "sourcing_notes": "Neither Mouser nor DigiKey can cover full required quantity.",
    }


def apply_sourcing_decisions(clean_bom, mouser_lookup, digikey_lookup):
    updated = clean_bom.copy().astype(object)

    for col in [
        "selected_supplier",
        "supplier_order_qty",
        "mouser_stock",
        "digikey_stock",
        "sourcing_status",
        "sourcing_notes",
    ]:
        if col not in updated.columns:
            updated[col] = ""

    for index, row in updated.iterrows():
        mpn = str(row.get("mpn", "")).strip()
        manufacturer = str(row.get("manufacturer", "")).strip()

        mouser_result = None
        digikey_result = None

        lookup_notes = []

        if mpn:
            required_qty = parse_int(row.get("required_qty"))

            try:
                mouser_result = mouser_lookup(mpn, manufacturer)
            except Exception as exc:
                mouser_result = None
                lookup_notes.append(f"Mouser lookup failed: {exc}")

            try:
                if not mouser_result or required_qty is None or mouser_result.stock < required_qty:
                    digikey_result = digikey_lookup(mpn, manufacturer)
            except Exception as exc:
                digikey_result = None
                lookup_notes.append(f"DigiKey lookup failed: {exc}")

        decision = decide_no_split_supplier(row, mouser_result, digikey_result)

        if lookup_notes:
            existing = decision.get("sourcing_notes", "")
            combined = "; ".join([existing] + lookup_notes if existing else lookup_notes)
            decision["sourcing_notes"] = combined


        for key, value in decision.items():
            updated.at[index, key] = str(value)

    return updated