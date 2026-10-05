"""
DigiKey supplier-import CSV -- generated from the same canonical
purchasing lines (purchasing_lines.build_purchasing_lines()) used by the
DigiKey FastAdd cart link and the purchasing summary counts, so a row
excluded from one is excluded from all of them (see
Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md, H2/H4).

This is a DOWNLOADABLE VENDOR-IMPORT file, distinct from
sourcing_report.py's export_sourcing_report() -- that remains the rich,
all-suppliers, all-columns internal sourcing report; this file carries
only what DigiKey's own import tooling needs.

Column headers confirmed 2026-09-28 against a real DigiKey-format BOM
export located via web search
(https://github.com/im-tomu/tomu-hardware/blob/master/bom-digikey.csv,
header row: "Digi-Key Part Number,Manufacturer,Manufacturer Part
Number,Customer Reference,Quantity 1,Quantity 2,Quantity 3,Mfg Std Lead
Time,Description,Comments,RoHS Status,Lead Free Status,REACH Status")
and DigiKey's BOM Manager documentation (which allows the operator to
choose which quantity column an upload should use). This is the
identifier/quantity/reference subset of that real column set, using a
single Quantity column (AutoBOM has exactly one order quantity per
line) -- NOT independently confirmed via a live DigiKey upload from this
environment (no DigiKey account/cart access here). Column order matches
the confirmed real file exactly, for maximum compatibility with a
re-import into DigiKey's own tooling.
"""

import csv
import os

from purchasing_lines import build_purchasing_lines

DIGIKEY_IMPORT_HEADERS = [
    "Digi-Key Part Number",
    "Manufacturer",
    "Manufacturer Part Number",
    "Customer Reference",
    "Quantity",
]


def export_digikey_list(clean_bom, output_folder, file_stem="digikey_list", run_id=""):
    """
    Returns (output_path, PurchasingLineResult) -- callers must check
    `result.is_valid` (empty `.errors`) before treating this artifact as
    successfully current; a nonempty `.errors` means at least one row
    that IS DigiKey-sourced and not DNP has an unusable supplier part
    number or quantity, and must block Ready (see
    workflow_runner.py's artifact-status handling).
    """
    os.makedirs(output_folder, exist_ok=True)
    result = build_purchasing_lines(clean_bom, "digikey", run_id=run_id)

    output_path = os.path.join(output_folder, f"{file_stem}.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(DIGIKEY_IMPORT_HEADERS)
        for line in result.lines:
            writer.writerow(
                [
                    line.supplier_part_number,
                    line.manufacturer,
                    line.mpn,
                    line.customer_reference,
                    line.quantity,
                ]
            )

    return output_path, result
