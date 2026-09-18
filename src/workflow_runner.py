import json
import os
from pathlib import Path

from dotenv import load_dotenv

from active_bom_state import ActiveBomState
from bom_cleaner import (
    apply_project_quantities,
    build_output_paths,
    export_clean_bom,
    export_clean_bom_workbook,
    process_bom_file,
)
from config import (
    OUTPUT_CLEAN_BOM_SUFFIX,
    OUTPUT_CLEAN_WORKBOOK_SUFFIX,
    OUTPUT_FOLDER,
)
from digikey_client import DigiKeyClient
from digikey_list_export import export_digikey_list
from digikey_mylists_client import create_digikey_mylist_from_bom
from mouser_cart_client import create_mouser_cart_from_bom
from mouser_client import MouserClient
from partsbox_project_builder import (
    add_bom_entries_to_project,
    create_partsbox_project_and_storage,
    export_partsbox_import_csv,
    export_partsbox_unmatched_csv,
)
from run_workspace import new_run_id
from sourcing_engine import apply_sourcing_decisions
from sourcing_report import export_sourcing_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _empty_result():
    return {
        "success": False,
        "errors": [],
        "warnings": [],
        "summary": {
            "mouser_sourced": 0,
            "digikey_sourced": 0,
            "manual_review": 0,
            "mouser_cart_items": 0,
            "digikey_list_items": 0,
            "partsbox_entries_added": 0,
            "review_items": 0,
            "warnings": 0,
        },
        "outputs": {
            "cleaned_workbook": "",
            "cleaned_csv": "",
            "sourcing_report": "",
            "digikey_list_csv": "",
            "partsbox_import_csv": "",
            "partsbox_unmatched_csv": "",
            "run_summary": "",
        },
        "messages": [],
        "run": {},
        "bom_rows": [],
        "review_items": [],
        "partsbox": None,
        "purchasing": {
            "mouser": None,
            "digikey": None,
        },
    }


def _append_warning_rows(response, warnings_df):
    if warnings_df is None or warnings_df.empty:
        return

    for warning in warnings_df.to_dict("records"):
        field = warning.get("field", "")
        message = warning.get("message", "")
        source_row = warning.get("source_row", "")
        prefix = f"row {source_row}: " if source_row else ""
        response["warnings"].append(f"{prefix}{field} - {message}".strip(" -"))


def _count_sourcing(clean_bom):
    if "sourcing_status" not in clean_bom.columns:
        return 0, 0, 0

    sourcing_counts = clean_bom["sourcing_status"].value_counts()
    mouser_sourced = int(sourcing_counts.get("sourced_mouser", 0))
    digikey_sourced = int(sourcing_counts.get("sourced_digikey", 0))
    manual_review = int(sourcing_counts.get("check_wall_inventory", 0)) + int(
        sourcing_counts.get("manual_review", 0)
    )

    return mouser_sourced, digikey_sourced, manual_review


def _extract_mouser_cart_key(raw_result):
    """
    Best-effort CartKey extraction. The Cart API response shape returned by
    add_items_to_cart() is not yet confirmed against a live Mouser response;
    this checks the shapes referenced in Mouser's published Cart API docs
    and falls back to None rather than guessing further.
    """
    if not isinstance(raw_result, dict):
        return None

    if raw_result.get("CartKey"):
        return raw_result["CartKey"]

    cart = raw_result.get("Cart")
    if isinstance(cart, dict) and cart.get("CartKey"):
        return cart["CartKey"]

    return None


def _build_mouser_purchasing(attempted, mouser_cart_result):
    if not attempted or mouser_cart_result is None:
        return {
            "attempted": bool(attempted),
            "created": False,
            "items_count": 0,
            "cart_key": None,
            "message": None,
            "raw_result": None,
        }

    raw_result = mouser_cart_result.get("result")

    return {
        "attempted": True,
        "created": bool(mouser_cart_result.get("created")),
        "items_count": int(mouser_cart_result.get("items_count", 0)),
        "cart_key": _extract_mouser_cart_key(raw_result),
        "message": mouser_cart_result.get("message"),
        "raw_result": raw_result,
    }


def _build_digikey_purchasing(attempted, digikey_mylist_result):
    if not attempted or digikey_mylist_result is None:
        return {
            "attempted": bool(attempted),
            "created": False,
            "list_id": None,
            "list_name": None,
            "share_id": None,
            "parts_count": 0,
            "message": None,
            "raw_create_result": None,
            "raw_add_result": None,
        }

    return {
        "attempted": True,
        "created": bool(digikey_mylist_result.get("created")),
        "list_id": digikey_mylist_result.get("list_id"),
        "list_name": digikey_mylist_result.get("list_name"),
        # DigiKey's confirmed MyLists response only returns ListId/ListName.
        # A distinct share ID/key field is not present in this repository's
        # client and must be verified against the live MyLists API before
        # a value can be surfaced here.
        "share_id": None,
        "parts_count": digikey_mylist_result.get("parts_count", 0),
        "message": digikey_mylist_result.get("message"),
        "raw_create_result": digikey_mylist_result.get("create_result"),
        "raw_add_result": digikey_mylist_result.get("add_result"),
    }


def _build_partsbox_response(partsbox_result, partsbox_entries_result):
    return {
        "project_name": partsbox_result.get("project_name"),
        "storage_name": partsbox_result.get("storage_name"),
        "project_reused": bool(partsbox_result.get("project_reused")),
        "storage_reused": bool(partsbox_result.get("storage_reused")),
        "storage_tag_missing": bool(partsbox_result.get("storage_tag_missing")),
        "project_result": partsbox_result.get("project_result"),
        "storage_result": partsbox_result.get("storage_result"),
        "entries_added": partsbox_entries_result.get("entries_added", 0),
        "entries_skipped_existing": partsbox_entries_result.get(
            "entries_skipped_existing", 0
        ),
        "entries_considered": partsbox_entries_result.get("entries_considered", 0),
        "quantity_mismatches": partsbox_entries_result.get("quantity_mismatches", []),
        "unrecognized_response": bool(
            partsbox_entries_result.get("unrecognized_response")
        ),
        "unmatched_count": len(partsbox_entries_result.get("unmatched_rows", [])),
    }


def _write_run_summary(response, source_file_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    source_stem = Path(source_file_path).stem or "bom"
    output_path = os.path.join(output_folder, f"{source_stem}_run_summary.json")

    with open(output_path, "w", encoding="utf-8") as summary_file:
        json.dump(response, summary_file, indent=2)

    response["outputs"]["run_summary"] = output_path


def run_bom_workflow(
    source_file_path,
    build_quantity,
    project_name="",
    project_description="",
    run_partsbox=True,
    run_sourcing=True,
    run_mouser_cart=False,
    run_digikey_mylist=False,
    use_mouser_sourcing=True,
    use_digikey_sourcing=True,
    run_id=None,
    output_folder=None,
):
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    response = _empty_result()
    source_file_path = str(source_file_path)
    project_name = str(project_name or "").strip()
    project_description = str(project_description or "").strip()
    run_id = run_id or new_run_id()
    output_folder = str(output_folder) if output_folder else OUTPUT_FOLDER

    response["run"] = {
        "run_id": run_id,
        "project_name": project_name,
        "build_quantity": build_quantity,
        "source_file_name": Path(source_file_path).name,
    }

    try:
        build_quantity = int(build_quantity)
    except (TypeError, ValueError):
        response["errors"].append("Build quantity must be an integer.")
        return response

    response["run"]["build_quantity"] = build_quantity

    try:
        os.makedirs(output_folder, exist_ok=True)

        result = process_bom_file(source_file_path)
        result.clean_bom = apply_project_quantities(result.clean_bom, build_quantity)
        _append_warning_rows(response, result.warnings)

        source_stem = Path(source_file_path).stem
        list_name_base = project_name or source_stem

        mouser_cart_result = None
        digikey_mylist_result = None

        if run_sourcing and (use_mouser_sourcing or use_digikey_sourcing):
            response["messages"].append("Running supplier sourcing.")
            supplier_mode = os.getenv("SUPPLIER_MODE", "mouser_then_digikey").strip().lower()
            digikey = DigiKeyClient()

            if not use_mouser_sourcing and use_digikey_sourcing:
                response["messages"].append("Supplier mode: DigiKey only.")
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=lambda row: None,
                    digikey_lookup=digikey.find_best_match_for_row,
                )
            elif use_mouser_sourcing and not use_digikey_sourcing:
                response["messages"].append("Supplier mode: Mouser only.")
                mouser = MouserClient()
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=mouser.find_best_match_for_row,
                    digikey_lookup=lambda row: None,
                )
            elif supplier_mode == "digikey_only":
                response["messages"].append("Supplier mode: DigiKey only.")
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=lambda row: None,
                    digikey_lookup=digikey.find_best_match_for_row,
                )
            else:
                response["messages"].append("Supplier mode: Mouser first, DigiKey fallback.")
                mouser = MouserClient()
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=mouser.find_best_match_for_row,
                    digikey_lookup=digikey.find_best_match_for_row,
                )

            sourcing_report_path = export_sourcing_report(
                result.clean_bom,
                output_folder,
                file_stem=f"{source_stem}_sourcing_report",
            )
            response["outputs"]["sourcing_report"] = sourcing_report_path
            response["messages"].append(f"Sourcing report exported to: {sourcing_report_path}")

            if run_mouser_cart:
                if os.getenv("MOUSER_CART_ENABLED", "false").lower() == "true":
                    try:
                        mouser_cart_result = create_mouser_cart_from_bom(result.clean_bom)
                        response["summary"]["mouser_cart_items"] = int(
                            mouser_cart_result.get("items_count", 0)
                        )
                        if mouser_cart_result.get("created"):
                            response["messages"].append(
                                f"Mouser cart items prepared: {response['summary']['mouser_cart_items']}"
                            )
                        else:
                            response["messages"].append(
                                f"Mouser cart skipped: {mouser_cart_result.get('message')}"
                            )
                    except Exception as exc:
                        response["errors"].append(f"Mouser cart step failed: {exc}")
                else:
                    response["messages"].append("Mouser cart skipped: MOUSER_CART_ENABLED is not true.")
            else:
                response["messages"].append("Mouser cart creation skipped.")

            digikey_list_path, digikey_count = export_digikey_list(
                result.clean_bom,
                output_folder,
                file_stem=f"{source_stem}_digikey_list",
            )
            response["outputs"]["digikey_list_csv"] = digikey_list_path
            response["summary"]["digikey_list_items"] = int(digikey_count)
            response["messages"].append(f"DigiKey list exported to: {digikey_list_path}")

            if run_digikey_mylist:
                if os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true":
                    try:
                        digikey_mylist_result = create_digikey_mylist_from_bom(
                            result.clean_bom,
                            list_name=f"{list_name_base} DigiKey List",
                        )
                        if digikey_mylist_result.get("created"):
                            response["messages"].append(
                                f"DigiKey MyList created: {digikey_mylist_result.get('list_id')}"
                            )
                            response["messages"].append(
                                f"DigiKey MyList parts added: {digikey_mylist_result.get('parts_count', 0)}"
                            )
                        else:
                            response["messages"].append(
                                f"DigiKey MyList skipped: {digikey_mylist_result.get('message')}"
                            )
                    except Exception as exc:
                        response["errors"].append(f"DigiKey MyList step failed: {exc}")
                else:
                    response["messages"].append(
                        "DigiKey MyList skipped: DIGIKEY_MYLISTS_ENABLED is not true."
                    )
            else:
                response["messages"].append("DigiKey MyList creation skipped.")
        elif run_sourcing:
            response["messages"].append("Supplier sourcing skipped: no suppliers selected.")
        else:
            response["messages"].append("Supplier sourcing skipped.")

        if run_partsbox:
            if not project_name:
                response["errors"].append("PartsBox skipped: project name is required.")
            else:
                try:
                    partsbox_result = create_partsbox_project_and_storage(
                        project_name=project_name,
                        description=project_description,
                    )
                    partsbox_entries_result = add_bom_entries_to_project(
                        partsbox_result,
                        result.clean_bom,
                    )

                    unmatched_path = export_partsbox_unmatched_csv(
                        partsbox_entries_result.get("unmatched_rows", []),
                        project_name,
                        output_folder,
                    )
                    partsbox_import_path = export_partsbox_import_csv(
                        result.clean_bom,
                        project_name,
                        output_folder,
                    )

                    response["outputs"]["partsbox_import_csv"] = partsbox_import_path
                    if unmatched_path:
                        response["outputs"]["partsbox_unmatched_csv"] = unmatched_path

                    response["summary"]["partsbox_entries_added"] = int(
                        partsbox_entries_result.get("entries_added", 0)
                    )

                    response["partsbox"] = _build_partsbox_response(
                        partsbox_result, partsbox_entries_result
                    )

                    if partsbox_entries_result.get("skipped"):
                        response["messages"].append(
                            f"PartsBox entries skipped: {partsbox_entries_result.get('message')}"
                        )
                        if partsbox_entries_result.get("unrecognized_response"):
                            response["warnings"].append(
                                "PartsBox project entries were not added: the "
                                "project/get-entries response was not in a "
                                "recognized shape, so AutoBOM could not safely "
                                "confirm what already exists in the project."
                            )
                    else:
                        response["messages"].append(
                            "PartsBox entries added: "
                            f"{response['summary']['partsbox_entries_added']}"
                        )
                        skipped_existing = partsbox_entries_result.get(
                            "entries_skipped_existing", 0
                        )
                        if skipped_existing:
                            response["messages"].append(
                                "PartsBox entries already present, skipped: "
                                f"{skipped_existing}"
                            )

                        for mismatch in partsbox_entries_result.get(
                            "quantity_mismatches", []
                        ):
                            response["warnings"].append(
                                "PartsBox quantity mismatch for "
                                f"'{mismatch.get('entry_name')}': project has "
                                f"{mismatch.get('existing_quantity')}, BOM now "
                                f"requires {mismatch.get('intended_quantity')}. "
                                "Not updated automatically -- no verified "
                                "PartsBox update operation is implemented; "
                                "update the quantity manually in PartsBox."
                            )

                    if partsbox_result.get("storage_tag_missing"):
                        response["warnings"].append(
                            "PartsBox storage "
                            f"'{partsbox_result.get('storage_name')}' is missing the "
                            "'production' tag and no supported API call exists to add "
                            "it to an existing storage location. Add the tag manually "
                            "in PartsBox."
                        )

                    response["messages"].append(f"PartsBox import CSV exported to: {partsbox_import_path}")
                    if unmatched_path:
                        response["messages"].append(f"PartsBox unmatched CSV exported to: {unmatched_path}")
                except Exception as exc:
                    response["errors"].append(f"PartsBox step failed: {exc}")
        else:
            response["messages"].append("PartsBox flow skipped.")

        # ActiveBomState wraps result.clean_bom by reference (not a copy) --
        # it is the single canonical BOM state for this run. Review items,
        # the response's bom_rows/review_items, and the exported workbook's
        # Review_Items sheet are all derived from it below, rather than
        # each independently re-filtering/re-copying clean_bom.
        active_bom_state = ActiveBomState(result.clean_bom, run_id)
        review_items_df = active_bom_state.review_items_dataframe()
        result.review_items = review_items_df

        workbook_path, csv_path = build_output_paths(
            source_file_path,
            output_folder,
            workbook_suffix=OUTPUT_CLEAN_WORKBOOK_SUFFIX,
            csv_suffix=OUTPUT_CLEAN_BOM_SUFFIX,
        )
        export_clean_bom_workbook(result, workbook_path)
        export_clean_bom(active_bom_state.dataframe, csv_path)
        response["outputs"]["cleaned_workbook"] = workbook_path
        response["outputs"]["cleaned_csv"] = csv_path
        response["messages"].append(f"Cleaned workbook exported to: {workbook_path}")
        response["messages"].append(f"Cleaned CSV exported to: {csv_path}")

        mouser_sourced, digikey_sourced, manual_review = _count_sourcing(active_bom_state.dataframe)
        response["summary"]["mouser_sourced"] = mouser_sourced
        response["summary"]["digikey_sourced"] = digikey_sourced
        response["summary"]["manual_review"] = manual_review
        response["summary"]["review_items"] = int(len(review_items_df))
        response["summary"]["warnings"] = int(len(response["warnings"]))

        response["bom_rows"] = active_bom_state.rows()
        response["review_items"] = active_bom_state.to_records(review_items_df)
        response["purchasing"] = {
            "mouser": _build_mouser_purchasing(run_mouser_cart, mouser_cart_result),
            "digikey": _build_digikey_purchasing(run_digikey_mylist, digikey_mylist_result),
        }

        response["success"] = not response["errors"]
        _write_run_summary(response, source_file_path, output_folder)
    except Exception as exc:
        response["errors"].append(str(exc))
        response["success"] = False
        try:
            _write_run_summary(response, source_file_path, output_folder)
        except Exception:
            pass

    return response
