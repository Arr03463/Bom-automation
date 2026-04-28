import os

from mouser_client import MouserClient
from digikey_client import DigiKeyClient
from sourcing_engine import apply_sourcing_decisions
from sourcing_report import export_sourcing_report

from partsbox_project_builder import (
    create_partsbox_project_and_storage,
    export_partsbox_import_csv,
)

from bom_cleaner import (
    build_output_paths,
    export_clean_bom_workbook,
    process_bom_file,
    preview_bom,
    export_clean_bom,
    apply_project_quantities,
)
from config import (
    INPUT_FOLDER,
    OUTPUT_FOLDER,
    OUTPUT_CLEAN_BOM_SUFFIX,
    OUTPUT_CLEAN_WORKBOOK_SUFFIX,
)
from supplier_matcher import enrich_bom_with_supplier_offers


REVIEW_STATUSES = {
    "missing_mpn",
    "missing_manufacturer",
    "qty_mismatch",
    "manual_review",
}

SUPPLIER_REVIEW_STATUSES = {
    "error",
    "no_offer",
    "shortage",
    "skipped",
}

SOURCING_REVIEW_STATUSES = {
    "check_wall_inventory",
    "manual_review",
    "no_supplier_match",
}


def main():
    print("BOM Automation Tool Started")

    file_name = input("Enter BOM file name (example: bom.csv or bom.xlsx): ").strip()
    file_path = os.path.join(INPUT_FOLDER, file_name)

    build_quantity_text = input("Enter build quantity: ").strip()
    overage_percent_text = input("Enter overage percent (example 10 for 10%): ").strip()
    partsbox_choice = input("Create PartsBox project/storage and import file? (y/n): ").strip().lower()
    try:
        build_quantity = int(build_quantity_text)
        overage_percent = float(overage_percent_text)
    except ValueError:
        print("\nError: Build quantity must be an integer and overage percent must be a number.")
        return

    try:
        result = process_bom_file(file_path)

        result.clean_bom = apply_project_quantities(
            result.clean_bom,
            build_quantity,
            overage_percent,
        )
        sourcing_choice = input("Run Mouser/DigiKey sourcing check? (y/n): ").strip().lower()

        if sourcing_choice == "y":
            print("\nRunning Mouser/DigiKey sourcing check...")

            mouser = MouserClient()
            digikey = DigiKeyClient()

            result.clean_bom = apply_sourcing_decisions(
                result.clean_bom,
                mouser_lookup=mouser.find_best_match,
                digikey_lookup=digikey.find_best_match,
            )

            source_stem = os.path.splitext(os.path.basename(file_path))[0]
            sourcing_report_path = export_sourcing_report(
                result.clean_bom,
                OUTPUT_FOLDER,
                file_stem=f"{source_stem}_sourcing_report",
            )

            print(f"Sourcing report exported to: {sourcing_report_path}")

        if partsbox_choice == "y":
            project_name = input("Enter PartsBox project name: ").strip()

            if not project_name.strip():
                print("\nSkipping PartsBox: project name is required.")
            else:
                description = input("Enter project description (optional): ").strip()

                try:
                    print("\nCreating PartsBox project/storage...")
                    partsbox_result = create_partsbox_project_and_storage(
                        project_name=project_name,
                        description=description,
                    )

                    partsbox_import_path = export_partsbox_import_csv(
                        result.clean_bom,
                        project_name,
                        OUTPUT_FOLDER,
                    )

                    if partsbox_result.get("project_result", {}).get("dry_run"):
                        print("\n[DRY RUN] No project or storage was actually created.")
                    else:
                        project_result = partsbox_result.get("project_result", {})
                        storage_result = partsbox_result.get("storage_result", {})

                        if project_result.get("dry_run") or storage_result.get("dry_run"):
                            print("\n[DRY RUN] No PartsBox project or storage was actually created.")
                        else:
                            if partsbox_result.get("project_reused"):
                                print(f"PartsBox project already exists, reused: {partsbox_result['project_name']}")
                            else:
                                print(f"PartsBox project created: {partsbox_result['project_name']}")

                            if partsbox_result.get("storage_reused"):
                                print(f"PartsBox storage already exists, reused: {partsbox_result['storage_name']}")
                            else:
                                print(f"PartsBox storage created: {partsbox_result['storage_name']}")

                    
                    print(f"PartsBox import CSV exported to: {partsbox_import_path}")
                    
                except Exception as partsbox_error:
                    print(f"\nPartsBox step failed: {partsbox_error}")
                    print("Continuing with cleaned BOM export.")

        #if enrich_choice == "y":
         #   print("\nSearching supplier offers with Nexar...")
        #    result.clean_bom = enrich_bom_with_supplier_offers(result.clean_bom)

        result.review_items = build_review_items(result.clean_bom)

        print("\nMapped Columns:")
        for standard, original in result.mapped_columns.items():
            print(f"{standard} -> {original}")

        preview_bom(result.clean_bom)

        workbook_path, csv_path = build_output_paths(
            file_path,
            OUTPUT_FOLDER,
            workbook_suffix=OUTPUT_CLEAN_WORKBOOK_SUFFIX,
            csv_suffix=OUTPUT_CLEAN_BOM_SUFFIX,
        )
        export_clean_bom_workbook(result, workbook_path)
        export_clean_bom(result.clean_bom, csv_path)

        print(f"\nCleaned workbook exported to: {workbook_path}")
        print(f"Cleaned CSV exported to: {csv_path}")
        print(f"Review items: {len(result.review_items)}")
        print(f"Warnings: {len(result.warnings)}")

    except Exception as e:
        print(f"\nError: {e}")


def build_review_items(clean_bom):
    review_mask = clean_bom["status"].isin(REVIEW_STATUSES)

    if "supplier_match_status" in clean_bom.columns:
        review_mask = review_mask | clean_bom["supplier_match_status"].isin(
            SUPPLIER_REVIEW_STATUSES
        )

    if "sourcing_status" in clean_bom.columns:
        review_mask = review_mask | clean_bom["sourcing_status"].isin(
            SOURCING_REVIEW_STATUSES
        )

    return clean_bom[review_mask].copy()


if __name__ == "__main__":
    main()
