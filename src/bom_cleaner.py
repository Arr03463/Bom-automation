import os
import pandas as pd


def load_bom(file_path):
    """
    Load a BOM file from CSV or Excel and return a pandas DataFrame.
    """
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
    """
    Clean up BOM column names so they're easier to work with.
    """
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def preview_bom(df, num_rows=5):
    """
    Print basic BOM preview info.
    """
    print("\nBOM Columns:")
    print(list(df.columns))

    print(f"\nTotal Rows: {len(df)}")

    print(f"\nPreview (first {num_rows} rows):")
    print(df.head(num_rows))