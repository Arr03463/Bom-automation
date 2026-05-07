import os


SOURCING_COLUMNS = [
    "manufacturer",
    "mpn",
    "required_qty",
    "selected_supplier",
    "supplier_order_qty",
    "mouser_stock",
    "digikey_stock",
    "sourcing_status",
    "sourcing_notes",
]


def export_sourcing_report(clean_bom, output_folder, file_stem="sourcing_report"):
    os.makedirs(output_folder, exist_ok=True)

    output_path = os.path.join(output_folder, f"{file_stem}.csv")

    available_columns = [
        col for col in SOURCING_COLUMNS
        if col in clean_bom.columns
    ]

    clean_bom[available_columns].to_csv(output_path, index=False)
    return output_path