import os
import re
import pandas as pd


COLUMN_ALIASES = {
    "designators": ["designator", "designators", "refdes", "ref_des", "reference", "references"],
    "qty_per_board": ["qty", "quantity", "q'ty", "bom_qty", "quantity_per_board"],
    "manufacturer": ["manufacturer", "mfg", "maker", "brand"],
    "mpn": ["part_number", "part number", "manufacturer_part_number", "manufacturer part number", "mfg_pn", "mpn"],
    "description": ["description", "item_description", "item description", "value", "comment", "notes"],
}


def load_bom(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    elif file_path.endswith(".xlsx"):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file type. Use CSV or XLSX.")

    return df


def normalize_columns(df):
    df.columns = [
        str(col).strip().lower().replace("\n", " ").replace("-", "_").replace(" ", "_")
        for col in df.columns
    ]
    return df


def map_columns(df):
    mapped = {}

    for standard_name, aliases in COLUMN_ALIASES.items():
        for col in df.columns:
            normalized_col = col.strip().lower()
            normalized_aliases = [a.strip().lower().replace(" ", "_") for a in aliases]
            if normalized_col in normalized_aliases:
                mapped[standard_name] = col
                break

    clean_df = pd.DataFrame()

    for standard_name in COLUMN_ALIASES.keys():
        if standard_name in mapped:
            clean_df[standard_name] = df[mapped[standard_name]]
        else:
            clean_df[standard_name] = ""

    return clean_df, mapped


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def count_designators(designator_text):
    """
    Simple V1 count:
    Counts comma/space/semicolon-separated refs like:
    R1,R2,R3 or R1 R2 R3
    """
    if not designator_text:
        return 0

    text = str(designator_text).strip()

    # Normalize separators
    text = text.replace(";", ",")
    text = re.sub(r"\s+", ",", text)

    parts = [p.strip() for p in text.split(",") if p.strip()]
    return len(parts)


def infer_quantity(row):
    qty = clean_text(row.get("qty_per_board", ""))
    designators = clean_text(row.get("designators", ""))

    if qty:
        try:
            return int(float(qty))
        except ValueError:
            return qty

    inferred_count = count_designators(designators)
    if inferred_count > 0:
        return inferred_count

    return ""


def determine_status(row):
    manufacturer = clean_text(row.get("manufacturer", ""))
    mpn = clean_text(row.get("mpn", ""))
    qty = clean_text(row.get("qty_per_board", ""))
    designators = clean_text(row.get("designators", ""))

    if not mpn:
        return "missing_mpn"

    if not qty and not designators:
        return "missing_quantity_info"

    if not manufacturer:
        return "review_manufacturer"

    return "clean"


def clean_rows(df):
    for col in df.columns:
        df[col] = df[col].apply(clean_text)

    df["qty_per_board"] = df.apply(infer_quantity, axis=1)
    df["status"] = df.apply(determine_status, axis=1)

    return df


def preview_bom(df, num_rows=10):
    print("\nCleaned BOM Columns:")
    print(list(df.columns))

    print(f"\nTotal Rows: {len(df)}")

    print(f"\nPreview (first {num_rows} rows):")
    print(df.head(num_rows))


def export_clean_bom(df, output_path):
    df.to_csv(output_path, index=False)