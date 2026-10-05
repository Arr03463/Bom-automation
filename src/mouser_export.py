"""
Mouser supplier-import CSV -- generated from the same canonical
purchasing lines (purchasing_lines.build_purchasing_lines()) used by the
purchasing summary counts, so a row excluded from one is excluded from
the other (see
Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md, H2/H4).

This is a DOWNLOADABLE VENDOR-IMPORT file, distinct from
sourcing_report.py's export_sourcing_report() -- that remains the rich,
all-suppliers, all-columns internal sourcing report; this file carries
only what Mouser's BOM Tool needs.

Column names verification limitation (disclosed per this project's
"verify with primary vendor documentation, or state the limitation"
policy -- see
Documentation/AutoBOM_Claude_Code_Direct_Cart_Handoff_Implementation_Prompt.md
section 5): Mouser's own BOM Tool pages
(https://www.mouser.com/en/bomtool/,
https://www.mouser.com/en/help/tools/how-to-create-a-new-bom) could not
be fetched from this environment (repeated timeouts, 2026-09-28), and
secondary sources describe Mouser's importer as accepting an uploaded
spreadsheet through a flexible, rememberable COLUMN-MAPPING step rather
than documenting one fixed required header set. The headers below
("Mouser Part Number", "Quantity", "Customer Reference") use Mouser's
OWN confirmed-live Cart API field names
(MouserPartNumber/Quantity/CustomerPartNumber -- see
mouser_cart_client.py's build_mouser_cart_items(), confirmed live
2026-09-25) translated to plain column headers, which should map
cleanly during Mouser's own import column-mapping step. This is a
best-effort, NOT an independently verified fixed-schema vendor contract
the way the DigiKey FastAdd URL format is -- re-verify directly against
Mouser's current BOM Tool before relying on this for high-volume
production use.
"""

import csv
import os

from purchasing_lines import build_purchasing_lines

MOUSER_IMPORT_HEADERS = [
    "Mouser Part Number",
    "Manufacturer Part Number",
    "Quantity",
    "Customer Reference",
]


def export_mouser_list(clean_bom, output_folder, file_stem="mouser_export", run_id=""):
    """
    Returns (output_path, PurchasingLineResult) -- mirrors
    digikey_list_export.export_digikey_list()'s shape/behavior exactly
    (same established pattern, not a new one), including producing an
    empty (header-only) CSV, not an error, when there are no
    Mouser-sourced rows yet. Callers must check `result.is_valid` before
    treating this artifact as successfully current.
    """
    os.makedirs(output_folder, exist_ok=True)
    result = build_purchasing_lines(clean_bom, "mouser", run_id=run_id)

    output_path = os.path.join(output_folder, f"{file_stem}.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(MOUSER_IMPORT_HEADERS)
        for line in result.lines:
            writer.writerow(
                [
                    line.supplier_part_number,
                    line.mpn,
                    line.quantity,
                    line.customer_reference,
                ]
            )

    return output_path, result
