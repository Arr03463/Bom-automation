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
]


def export_digikey_list(clean_bom, output_folder, file_stem="digikey_list"):
    os.makedirs(output_folder, exist_ok=True)

    digikey_rows = clean_bom[
        clean_bom.get("selected_supplier", "").astype(str).str.lower() == "digikey"
    ].copy()

    output_path = os.path.join(output_folder, f"{file_stem}.csv")

    available_columns = [
        col for col in DIGIKEY_COLUMNS
        if col in digikey_rows.columns
    ]

    digikey_rows[available_columns].to_csv(output_path, index=False)

    return output_path, len(digikey_rows)