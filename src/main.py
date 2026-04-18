import os

from bom_cleaner import load_bom, normalize_columns, preview_bom
from config import INPUT_FOLDER


def main():
    print("BOM Automation Tool Started")

    file_name = input("Enter BOM file name (example: bom.csv or bom.xlsx): ").strip()
    file_path = os.path.join(INPUT_FOLDER, file_name)

    try:
        df = load_bom(file_path)
        df = normalize_columns(df)
        preview_bom(df)
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()