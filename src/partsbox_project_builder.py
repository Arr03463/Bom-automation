import os
import re
import pandas as pd

from partsbox_client import PartsBoxClient


def make_safe_name(value):
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def build_default_names(project_name):
    clean_name = make_safe_name(project_name)

    return {
        "project_name": clean_name,
        "storage_name": f"{clean_name} - Incoming Parts",
        "import_file_name": re.sub(r"[^A-Za-z0-9._-]+", "_", clean_name).strip("_")
        + "_partsbox_import.csv",
    }

def extract_project_id(partsbox_result):
    project_result = partsbox_result.get("project_result", {})

    return (
        project_result.get("project/id")
        or project_result.get("data", {}).get("project/id")
        or project_result.get("project", {}).get("project/id")
    )


def split_designators(value):
    text = str(value or "").replace(";", ",")
    chunks = []

    for part in text.split(","):
        chunks.extend(part.strip().split())

    return [item.strip() for item in chunks if item.strip()]


def parse_quantity(value):
    try:
        if value is None or value == "":
            return None

        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def calculate_project_entry_quantity(row):
    qty_per_board = parse_quantity(row.get("qty_per_board", ""))
    build_quantity = parse_quantity(row.get("build_quantity", ""))

    if qty_per_board is None or build_quantity is None:
        return None

    return qty_per_board * build_quantity


def build_entry_name(mpn, description, order_number):
    if mpn:
        return mpn

    if description:
        return description[:80]

    return f"Unmatched BOM row {order_number}"


def build_entry_comments(description, manufacturer, mpn, match_note=""):
    comments = []

    if match_note:
        comments.append(f"UNMATCHED: {match_note}")

    if manufacturer:
        comments.append(f"Manufacturer: {manufacturer}")

    if mpn:
        comments.append(f"MPN: {mpn}")

    if description:
        comments.append(f"Description: {description}")

    return "\n".join(comments)


def build_project_entry(row, order_number, part=None, match_note=""):
    mpn = str(row.get("mpn", "") or "").strip()
    manufacturer = str(row.get("manufacturer", "") or "").strip()
    description = str(row.get("description", "") or "").strip()
    quantity = calculate_project_entry_quantity(row)

    if quantity is None:
        return None

    entry = {
        "entry/quantity": quantity,
        "entry/name": build_entry_name(mpn, description, order_number),
        "entry/comments": build_entry_comments(
            description,
            manufacturer,
            mpn,
            match_note=match_note,
        ),
        "entry/designators": split_designators(row.get("designators", "")),
        "entry/order": order_number,
    }

    if part:
        entry["entry/part-id"] = part["part/id"]
        entry["entry/comments"] = description

    return entry


def build_project_entries(clean_bom, client):
    entries = []
    unmatched_rows = []

    for order_number, (_, row) in enumerate(clean_bom.iterrows(), start=1):
        mpn = str(row.get("mpn", "") or "").strip()
        manufacturer = str(row.get("manufacturer", "") or "").strip()
        quantity = calculate_project_entry_quantity(row)

        unmatched_row = row.to_dict()
        unmatched_row["partsbox_match_status"] = "unmatched"

        if quantity is None:
            unmatched_row["partsbox_match_notes"] = "Missing or invalid BOM/build quantity."
            unmatched_rows.append(unmatched_row)
            continue

        part = None

        if mpn:
            part = client.find_part_by_mpn_and_manufacturer(mpn, manufacturer)

        if part:
            entries.append(build_project_entry(row, order_number, part=part))
        else:
            if mpn:
                match_note = "No PartsBox part matched MPN/manufacturer."
            else:
                match_note = "Missing MPN; manual PartsBox match required."

            entries.append(build_project_entry(row, order_number, match_note=match_note))
            unmatched_row["partsbox_match_notes"] = match_note
            unmatched_rows.append(unmatched_row)

    return entries, unmatched_rows


def add_bom_entries_to_project(partsbox_result, clean_bom):
    project_id = extract_project_id(partsbox_result)

    if not project_id:
        return {
            "skipped": True,
            "message": "No PartsBox project ID found; entries were not added.",
            "entries_added": 0,
            "unmatched_rows": [],
        }

    client = PartsBoxClient()
    entries, unmatched_rows = build_project_entries(clean_bom, client)

    add_result = None

    if entries:
        add_result = client.add_project_entries(project_id, entries)

    return {
        "skipped": False,
        "project_id": project_id,
        "entries_added": len(entries),
        "unmatched_rows": unmatched_rows,
        "add_result": add_result,
    }

def create_partsbox_project_and_storage(project_name, description=""):
    client = PartsBoxClient()
    names = build_default_names(project_name)

    existing_project = client.find_project_by_name(names["project_name"])
    existing_storage = client.find_storage_by_name(names["storage_name"])

    if existing_project:
        project_result = {
            "reused": True,
            "message": "Project already exists; reusing existing project.",
            "project": existing_project,
        }
    else:
        project_result = client.create_project(
            name=names["project_name"],
            description=description,
           # notes="Created by BOM automation tool.",
            #tags=["bom-automation"],
        )

    if existing_storage:
        storage_result = {
            "reused": True,
            "message": "Storage already exists; reusing existing storage.",
            "storage": existing_storage,
        }
    else:
        storage_result = client.create_storage_location(
            name=names["storage_name"],
            #description=f"Incoming parts storage for {names['project_name']}",
            #tags=["bom-automation", "incoming"],
        )

    return {
        "project_name": names["project_name"],
        "storage_name": names["storage_name"],
        "project_result": project_result,
        "storage_result": storage_result,
        "project_reused": bool(existing_project),
        "storage_reused": bool(existing_storage),
    }


def export_partsbox_import_csv(clean_bom, project_name, output_folder):
    names = build_default_names(project_name)
    output_path = os.path.join(output_folder, names["import_file_name"])

    export_df = pd.DataFrame()

    export_df["Designators"] = clean_bom.get("designators", "")
    export_df["Quantity"] = clean_bom.get("qty_per_board", "")
    export_df["Manufacturer"] = clean_bom.get("manufacturer", "")
    export_df["MPN"] = clean_bom.get("mpn", "")
    export_df["Description"] = clean_bom.get("description", "")
    export_df["Required Qty"] = clean_bom.get("required_qty", "")
    export_df["Notes"] = clean_bom.get("notes", "")

    os.makedirs(output_folder, exist_ok=True)
    export_df.to_csv(output_path, index=False)

    return output_path


def export_partsbox_unmatched_csv(unmatched_rows, project_name, output_folder):
    if not unmatched_rows:
        return None

    names = build_default_names(project_name)
    unmatched_file_name = names["import_file_name"].replace(
        "_partsbox_import.csv",
        "_partsbox_unmatched.csv",
    )
    output_path = os.path.join(output_folder, unmatched_file_name)

    os.makedirs(output_folder, exist_ok=True)
    pd.DataFrame(unmatched_rows).to_csv(output_path, index=False)

    return output_path
