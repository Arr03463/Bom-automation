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
from digikey_mylists_client import build_digikey_mylists_parts, create_digikey_mylist_from_bom
from mouser_cart_client import build_mouser_cart_items, create_mouser_cart_from_bom
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


# Artifact freshness/state model (Phase 4 purchasing-correctness fix pass).
#
# Each artifact tracks its OWN state independently -- there is no longer a
# single global flag that blindly disables every download after one
# mutation or one regeneration failure. `stale_after_mutation` still exists
# as a derived convenience flag (see _recompute_global_stale_flag) for
# broad "something needs attention" messaging, but per-download/per-status
# decisions must read `artifact_status`, not that flag.
#
# Plain re-exportable file artifacts: regenerate_purchasing() always
# re-attempts these independently of each other and of the supplier
# artifacts.
FILE_ARTIFACT_KEYS = [
    "cleaned_csv",
    "sourcing_report",
    "digikey_list_csv",
    "partsbox_import_csv",
    "run_summary",
]

# These two need inputs regenerate_purchasing() does not have (the
# original run's column_mapping/warnings DataFrames for the workbook, or a
# fresh PartsBox project/get-entries call for the unmatched list). Rather
# than fabricate missing sheets or silently re-run a side-effecting
# PartsBox comparison, they are left permanently stale once a mutation
# marks them so -- never re-enabled by regenerate_purchasing().
PERMANENT_ARTIFACT_KEYS = [
    "cleaned_workbook",
    "partsbox_unmatched_csv",
]

# External, side-effecting artifacts (create a live Mouser cart / DigiKey
# MyList). regenerate_purchasing() skips re-invoking one of these entirely
# when it is already STATUS_CURRENT, so a retry needed only for the other
# supplier never creates a duplicate cart/list.
SUPPLIER_ARTIFACT_KEYS = [
    "mouser_cart",
    "digikey_mylist",
]

ARTIFACT_KEYS = FILE_ARTIFACT_KEYS + PERMANENT_ARTIFACT_KEYS + SUPPLIER_ARTIFACT_KEYS

STATUS_CURRENT = "current"
STATUS_STALE = "stale"
STATUS_NOT_GENERATED = "not_generated"
STATUS_FAILED = "failed"
STATUS_NOT_REQUIRED = "not_required"


def _initial_artifact_status():
    return {key: STATUS_NOT_GENERATED for key in ARTIFACT_KEYS}


def _supplier_requirement(dataframe):
    """
    A supplier artifact is only "required" when build_mouser_cart_items()/
    build_digikey_mylists_parts() -- the exact same selection logic used to
    actually build the cart/MyList -- finds at least one item for it. A
    supplier with zero required items needs no artifact and must never
    block "Ready for Handoff".
    """
    return {
        "mouser_cart": len(build_mouser_cart_items(dataframe)) > 0,
        "digikey_mylist": len(build_digikey_mylists_parts(dataframe)) > 0,
    }


def _mark_artifacts_stale_if_current(response):
    """
    Called after a Needs Review mutation (Retry Exact, replacement
    selection). Only artifacts that were STATUS_CURRENT move to
    STATUS_STALE -- an artifact that was already NOT_GENERATED/FAILED/
    NOT_REQUIRED stays exactly what it was, so one row's mutation can't
    manufacture a false "failed" or "required" state for an artifact that
    never applied.
    """
    artifact_status = response.setdefault("artifact_status", _initial_artifact_status())
    for key in ARTIFACT_KEYS:
        if artifact_status.get(key) == STATUS_CURRENT:
            artifact_status[key] = STATUS_STALE


def _recompute_global_stale_flag(response):
    """
    Derived convenience flag, not a source of truth: True when any
    re-exportable artifact (file or supplier) is stale relative to the
    current BOM state. Deliberately excludes PERMANENT_ARTIFACT_KEYS --
    those stay disabled forever after their first mutation by design, and
    must not keep the whole purchasing page reporting "Stale — BOM
    Changed" forever once everything else has been regenerated.
    """
    artifact_status = response.get("artifact_status") or {}
    regeneratable_keys = FILE_ARTIFACT_KEYS + SUPPLIER_ARTIFACT_KEYS
    stale = any(artifact_status.get(key) == STATUS_STALE for key in regeneratable_keys)
    response["stale_after_mutation"] = stale
    return stale


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
        "results_summary": {
            "total_parts": 0,
            "partsbox": 0,
            "mouser": 0,
            "digikey": 0,
            "needs_review": 0,
        },
        "partsbox": None,
        "purchasing": {
            "mouser": None,
            "digikey": None,
        },
        "_active_bom_state": None,
        "_purchasing_raw": {
            "mouser": None,
            "digikey": None,
        },
        "artifact_status": _initial_artifact_status(),
        "stale_after_mutation": False,
        "purchasing_regeneration_errors": [],
        "purchasing_regenerated_at_least_once": False,
    }


def refresh_response_snapshot(response):
    """
    bom_rows/review_items/results_summary are snapshots taken once at run
    completion. A Needs Review action (Retry Exact, replacement
    selection) mutates the live _active_bom_state directly and does not
    touch those snapshots -- call this one shared function afterward to
    recompute them, instead of hand-updating several dict keys inline in
    UI code.

    purchasing/outputs are deliberately left untouched: they describe the
    last generated cart/MyList/export artifacts, which remain exactly
    what they were, not what they'd be if regenerated now.
    _mark_artifacts_stale_if_current() marks each artifact that was
    STATUS_CURRENT as STATUS_STALE -- per-artifact, not a single blanket
    flag -- and _recompute_global_stale_flag() derives the convenience
    `stale_after_mutation` flag from that per-artifact state. Callers must
    treat any newly-stale artifact as pending regeneration, not silently
    current, once this has been called.
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return response

    response["bom_rows"] = active_bom_state.rows()
    response["review_items"] = active_bom_state.to_records(active_bom_state.review_items_dataframe())
    response["results_summary"] = active_bom_state.summary_counts()
    _mark_artifacts_stale_if_current(response)
    _recompute_global_stale_flag(response)
    return response


def derive_purchasing_status(response):
    """
    Describes the state of purchasing ARTIFACTS (cart/MyList/exports),
    not component sourcing status -- kept as a separate concept from a
    BOM row's result_status, per the same Source/Status separation the
    Results Workspace uses.

    Readiness is judged per REQUIRED supplier artifact (see
    _supplier_requirement): a supplier with zero required items is
    excluded entirely, never blocking "Ready for Handoff"; a required
    supplier that was attempted but not created (STATUS_FAILED) always
    blocks it, even if `purchasing["<supplier>"]["attempted"]` is True --
    attempted is not the same as ready.
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return "Not Available"

    artifact_status = response.get("artifact_status") or {}
    regeneratable_keys = FILE_ARTIFACT_KEYS + SUPPLIER_ARTIFACT_KEYS
    if any(artifact_status.get(key) == STATUS_STALE for key in regeneratable_keys):
        return "Stale — BOM Changed"

    if active_bom_state.summary_counts()["needs_review"] > 0:
        return "Needs Review"

    requirement = _supplier_requirement(active_bom_state.dataframe)
    required_keys = [key for key in SUPPLIER_ARTIFACT_KEYS if requirement.get(key)]

    if not required_keys:
        if not response.get("purchasing_regenerated_at_least_once"):
            return "Not Yet Generated"
        return "Ready for Handoff"

    required_statuses = [artifact_status.get(key) for key in required_keys]

    if all(status == STATUS_NOT_GENERATED for status in required_statuses):
        return "Not Yet Generated"

    if any(status == STATUS_FAILED for status in required_statuses):
        if all(status == STATUS_FAILED for status in required_statuses):
            return "Generation Failed"
        return "Partial — Generation Failed"

    if all(status == STATUS_CURRENT for status in required_statuses):
        return "Ready for Handoff"

    return "Not Yet Generated"


def build_purchasing_summary(response):
    """
    Purchasing summary for the Purchasing Handoff workspace. Item counts
    are read from the existing, unmodified build_mouser_cart_items()/
    build_digikey_mylists_parts() selection logic -- the same functions
    the actual cart/MyList creation calls use -- so this never recomputes
    a second sourcing/selection decision of its own.
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return None

    mouser_items = build_mouser_cart_items(active_bom_state.dataframe)
    digikey_items = build_digikey_mylists_parts(active_bom_state.dataframe)
    purchasing = response.get("purchasing") or {}
    mouser = purchasing.get("mouser") or {}
    digikey = purchasing.get("digikey") or {}
    artifact_status = response.get("artifact_status") or {}
    requirement = _supplier_requirement(active_bom_state.dataframe)

    return {
        "status": derive_purchasing_status(response),
        "mouser": {
            "item_count": len(mouser_items),
            "total_quantity": sum(int(item.get("Quantity", 0)) for item in mouser_items),
            "cart_created": bool(mouser.get("created")),
            "cart_key": mouser.get("cart_key"),
            "required": requirement.get("mouser_cart", False),
            "artifact_status": artifact_status.get("mouser_cart", STATUS_NOT_GENERATED),
        },
        "digikey": {
            "item_count": len(digikey_items),
            "total_quantity": sum(
                int(quantity.get("Quantity", 0))
                for part in digikey_items
                for quantity in part.get("Quantities", [])
            ),
            "list_created": bool(digikey.get("created")),
            "list_id": digikey.get("list_id"),
            "share_id": digikey.get("share_id"),
            "required": requirement.get("digikey_mylist", False),
            "artifact_status": artifact_status.get("digikey_mylist", STATUS_NOT_GENERATED),
        },
        "needs_review_count": active_bom_state.summary_counts()["needs_review"],
    }


def regenerate_purchasing(response, run_mouser_cart=True, run_digikey_mylist=True):
    """
    Explicit, operator-triggered regeneration of purchasing artifacts
    from the CURRENT canonical BOM state. Reuses create_mouser_cart_from_bom()/
    create_digikey_mylist_from_bom() -- the exact calls run_bom_workflow()
    makes during a normal run -- and _build_mouser_purchasing()/
    _build_digikey_purchasing() to build the same structured shape. Not a
    second purchasing implementation.

    Also re-exports the plain CSV artifacts (cleaned BOM, sourcing
    report, DigiKey list, PartsBox import CSV) from the current state
    using the existing exporters, and rewrites run_summary.json, so
    downloads stop reflecting the pre-mutation BOM. The multi-sheet
    cleaned workbook and the PartsBox unmatched CSV are NOT regenerated
    here -- see PERMANENT_ARTIFACT_KEYS -- and are left exactly as their
    current artifact_status says.

    Every stage below is wrapped in its own try/except and records its
    OWN artifact_status entry: one export failing must never crash this
    function, never mark an unrelated artifact current, and never touch
    canonical BOM state. An already-STATUS_CURRENT supplier artifact is
    skipped entirely (not re-invoked) so a retry needed only for one
    supplier can never create a duplicate cart/list for the other, and a
    plain rerun that doesn't call this function creates nothing at all.

    Must only be called in response to an explicit operator action (a
    "Regenerate Purchasing" button), never automatically on a Streamlit
    rerun -- both cart/MyList calls can hit live vendor APIs and create a
    new cart/list every time they run.
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return response

    artifact_status = response.setdefault("artifact_status", _initial_artifact_status())
    purchasing_raw = response.setdefault("_purchasing_raw", {"mouser": None, "digikey": None})
    purchasing = response.setdefault("purchasing", {"mouser": None, "digikey": None})

    run_info = response.get("run", {})
    project_name = str(run_info.get("project_name") or "").strip()
    source_file_name = run_info.get("source_file_name") or "bom"
    source_stem = Path(source_file_name).stem
    list_name_base = project_name or source_stem

    output_folder = os.path.dirname(response["outputs"].get("cleaned_csv") or "") or OUTPUT_FOLDER
    os.makedirs(output_folder, exist_ok=True)
    dataframe = active_bom_state.dataframe

    # Superseded by this attempt's outcome, not accumulated forever --
    # each stage below re-records its own current failure (if any).
    errors = []
    messages = []

    try:
        csv_path = response["outputs"].get("cleaned_csv") or build_output_paths(
            source_file_name, output_folder, csv_suffix=OUTPUT_CLEAN_BOM_SUFFIX
        )[1]
        export_clean_bom(dataframe, csv_path)
        response["outputs"]["cleaned_csv"] = csv_path
        artifact_status["cleaned_csv"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["cleaned_csv"] = STATUS_FAILED
        errors.append(f"Cleaned CSV regeneration failed: {exc}")

    try:
        sourcing_report_path = export_sourcing_report(
            dataframe, output_folder, file_stem=f"{source_stem}_sourcing_report"
        )
        response["outputs"]["sourcing_report"] = sourcing_report_path
        artifact_status["sourcing_report"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["sourcing_report"] = STATUS_FAILED
        errors.append(f"Sourcing report regeneration failed: {exc}")

    try:
        digikey_list_path, _ = export_digikey_list(
            dataframe, output_folder, file_stem=f"{source_stem}_digikey_list"
        )
        response["outputs"]["digikey_list_csv"] = digikey_list_path
        artifact_status["digikey_list_csv"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["digikey_list_csv"] = STATUS_FAILED
        errors.append(f"DigiKey list regeneration failed: {exc}")

    if project_name:
        try:
            response["outputs"]["partsbox_import_csv"] = export_partsbox_import_csv(
                dataframe, project_name, output_folder
            )
            artifact_status["partsbox_import_csv"] = STATUS_CURRENT
        except Exception as exc:
            artifact_status["partsbox_import_csv"] = STATUS_FAILED
            errors.append(f"PartsBox import CSV regeneration failed: {exc}")
    else:
        artifact_status["partsbox_import_csv"] = STATUS_NOT_REQUIRED

    requirement = _supplier_requirement(dataframe)

    if not requirement["mouser_cart"]:
        artifact_status["mouser_cart"] = STATUS_NOT_REQUIRED
    elif artifact_status.get("mouser_cart") == STATUS_CURRENT:
        messages.append("Mouser cart already current for this BOM state; not recreated.")
    elif not run_mouser_cart:
        pass
    elif os.getenv("MOUSER_CART_ENABLED", "false").lower() != "true":
        messages.append("Mouser cart regeneration skipped: MOUSER_CART_ENABLED is not true.")
    else:
        try:
            mouser_cart_result = create_mouser_cart_from_bom(dataframe)
            built = _build_mouser_purchasing(True, mouser_cart_result)
            purchasing_raw["mouser"] = mouser_cart_result.get("result") if mouser_cart_result else None
            purchasing["mouser"] = built
            if built["created"]:
                artifact_status["mouser_cart"] = STATUS_CURRENT
                messages.append("Mouser cart regenerated from the current BOM state.")
            else:
                artifact_status["mouser_cart"] = STATUS_FAILED
                errors.append(f"Mouser cart regeneration did not create a cart: {built.get('message')}")
        except Exception as exc:
            artifact_status["mouser_cart"] = STATUS_FAILED
            errors.append(f"Mouser cart regeneration failed: {exc}")

    if not requirement["digikey_mylist"]:
        artifact_status["digikey_mylist"] = STATUS_NOT_REQUIRED
    elif artifact_status.get("digikey_mylist") == STATUS_CURRENT:
        messages.append("DigiKey MyList already current for this BOM state; not recreated.")
    elif not run_digikey_mylist:
        pass
    elif os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() != "true":
        messages.append("DigiKey MyList regeneration skipped: DIGIKEY_MYLISTS_ENABLED is not true.")
    else:
        try:
            digikey_mylist_result = create_digikey_mylist_from_bom(
                dataframe, list_name=f"{list_name_base} DigiKey List"
            )
            built = _build_digikey_purchasing(True, digikey_mylist_result)
            purchasing_raw["digikey"] = {
                "create_result": digikey_mylist_result.get("create_result") if digikey_mylist_result else None,
                "add_result": digikey_mylist_result.get("add_result") if digikey_mylist_result else None,
            }
            purchasing["digikey"] = built
            if built["created"] and not built["token_persistence_degraded"]:
                artifact_status["digikey_mylist"] = STATUS_CURRENT
                messages.append("DigiKey MyList regenerated from the current BOM state.")
            elif built["created"] and built["token_persistence_degraded"]:
                # The list itself was created (its data is preserved
                # above), but the rotated refresh token this call
                # produced could not be durably persisted -- the next
                # refresh attempt will likely fail until that's fixed.
                # Reported as failed, not current, so purchasing doesn't
                # claim DigiKey is fully healthy (Codex F2).
                artifact_status["digikey_mylist"] = STATUS_FAILED
                errors.append(
                    "DigiKey MyList was created, but its rotated refresh token could "
                    "not be durably persisted -- DigiKey MyLists automation will "
                    "likely fail on the next attempt or after a restart until this "
                    "is corrected. See "
                    "Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md."
                )
            else:
                artifact_status["digikey_mylist"] = STATUS_FAILED
                errors.append(f"DigiKey MyList regeneration did not create a list: {built.get('message')}")
        except Exception as exc:
            artifact_status["digikey_mylist"] = STATUS_FAILED
            errors.append(f"DigiKey MyList regeneration failed: {exc}")

    response["purchasing_regeneration_errors"] = errors
    response["messages"] = response.get("messages", []) + messages

    response["bom_rows"] = active_bom_state.rows()
    response["review_items"] = active_bom_state.to_records(active_bom_state.review_items_dataframe())
    response["results_summary"] = active_bom_state.summary_counts()

    try:
        _write_run_summary(response, source_file_name, output_folder)
        artifact_status["run_summary"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["run_summary"] = STATUS_FAILED
        errors.append(f"Run summary regeneration failed: {exc}")
        response["purchasing_regeneration_errors"] = errors

    response["purchasing_regenerated_at_least_once"] = True
    _recompute_global_stale_flag(response)

    return response


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
    Confirmed live (2026-09-24, one real disposable test cart via
    MouserCartClient.add_items_to_cart()): CartKey is returned at the TOP
    LEVEL of the response (alongside CartItems/CurrencyCode/Errors/
    MerchandiseTotal/TotalItemCount), with no "Cart" sub-object present in
    that response at all. The Cart.CartKey branch below is kept as a
    defensive fallback for a response shape variant referenced in
    Mouser's published docs but never observed against this account --
    not removed, since it costs nothing to keep and protects against a
    shape change.
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
    """
    Retains only the structured fields the app actually needs. The full
    vendor response (which may carry more than AutoBOM needs to persist)
    is kept separately in-memory, in response["_purchasing_raw"] -- a key
    starting with "_", so _write_run_summary() already excludes it from
    the JSON written to disk -- rather than embedded here.
    """
    if not attempted or mouser_cart_result is None:
        return {
            "attempted": bool(attempted),
            "created": False,
            "items_count": 0,
            "cart_key": None,
            "message": None,
        }

    raw_result = mouser_cart_result.get("result")

    return {
        "attempted": True,
        "created": bool(mouser_cart_result.get("created")),
        "items_count": int(mouser_cart_result.get("items_count", 0)),
        "cart_key": _extract_mouser_cart_key(raw_result),
        "message": mouser_cart_result.get("message"),
    }


def _build_digikey_purchasing(attempted, digikey_mylist_result):
    """
    Same structured-fields-only retention as _build_mouser_purchasing();
    raw create/add responses belong in response["_purchasing_raw"], not
    here.
    """
    if not attempted or digikey_mylist_result is None:
        return {
            "attempted": bool(attempted),
            "created": False,
            "list_id": None,
            "list_name": None,
            "share_id": None,
            "parts_count": 0,
            "message": None,
            "token_persistence_degraded": False,
        }

    # Codex F2: a MyList can be genuinely created while the DigiKey
    # refresh token rotated during that call failed to persist durably.
    # That is not a healthy outcome -- the store still holds a token
    # DigiKey has already invalidated -- so callers (regenerate_purchasing,
    # run_bom_workflow) must not treat "created: True" alone as
    # sufficient to mark this artifact current. See
    # create_digikey_mylist_from_bom()'s "token_store_error" field.
    token_store_error = digikey_mylist_result.get("token_store_error")

    return {
        "attempted": True,
        "created": bool(digikey_mylist_result.get("created")),
        "list_id": digikey_mylist_result.get("list_id"),
        "list_name": digikey_mylist_result.get("list_name"),
        # Confirmed live (2026-09-25, three real disposable test
        # MyLists): create_list() returns a bare string list ID and
        # add_parts_to_list() returns a plain list of string item IDs --
        # no share identifier/link field exists anywhere in either
        # response. This is a confirmed absence, not an open question;
        # do not fabricate a value here.
        "share_id": None,
        "parts_count": digikey_mylist_result.get("parts_count", 0),
        "message": digikey_mylist_result.get("message"),
        "token_persistence_degraded": bool(token_store_error),
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

    # Keys starting with "_" carry live Python objects for in-process
    # session-state use (e.g. "_active_bom_state") -- never JSON-safe, and
    # never written to disk.
    json_safe_response = {
        key: value for key, value in response.items() if not key.startswith("_")
    }

    with open(output_path, "w", encoding="utf-8") as summary_file:
        json.dump(json_safe_response, summary_file, indent=2)

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
                            if digikey_mylist_result.get("token_store_error"):
                                response["warnings"].append(
                                    "DigiKey MyList was created, but its rotated refresh "
                                    "token could not be durably persisted -- DigiKey "
                                    "MyLists automation will likely fail on the next "
                                    "attempt or after a restart until this is corrected. "
                                    "See Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md."
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
        # Canonical Customer Reference field (see customer_reference.py):
        # initialized here so it exists as a real column from run start --
        # present in rows()/exports immediately, not only once an operator
        # first assigns a value via update_row().
        if "customer_reference" not in active_bom_state.dataframe.columns:
            active_bom_state.dataframe["customer_reference"] = ""
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

        # Live object, kept out of the JSON-serialized response (see
        # _write_run_summary) -- app.py stores this directly in
        # st.session_state so the Results Workspace/Needs Review always
        # read and mutate the one canonical BOM state, not a copy re-built
        # from the serialized bom_rows/review_items below.
        response["_active_bom_state"] = active_bom_state
        response["results_summary"] = active_bom_state.summary_counts()

        response["bom_rows"] = active_bom_state.rows()
        response["review_items"] = active_bom_state.to_records(review_items_df)
        response["purchasing"] = {
            "mouser": _build_mouser_purchasing(run_mouser_cart, mouser_cart_result),
            "digikey": _build_digikey_purchasing(run_digikey_mylist, digikey_mylist_result),
        }
        response["_purchasing_raw"] = {
            "mouser": mouser_cart_result.get("result") if mouser_cart_result else None,
            "digikey": {
                "create_result": digikey_mylist_result.get("create_result") if digikey_mylist_result else None,
                "add_result": digikey_mylist_result.get("add_result") if digikey_mylist_result else None,
            }
            if digikey_mylist_result
            else None,
        }

        # Initial artifact_status for this fresh run. Everything reached
        # this point without raising, so each artifact is either CURRENT
        # (it was just exported/attempted successfully), NOT_REQUIRED (its
        # step never ran / had nothing to do), or FAILED (its step ran and
        # its own try/except above recorded an error without this
        # attribute otherwise reflecting success).
        artifact_status = response["artifact_status"]
        artifact_status["cleaned_csv"] = STATUS_CURRENT
        artifact_status["cleaned_workbook"] = STATUS_CURRENT

        sourcing_ran = bool(run_sourcing and (use_mouser_sourcing or use_digikey_sourcing))
        artifact_status["sourcing_report"] = STATUS_CURRENT if sourcing_ran else STATUS_NOT_REQUIRED
        artifact_status["digikey_list_csv"] = STATUS_CURRENT if sourcing_ran else STATUS_NOT_REQUIRED

        requirement = _supplier_requirement(active_bom_state.dataframe)
        if not requirement["mouser_cart"]:
            artifact_status["mouser_cart"] = STATUS_NOT_REQUIRED
        elif run_mouser_cart and os.getenv("MOUSER_CART_ENABLED", "false").lower() == "true":
            artifact_status["mouser_cart"] = (
                STATUS_CURRENT if mouser_cart_result and mouser_cart_result.get("created") else STATUS_FAILED
            )
        else:
            artifact_status["mouser_cart"] = STATUS_NOT_GENERATED

        if not requirement["digikey_mylist"]:
            artifact_status["digikey_mylist"] = STATUS_NOT_REQUIRED
        elif run_digikey_mylist and os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true":
            # Created but with a token-persistence failure (Codex F2) is
            # reported as failed, not current -- see _build_digikey_purchasing().
            artifact_status["digikey_mylist"] = (
                STATUS_CURRENT
                if digikey_mylist_result
                and digikey_mylist_result.get("created")
                and not digikey_mylist_result.get("token_store_error")
                else STATUS_FAILED
            )
        else:
            artifact_status["digikey_mylist"] = STATUS_NOT_GENERATED

        partsbox_attempted = bool(run_partsbox and project_name)
        partsbox_import_ok = bool(response["outputs"].get("partsbox_import_csv"))
        partsbox_unmatched_present = bool(response["outputs"].get("partsbox_unmatched_csv"))
        if not partsbox_attempted:
            artifact_status["partsbox_import_csv"] = STATUS_NOT_REQUIRED
            artifact_status["partsbox_unmatched_csv"] = STATUS_NOT_REQUIRED
        elif partsbox_import_ok:
            artifact_status["partsbox_import_csv"] = STATUS_CURRENT
            artifact_status["partsbox_unmatched_csv"] = (
                STATUS_CURRENT if partsbox_unmatched_present else STATUS_NOT_REQUIRED
            )
        else:
            artifact_status["partsbox_import_csv"] = STATUS_FAILED
            artifact_status["partsbox_unmatched_csv"] = STATUS_FAILED

        response["success"] = not response["errors"]
        _write_run_summary(response, source_file_path, output_folder)
        artifact_status["run_summary"] = STATUS_CURRENT
    except Exception as exc:
        response["errors"].append(str(exc))
        response["success"] = False
        try:
            _write_run_summary(response, source_file_path, output_folder)
            response["artifact_status"]["run_summary"] = STATUS_CURRENT
        except Exception:
            response["artifact_status"]["run_summary"] = STATUS_FAILED

    return response
