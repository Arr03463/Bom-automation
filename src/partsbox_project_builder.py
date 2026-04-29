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