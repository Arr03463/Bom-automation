import os

from bom_cleaner import (
    load_bom,
    normalize_columns,
    map_columns,
    clean_rows,
    preview_bom,
    export_clean_bom,
)
from config import INPUT_FOLDER, OUTPUT_FOLDER, OUTPUT_CLEAN_BOM_NAME


def main():
    print("BOM Automation Tool Started")

    file_name = input("Enter BOM file name (example: bom.csv or bom.xlsx): ").strip()
    file_path = os.path.join(INPUT_FOLDER, file_name)

    try:
        raw_df = load_bom(file_path)
        raw_df = normalize_columns(raw_df)

        clean_df, mapped_columns = map_columns(raw_df)
        clean_df = clean_rows(clean_df)

        print("\nMapped Columns:")
        for standard, original in mapped_columns.items():
            print(f"{standard} -> {original}")

        preview_bom(clean_df)

        output_path = os.path.join(OUTPUT_FOLDER, OUTPUT_CLEAN_BOM_NAME)
        export_clean_bom(clean_df, output_path)

        print(f"\nCleaned BOM exported to: {output_path}")

    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()