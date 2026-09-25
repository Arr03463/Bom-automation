import os
import re
from dataclasses import dataclass, field

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
        "storage_name": clean_name,
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

    if qty_per_board is None:
        return None

    return qty_per_board


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
    """
    Builds PartsBox entries AND writes partsbox_match_status/
    partsbox_part_id back onto clean_bom (by row index) so the canonical
    BOM state carries per-row PartsBox match info -- the Results
    Workspace's Source/Status model reads these columns rather than
    recomputing PartsBox matching separately.
    """
    entries = []
    unmatched_rows = []

    if "partsbox_match_status" not in clean_bom.columns:
        clean_bom["partsbox_match_status"] = ""
    if "partsbox_part_id" not in clean_bom.columns:
        clean_bom["partsbox_part_id"] = ""

    for order_number, (index, row) in enumerate(clean_bom.iterrows(), start=1):
        mpn = str(row.get("mpn", "") or "").strip()
        manufacturer = str(row.get("manufacturer", "") or "").strip()
        quantity = calculate_project_entry_quantity(row)

        unmatched_row = row.to_dict()
        unmatched_row["partsbox_match_status"] = "unmatched"

        if quantity is None:
            unmatched_row["partsbox_match_notes"] = "Missing or invalid BOM quantity."
            unmatched_rows.append(unmatched_row)
            clean_bom.at[index, "partsbox_match_status"] = "unmatched"
            continue

        part = None

        if mpn:
            part = client.find_part_by_mpn_and_manufacturer(mpn, manufacturer)

        if part:
            entries.append(build_project_entry(row, order_number, part=part))
            clean_bom.at[index, "partsbox_match_status"] = "matched"
            clean_bom.at[index, "partsbox_part_id"] = part.get("part/id", "")
        else:
            if mpn:
                match_note = "No PartsBox part matched MPN/manufacturer."
            else:
                match_note = "Missing MPN; manual PartsBox match required."

            entries.append(build_project_entry(row, order_number, match_note=match_note))
            unmatched_row["partsbox_match_notes"] = match_note
            unmatched_rows.append(unmatched_row)
            clean_bom.at[index, "partsbox_match_status"] = "unmatched"

    return entries, unmatched_rows


def _entry_identity(entry):
    """
    Identity used to decide whether a built entry already exists in the
    project -- deliberately EXCLUDES quantity. Matched parts are
    identified by PartsBox part ID; unmatched rows (no part-id) fall back
    to name, since that is the only stable field build_project_entry()
    gives them. Designators are included so two different rows for the
    same part are not treated as duplicates of each other.

    Because quantity is excluded, two entries can share an identity while
    disagreeing on quantity -- callers must check that separately (see
    add_bom_entries_to_project) rather than treating identity-match as
    "fully in sync."
    """
    designators = tuple(sorted(str(d) for d in (entry.get("entry/designators") or [])))
    part_id = entry.get("entry/part-id")

    if part_id:
        return ("part", str(part_id), designators)

    name = str(entry.get("entry/name") or "").strip().lower()
    return ("name", name, designators)


def _quantities_equal(existing_quantity, intended_quantity):
    try:
        return float(existing_quantity) == float(intended_quantity)
    except (TypeError, ValueError):
        return existing_quantity == intended_quantity


@dataclass
class ExistingEntriesExtraction:
    """
    recognized=True means this response shape was understood -- entries
    may legitimately be an empty list for a project with no entries yet.
    recognized=False means the response could not be interpreted at all
    (wrong type, missing/non-list envelope key) and entries is always
    empty in that case; callers must fail closed rather than treat that
    as "confirmed no entries."
    """

    recognized: bool
    entries: list = field(default_factory=list)


def _extract_existing_entries(get_entries_response):
    """
    The live project/get-entries response shape has not been verified
    against the PartsBox API (per the Codex audit). Distinguish a
    recognized envelope -- including a genuinely empty project, which is
    valid -- from one this client cannot interpret, so an unrecognized
    shape can be fail-closed by the caller instead of silently treated as
    "no entries" (which would risk re-adding entries that already exist).
    """
    if not isinstance(get_entries_response, dict):
        return ExistingEntriesExtraction(recognized=False)

    for key in ("data", "entries", "project/entries"):
        if key not in get_entries_response:
            continue

        records = get_entries_response[key]
        if isinstance(records, list):
            return ExistingEntriesExtraction(recognized=True, entries=records)

        # The key we expected exists but is not a list -- don't guess at
        # what it means.
        return ExistingEntriesExtraction(recognized=False)

    return ExistingEntriesExtraction(recognized=False)


def add_bom_entries_to_project(partsbox_result, clean_bom, client=None):
    project_id = extract_project_id(partsbox_result)

    if not project_id:
        return {
            "skipped": True,
            "message": "No PartsBox project ID found; entries were not added.",
            "entries_added": 0,
            "entries_skipped_existing": 0,
            "entries_considered": 0,
            "quantity_mismatches": [],
            "unmatched_rows": [],
        }

    client = client or PartsBoxClient()
    entries, unmatched_rows = build_project_entries(clean_bom, client)

    extraction = _extract_existing_entries(client.get_project_entries(project_id))

    if not extraction.recognized:
        return {
            "skipped": True,
            "message": (
                "PartsBox project/get-entries response was not in a recognized "
                "shape; no entries were added to avoid risking duplicates. "
                "Verify the current PartsBox API response schema before "
                "retrying."
            ),
            "entries_added": 0,
            "entries_skipped_existing": 0,
            "entries_considered": len(entries),
            "quantity_mismatches": [],
            "unmatched_rows": unmatched_rows,
            "unrecognized_response": True,
        }

    existing_by_identity = {}
    for existing_entry in extraction.entries:
        if isinstance(existing_entry, dict):
            existing_by_identity[_entry_identity(existing_entry)] = existing_entry

    new_entries = []
    quantity_mismatches = []
    entries_skipped_existing = 0

    for entry in entries:
        existing_entry = existing_by_identity.get(_entry_identity(entry))

        if existing_entry is None:
            new_entries.append(entry)
            continue

        existing_quantity = existing_entry.get("entry/quantity")
        intended_quantity = entry.get("entry/quantity")

        if _quantities_equal(existing_quantity, intended_quantity):
            entries_skipped_existing += 1
            continue

        # Same logical part/designators, different quantity: do not
        # silently skip (that would leave PartsBox stale) and do not
        # append a duplicate entry (no verified PartsBox update operation
        # exists for this yet). Surface it instead.
        quantity_mismatches.append(
            {
                "entry_name": entry.get("entry/name"),
                "part_id": entry.get("entry/part-id"),
                "designators": entry.get("entry/designators"),
                "existing_quantity": existing_quantity,
                "intended_quantity": intended_quantity,
            }
        )

    add_result = None

    if new_entries:
        add_result = client.add_project_entries(project_id, new_entries)

    return {
        "skipped": False,
        "project_id": project_id,
        "entries_added": len(new_entries),
        "entries_skipped_existing": entries_skipped_existing,
        "entries_considered": len(entries),
        "quantity_mismatches": quantity_mismatches,
        "unmatched_rows": unmatched_rows,
        "add_result": add_result,
    }

PRODUCTION_STORAGE_TAG = "production"


def storage_has_tag(storage_record, tag):
    """
    Shared production-tag detection: used both by the PartsBox project
    lifecycle below (deciding storage_tag_missing) and by the PartsBox
    Inventory UI's Storage Locations view (app.py), so the two never
    duplicate this check with diverging logic.

    Confirmed live (2026-09-24, real storage/all response, 1888 storage
    records): "storage/tags" is a plain list of plain strings when
    present (e.g. ["Production"]), and the KEY IS ABSENT ENTIRELY (not an
    empty list) on records with no tags -- confirmed across several
    distinct field-presence combinations. Tag values are not
    lowercase-normalized by the API ("Production", not "production"),
    confirming the .strip().lower() normalization below is load-bearing.
    """
    if not isinstance(storage_record, dict):
        return False

    tags = storage_record.get("storage/tags") or storage_record.get("tags") or []
    if not isinstance(tags, (list, tuple, set)):
        return False

    normalized_tags = {str(item).strip().lower() for item in tags}
    return tag.strip().lower() in normalized_tags


def create_partsbox_project_and_storage(project_name, description="", client=None):
    client = client or PartsBoxClient()
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

    storage_tag_missing = False

    if existing_storage:
        storage_result = {
            "reused": True,
            "message": "Storage already exists; reusing existing storage.",
            "storage": existing_storage,
        }
        # No PartsBox API for updating tags on an existing storage location
        # is implemented/confirmed here; surface the gap instead of
        # inventing an endpoint. See partsbox_client.py.
        storage_tag_missing = not storage_has_tag(existing_storage, PRODUCTION_STORAGE_TAG)
    else:
        storage_result = client.create_storage_location(
            name=names["storage_name"],
            tags=[PRODUCTION_STORAGE_TAG],
            #description=f"Incoming parts storage for {names['project_name']}",
        )

    return {
        "project_name": names["project_name"],
        "storage_name": names["storage_name"],
        "project_result": project_result,
        "storage_result": storage_result,
        "project_reused": bool(existing_project),
        "storage_reused": bool(existing_storage),
        "storage_tag_missing": storage_tag_missing,
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
