import os

from bom_cleaner import (
    build_output_paths,
    export_clean_bom_workbook,
    process_bom_file,
    preview_bom,
    export_clean_bom,
)
from config import (
    INPUT_FOLDER,
    OUTPUT_FOLDER,
    OUTPUT_CLEAN_BOM_SUFFIX,
    OUTPUT_CLEAN_WORKBOOK_SUFFIX,
)


def main():
    print("BOM Automation Tool Started")

    file_name = input("Enter BOM file name (example: bom.csv or bom.xlsx): ").strip()
    file_path = os.path.join(INPUT_FOLDER, file_name)

    try:
        result = process_bom_file(file_path)

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


if __name__ == "__main__":
    main()
