import os

from mouser_client import MouserClient
from mouser_cart_client import create_mouser_cart_from_bom
from digikey_client import DigiKeyClient
from digikey_mylists_client import create_digikey_mylist_from_bom
from sourcing_engine import apply_sourcing_decisions
from sourcing_report import export_sourcing_report

from digikey_list_export import export_digikey_list


from partsbox_project_builder import (
    add_bom_entries_to_project,
    create_partsbox_project_and_storage,
    export_partsbox_import_csv,
    export_partsbox_unmatched_csv,
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
}


def main():
    print("BOM Automation Tool Started")

    mouser_cart_items = 0
    digikey_list_items = 0
    partsbox_entries_added = 0

    file_name = input("Enter BOM file name (example: bom.csv or bom.xlsx): ").strip()
    file_path = os.path.join(INPUT_FOLDER, file_name)

    build_quantity_text = input("Enter build quantity: ").strip()
    project_name = input("Enter project name: ").strip()
    partsbox_choice = input("Run PartsBox project/storage flow? (y/n): ").strip().lower()
    sourcing_choice = input("Run Mouser/DigiKey sourcing check? (y/n): ").strip().lower()
    carts_lists_choice = input("Create carts/lists? (y/n): ").strip().lower()
    try:
        build_quantity = int(build_quantity_text)
    except ValueError:
        print("\nError: Build quantity must be an integer.")
        return

    try:
        result = process_bom_file(file_path)

        result.clean_bom = apply_project_quantities(
            result.clean_bom,
            build_quantity,
        )
        source_stem = os.path.splitext(os.path.basename(file_path))[0]
        list_name_base = project_name or source_stem

        if sourcing_choice == "y":
            print("\nRunning Mouser/DigiKey sourcing check...")

            supplier_mode = os.getenv("SUPPLIER_MODE", "mouser_then_digikey").strip().lower()

            digikey = DigiKeyClient()

            if supplier_mode == "digikey_only":
                print("Supplier mode: DigiKey only")

                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=lambda row: None,
                    digikey_lookup=digikey.find_best_match_for_row,
                )
            else:
                print("Supplier mode: Mouser first, DigiKey fallback")

                mouser = MouserClient()

                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=mouser.find_best_match_for_row,
                    digikey_lookup=digikey.find_best_match_for_row,
                )

            sourcing_report_path = export_sourcing_report(
                result.clean_bom,
                OUTPUT_FOLDER,
                file_stem=f"{source_stem}_sourcing_report",
            )

            print(f"Sourcing report exported to: {sourcing_report_path}")

            if (
                carts_lists_choice == "y"
                and os.getenv("MOUSER_CART_ENABLED", "false").lower() == "true"
            ):
                try:
                    mouser_cart_result = create_mouser_cart_from_bom(result.clean_bom)

                    if mouser_cart_result.get("created"):
                        print(f"Mouser cart items prepared: {mouser_cart_result.get('items_count')}")
                        mouser_cart_items = mouser_cart_result.get("items_count", 0)
                        print(f"Mouser cart result: {mouser_cart_result.get('result')}")
                    else:
                        print(f"Mouser cart skipped: {mouser_cart_result.get('message')}")

                except Exception as exc:
                    print(f"Mouser cart step failed: {exc}")
                    print("Continuing with sourcing report export only.")
            elif carts_lists_choice != "y":
                print("Remote cart/list creation skipped by operator choice.")

            # STEP 1 - always export CSV first
            digikey_list_path, digikey_count = export_digikey_list(
                result.clean_bom,
                OUTPUT_FOLDER,
                file_stem=f"{source_stem}_digikey_list",
            )

            print(f"DigiKey list exported to: {digikey_list_path}")
            print(f"DigiKey list rows: {digikey_count}")
            digikey_list_items = digikey_count

            # STEP 2 - then try MyLists API
            if (
                carts_lists_choice == "y"
                and os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true"
            ):
                try:
                    digikey_mylist_result = create_digikey_mylist_from_bom(
                        result.clean_bom,
                        list_name=f"{list_name_base} DigiKey List",
                    )

                    if digikey_mylist_result.get("created"):
                        print(f"DigiKey MyList created: {digikey_mylist_result.get('list_id')}")
                        if digikey_mylist_result.get("name_changed"):
                            print(
                                "DigiKey MyList name already existed. "
                                f"Created with timestamped name: {digikey_mylist_result.get('list_name')}"
                            )
                        else:
                            print(f"DigiKey MyList name: {digikey_mylist_result.get('list_name')}")
                        print(f"DigiKey MyList parts added: {digikey_mylist_result.get('parts_count')}")
                    else:
                        print(f"DigiKey MyList skipped: {digikey_mylist_result.get('message')}")

                except Exception as exc:
                    print(f"DigiKey MyList step failed: {exc}")
                    print("Continuing with DigiKey CSV export only.")

        if partsbox_choice == "y":
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

                    partsbox_entries_result = add_bom_entries_to_project(
                        partsbox_result,
                        result.clean_bom,
                    )
                    unmatched_path = export_partsbox_unmatched_csv(
                        partsbox_entries_result.get("unmatched_rows", []),
                        project_name,
                        OUTPUT_FOLDER,
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

                            if partsbox_entries_result.get("skipped"):
                                print(f"PartsBox entries skipped: {partsbox_entries_result['message']}")
                            else:
                                print(f"PartsBox entries added: {partsbox_entries_result['entries_added']}")
                                partsbox_entries_added = partsbox_entries_result.get("entries_added", 0)

                            unmatched_count = len(partsbox_entries_result.get("unmatched_rows", []))
                            if unmatched_count:
                                print(f"PartsBox unmatched BOM rows: {unmatched_count}")
                                print(f"PartsBox unmatched CSV exported to: {unmatched_path}")

                    
                    
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

        mouser_sourced = 0
        digikey_sourced = 0
        manual_review = 0

        if "sourcing_status" in result.clean_bom.columns:
            sourcing_counts = result.clean_bom["sourcing_status"].value_counts()

            mouser_sourced = int(sourcing_counts.get("sourced_mouser", 0))
            digikey_sourced = int(sourcing_counts.get("sourced_digikey", 0))
            manual_review = int(sourcing_counts.get("check_wall_inventory", 0)) + int(
                sourcing_counts.get("manual_review", 0)
            )

        print("\nFinal Run Summary:")
        print(f"Mouser sourced: {mouser_sourced}")
        print(f"DigiKey sourced: {digikey_sourced}")
        print(f"Manual / wall review: {manual_review}")
        print(f"Mouser cart items: {mouser_cart_items}")
        print(f"DigiKey list items: {digikey_list_items}")
        print(f"PartsBox entries added: {partsbox_entries_added}")

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
