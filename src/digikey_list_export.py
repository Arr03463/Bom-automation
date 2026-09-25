import os
import pandas as pd


DIGIKEY_COLUMNS = [
    "mpn",
    "manufacturer",
    "required_qty",
    "supplier_order_qty",
    "selected_supplier",
    "sourcing_status",
    "sourcing_notes",
    "customer_reference",
]


def export_digikey_list(clean_bom, output_folder, file_stem="digikey_list"):
    os.makedirs(output_folder, exist_ok=True)

    if "selected_supplier" in clean_bom.columns:
        digikey_rows = clean_bom[
            clean_bom["selected_supplier"].astype(str).str.lower() == "digikey"
        ].copy()
    else:
        # Sourcing hasn't run yet for this BOM (selected_supplier doesn't
        # exist as a column) -- there are no DigiKey-selected rows to
        # export, not an error. clean_bom.get("selected_supplier", "")
        # previously returned the plain string "" here instead of a
        # Series, which crashed on .astype().
        digikey_rows = clean_bom.iloc[0:0].copy()

    output_path = os.path.join(output_folder, f"{file_stem}.csv")

    available_columns = [
        col for col in DIGIKEY_COLUMNS
        if col in digikey_rows.columns
    ]

    digikey_rows[available_columns].to_csv(output_path, index=False)

    return output_path, len(digikey_rows)