import os


MOUSER_EXPORT_COLUMNS = [
    "mpn",
    "manufacturer",
    "required_qty",
    "supplier_order_qty",
    "selected_supplier",
    "supplier_part_number",
    "sourcing_status",
    "sourcing_notes",
    "customer_reference",
]


def export_mouser_list(clean_bom, output_folder, file_stem="mouser_export"):
    """
    Downloadable Mouser-sourced parts list -- the current operator-facing
    Mouser handoff. The operator uploads this file to Mouser manually;
    AutoBOM does not call the Mouser Cart API as part of the normal
    workflow (see mouser_cart_client.py, preserved unchanged for a
    possible future supported share-link integration, not wired into
    this path).

    Mirrors digikey_list_export.export_digikey_list()'s shape/behavior
    exactly (same column selection approach, same (path, count) return),
    so this is the second instance of an established pattern, not a new
    one -- including producing an empty (header-only) CSV, not an error,
    when there are no Mouser-sourced rows yet.
    """
    os.makedirs(output_folder, exist_ok=True)

    if "selected_supplier" in clean_bom.columns:
        mouser_rows = clean_bom[
            clean_bom["selected_supplier"].astype(str).str.lower() == "mouser"
        ].copy()
    else:
        # Sourcing hasn't run yet for this BOM (selected_supplier doesn't
        # exist as a column) -- there are no Mouser-selected rows to
        # export, not an error.
        mouser_rows = clean_bom.iloc[0:0].copy()

    output_path = os.path.join(output_folder, f"{file_stem}.csv")

    available_columns = [col for col in MOUSER_EXPORT_COLUMNS if col in mouser_rows.columns]
    mouser_rows[available_columns].to_csv(output_path, index=False)

    return output_path, len(mouser_rows)
