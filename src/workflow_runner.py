import json
import os
from pathlib import Path

from dotenv import load_dotenv

import pandas as pd

from active_bom_state import ActiveBomState
from bom_cleaner import (
    STANDARD_COLUMNS,
    BomCleanResult,
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
from digikey_fastadd import build_digikey_fastadd_url
from digikey_list_export import export_digikey_list
from mouser_client import MouserClient
from mouser_export import export_mouser_list
from partsbox_project_builder import (
    add_bom_entries_to_project,
    create_partsbox_project_and_storage,
    export_partsbox_import_csv,
    export_partsbox_unmatched_csv,
)
from purchasing_lines import build_purchasing_lines
from run_workspace import new_run_id
from sourcing_engine import apply_sourcing_decisions
from sourcing_report import export_sourcing_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)


# Artifact freshness/state model (Phase 4 purchasing-correctness fix pass;
# revised for the direct DigiKey/Mouser handoff -- see
# Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md).
#
# Each artifact tracks its OWN state independently -- there is no longer a
# single global flag that blindly disables every download after one
# mutation or one regeneration failure. `stale_after_mutation` still exists
# as a derived convenience flag (see _recompute_global_stale_flag) for
# broad "something needs attention" messaging, but per-download/per-status
# decisions must read `artifact_status`, not that flag.
#
# Every purchasing artifact here is a plain local file write or a pure
# deterministic URL derivation -- NONE of them is a live vendor API call
# during normal application use. DigiKey MyList creation
# (src/digikey_mylists_client.py) is retained only as a separate,
# explicitly-gated legacy path (src/main.py's CLI, behind an operator
# "y" prompt and DIGIKEY_MYLISTS_ENABLED) -- never invoked from here.
#
# cleaned_workbook regenerates too (QA/QC deep-dive report, Q9): its
# Clean_BOM/Review_Items sheets are freshly derived from the current
# canonical state, same as cleaned_csv, but its Column_Mapping/Warnings
# sheets come back EMPTY on a regenerated workbook -- those describe the
# ORIGINAL upload's raw-header-to-clean-column mapping and per-row
# cleaning warnings, which regenerate_purchasing() has no way to
# recompute after canonical-BOM edits (it isn't reprocessing a raw
# upload file). Preferred over leaving the workbook permanently stale
# forever after the first edit; see _regenerate_cleaned_workbook().
#
# digikey_cart_link is the pure, deterministic DigiKey FastAdd cart URL
# (src/digikey_fastadd.py) -- no MyLists OAuth, no vendor call. It sits
# alongside digikey_list_csv/mouser_export_csv as a REQUIRED-when-that-
# supplier-has-lines artifact (see REQUIRED_ARTIFACT_KEYS below), not a
# side-effecting one, since generating it has no external consequence.
FILE_ARTIFACT_KEYS = [
    "cleaned_csv",
    "cleaned_workbook",
    "sourcing_report",
    "digikey_list_csv",
    "digikey_cart_link",
    "mouser_export_csv",
    "partsbox_import_csv",
    "run_summary",
]

# partsbox_unmatched_csv needs a fresh PartsBox project/get-entries call
# regenerate_purchasing() has no reason to perform on a plain
# regeneration (it's a read against live PartsBox state, not derivable
# from the canonical BOM alone) -- left permanently stale once a
# mutation marks it so, never re-enabled by regenerate_purchasing().
PERMANENT_ARTIFACT_KEYS = [
    "partsbox_unmatched_csv",
]

ARTIFACT_KEYS = FILE_ARTIFACT_KEYS + PERMANENT_ARTIFACT_KEYS

STATUS_CURRENT = "current"
STATUS_STALE = "stale"
STATUS_NOT_GENERATED = "not_generated"
STATUS_FAILED = "failed"
STATUS_NOT_REQUIRED = "not_required"
# digikey_cart_link-only status: the current BOM's DigiKey purchasing
# data is valid, but the encoded FastAdd URL exceeded the safe length --
# the DigiKey CSV is the supported fallback in this state (see
# digikey_fastadd.py). Counts as "current and valid" for readiness,
# exactly like STATUS_CURRENT (H1's required handoff-artifact policy).
STATUS_CSV_FALLBACK = "csv_fallback"

# Artifacts whose requirement depends on whether that supplier actually
# has any validated purchasing lines in the CURRENT canonical BOM -- see
# _purchasing_requirement(). A supplier with zero lines needs none of
# its artifacts and must never block "Ready for Handoff" (replaces the
# old MyList-centered SUPPLIER_ARTIFACT_KEYS/_supplier_requirement()
# model; see the change-risk audit's H1).
REQUIRED_ARTIFACT_KEYS = ["digikey_list_csv", "digikey_cart_link", "mouser_export_csv"]


def _initial_artifact_status():
    return {key: STATUS_NOT_GENERATED for key in ARTIFACT_KEYS}


def _purchasing_requirement(dataframe, run_id=""):
    """
    Whether each REQUIRED_ARTIFACT_KEYS entry is required at all, judged
    against the SAME canonical purchasing-line selection
    (purchasing_lines.build_purchasing_lines()) every other purchasing
    artifact uses. A supplier counts as "required" when it has either
    valid lines OR validation errors -- a row that IS sourced from a
    supplier but has an unusable part number/quantity must not be
    invisible to this check (bool(result.lines) alone would be False for
    it, same as a supplier with zero rows at all), or its CSV/link
    FAILED status would never be in REQUIRED_ARTIFACT_KEYS's
    `required_keys` and could never block Ready for Handoff -- exactly
    the "must not silently omit an invalid row and report the package
    Ready" failure mode H2 in the change-risk audit describes.
    """
    digikey_result = build_purchasing_lines(dataframe, "digikey", run_id=run_id)
    mouser_result = build_purchasing_lines(dataframe, "mouser", run_id=run_id)
    digikey_required = bool(digikey_result.lines) or bool(digikey_result.errors)
    mouser_required = bool(mouser_result.lines) or bool(mouser_result.errors)
    return {
        "digikey_list_csv": digikey_required,
        "digikey_cart_link": digikey_required,
        "mouser_export_csv": mouser_required,
    }


def _is_required_artifact_valid(key, status):
    """"Current and valid" per key -- digikey_cart_link additionally
    accepts STATUS_CSV_FALLBACK (a deliberate, documented terminal state,
    not a degraded one; see H1/H6)."""
    if key == "digikey_cart_link":
        return status in (STATUS_CURRENT, STATUS_CSV_FALLBACK)
    return status == STATUS_CURRENT


def _mark_artifacts_stale_if_current(response):
    """
    Called after a Needs Review mutation (Retry Exact, replacement
    selection) or any other purchasing-affecting change. An artifact
    that was "valid" (STATUS_CURRENT, or STATUS_CSV_FALLBACK for
    digikey_cart_link) moves to STATUS_STALE -- an artifact that was
    already NOT_GENERATED/FAILED/NOT_REQUIRED stays exactly what it was,
    so one row's mutation can't manufacture a false "failed" or
    "required" state for an artifact that never applied.
    """
    artifact_status = response.setdefault("artifact_status", _initial_artifact_status())
    for key in ARTIFACT_KEYS:
        status = artifact_status.get(key)
        was_valid = status == STATUS_CURRENT or (key == "digikey_cart_link" and status == STATUS_CSV_FALLBACK)
        if was_valid:
            artifact_status[key] = STATUS_STALE


def _reconcile_purchasing_requirement_status(response, dataframe, run_id=""):
    """
    A REQUIRED_ARTIFACT_KEYS entry's status can go wrong in a way
    _mark_artifacts_stale_if_current() alone never catches: a Needs
    Review mutation can change whether that supplier has any purchasing
    lines AT ALL (e.g. zero DigiKey-sourced rows becoming one or more),
    not just whether an already-required artifact is current. Without
    this, a prior STATUS_NOT_REQUIRED can survive after DigiKey becomes
    required, letting Purchasing Handoff display "Not Required" while a
    nonzero DigiKey item count is shown right next to it (see the QA/QC
    deep-dive report's Q8, generalized here to all three
    REQUIRED_ARTIFACT_KEYS instead of just digikey_mylist).
    """
    artifact_status = response.setdefault("artifact_status", _initial_artifact_status())
    requirement = _purchasing_requirement(dataframe, run_id=run_id)
    for key in REQUIRED_ARTIFACT_KEYS:
        required_now = requirement.get(key, False)
        current_status = artifact_status.get(key)
        if required_now and current_status == STATUS_NOT_REQUIRED:
            artifact_status[key] = STATUS_NOT_GENERATED
        elif not required_now and current_status != STATUS_NOT_REQUIRED:
            artifact_status[key] = STATUS_NOT_REQUIRED


def _recompute_global_stale_flag(response):
    """
    Derived convenience flag, not a source of truth: True when any
    re-exportable artifact is stale relative to the current BOM state.
    Deliberately excludes PERMANENT_ARTIFACT_KEYS -- those stay disabled
    forever after their first mutation by design, and must not keep the
    whole purchasing page reporting "Stale — BOM Changed" forever once
    everything else has been regenerated.
    """
    artifact_status = response.get("artifact_status") or {}
    stale = any(artifact_status.get(key) == STATUS_STALE for key in FILE_ARTIFACT_KEYS)
    response["stale_after_mutation"] = stale
    return stale


def _empty_digikey_cart_link():
    return {
        "status": STATUS_NOT_GENERATED,
        "url": "",
        "encoded_length": 0,
        "item_count": 0,
        "fallback_reason": "",
    }


def _empty_result():
    return {
        "success": False,
        "errors": [],
        "warnings": [],
        "summary": {
            "mouser_sourced": 0,
            "digikey_sourced": 0,
            "manual_review": 0,
            "mouser_export_items": 0,
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
            "mouser_export_csv": "",
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
        # Pure, deterministic DigiKey FastAdd cart-link state (see
        # digikey_fastadd.py) -- no vendor API call. Replaces the old
        # `purchasing`/`_purchasing_raw` DigiKey-MyList/Mouser-cart
        # side-effect tracking, which no longer exists in normal flow
        # (see digikey_mylists_client.py/mouser_cart_client.py, retained
        # only for src/main.py's separate, explicitly-gated legacy CLI
        # path). A response dict from before this change may still carry
        # the old `purchasing`/`artifact_status["digikey_mylist"]` keys
        # in a live Streamlit session that survived a hot reload -- every
        # reader in this module ignores those legacy keys entirely
        # rather than reinterpreting them (see H9).
        "digikey_cart_link": _empty_digikey_cart_link(),
        "_active_bom_state": None,
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

    outputs/digikey_cart_link are deliberately left untouched: they
    describe the last generated exports/link, which remain exactly what
    they were, not what they'd be if regenerated now.
    _mark_artifacts_stale_if_current() marks each artifact that was
    valid as STATUS_STALE -- per-artifact, not a single blanket flag --
    and _recompute_global_stale_flag() derives the convenience
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
    _reconcile_purchasing_requirement_status(
        response, active_bom_state.dataframe, run_id=response.get("run", {}).get("run_id", "")
    )
    _recompute_global_stale_flag(response)
    return response


def derive_purchasing_status(response):
    """
    Describes the state of purchasing ARTIFACTS (supplier CSVs, DigiKey
    cart link), not component sourcing status -- kept as a separate
    concept from a BOM row's result_status, per the same Source/Status
    separation the Results Workspace uses.

    Readiness is judged per REQUIRED_ARTIFACT_KEYS entry (see
    _purchasing_requirement): a supplier with zero purchasing lines is
    excluded entirely, never blocking "Ready for Handoff"; a required
    artifact that was attempted but failed (invalid purchasing data or an
    export error) always blocks it (H1).
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return "Not Available"

    artifact_status = response.get("artifact_status") or {}
    if any(artifact_status.get(key) == STATUS_STALE for key in FILE_ARTIFACT_KEYS):
        return "Stale — BOM Changed"

    if active_bom_state.summary_counts()["needs_review"] > 0:
        return "Needs Review"

    run_id = response.get("run", {}).get("run_id", "")
    requirement = _purchasing_requirement(active_bom_state.dataframe, run_id=run_id)
    required_keys = [key for key in REQUIRED_ARTIFACT_KEYS if requirement.get(key)]

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

    if all(_is_required_artifact_valid(key, artifact_status.get(key)) for key in required_keys):
        return "Ready for Handoff"

    return "Not Yet Generated"


def build_purchasing_summary(response):
    """
    Purchasing summary for the Purchasing Handoff workspace. Item/
    quantity counts are read from the SAME canonical purchasing lines
    (purchasing_lines.build_purchasing_lines()) that generate the
    supplier CSVs and the DigiKey FastAdd link -- one validated
    selection, not a second recomputation (H2/H4).
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return None

    run_id = response.get("run", {}).get("run_id", "")
    dataframe = active_bom_state.dataframe
    mouser_result = build_purchasing_lines(dataframe, "mouser", run_id=run_id)
    digikey_result = build_purchasing_lines(dataframe, "digikey", run_id=run_id)
    artifact_status = response.get("artifact_status") or {}
    requirement = _purchasing_requirement(dataframe, run_id=run_id)
    cart_link = response.get("digikey_cart_link") or _empty_digikey_cart_link()

    return {
        "status": derive_purchasing_status(response),
        "mouser": {
            "item_count": mouser_result.item_count,
            "total_quantity": mouser_result.total_quantity,
            "required": requirement.get("mouser_export_csv", False),
            "artifact_status": artifact_status.get("mouser_export_csv", STATUS_NOT_GENERATED),
            "errors": [error.reason for error in mouser_result.errors],
        },
        "digikey": {
            "item_count": digikey_result.item_count,
            "total_quantity": digikey_result.total_quantity,
            "required": requirement.get("digikey_list_csv", False),
            "csv_artifact_status": artifact_status.get("digikey_list_csv", STATUS_NOT_GENERATED),
            "cart_link_status": artifact_status.get("digikey_cart_link", STATUS_NOT_GENERATED),
            "cart_link_url": cart_link.get("url", ""),
            "cart_link_encoded_length": cart_link.get("encoded_length", 0),
            "cart_link_fallback_reason": cart_link.get("fallback_reason", ""),
            "errors": [error.reason for error in digikey_result.errors],
        },
        "needs_review_count": active_bom_state.summary_counts()["needs_review"],
    }


def _regenerate_cleaned_workbook(active_bom_state, output_path):
    """
    Regenerates the multi-sheet cleaned workbook from the CURRENT
    canonical state (QA/QC deep-dive report, Q9) instead of leaving it
    permanently stale after the first post-upload edit. Clean_BOM and
    Review_Items are freshly derived, exactly like every other artifact
    regenerate_purchasing() re-exports. Column_Mapping/Warnings come back
    empty: they describe the ORIGINAL upload's raw-header-to-clean-column
    mapping and per-row cleaning warnings, which only exist as a
    byproduct of process_bom_file() reprocessing a raw upload file --
    there is no raw file to re-derive them from here, and fabricating
    values would misrepresent what actually happened during cleaning.
    """
    empty_mapping = pd.DataFrame(columns=["original_header", "mapped_field"])
    empty_warnings = pd.DataFrame(columns=["source_row", "field", "message"])
    result = BomCleanResult(
        clean_bom=active_bom_state.dataframe,
        review_items=active_bom_state.review_items_dataframe(),
        column_mapping=empty_mapping,
        warnings=empty_warnings,
        mapped_columns={},
    )
    export_clean_bom_workbook(result, output_path)


def _generate_supplier_csv(export_fn, dataframe, run_id, output_folder, file_stem, artifact_status, key, outputs, errors, supplier_label):
    """
    Shared by run_bom_workflow()/regenerate_purchasing() for both
    digikey_list_csv and mouser_export_csv: exports the supplier CSV
    from canonical purchasing lines (export_fn is
    digikey_list_export.export_digikey_list or
    mouser_export.export_mouser_list, both of which return
    (output_path, PurchasingLineResult)) and records this artifact's
    status. A nonempty PurchasingLineResult.errors means at least one
    row that IS sourced from this supplier and not DNP has unusable
    purchasing data -- FAILED, never silently dropped (H2). Returns the
    PurchasingLineResult so the caller can reuse it (e.g. for the DigiKey
    FastAdd link) without re-deriving the lines a second time.
    """
    try:
        path, result = export_fn(dataframe, output_folder, file_stem=file_stem, run_id=run_id)
        outputs[key] = path
        if result.errors:
            artifact_status[key] = STATUS_FAILED
            for line_error in result.errors:
                errors.append(
                    f"{supplier_label} purchasing data invalid (row {line_error.row_id}, "
                    f"{line_error.field}): {line_error.reason}"
                )
        elif result.lines:
            artifact_status[key] = STATUS_CURRENT
        else:
            artifact_status[key] = STATUS_NOT_REQUIRED
        return result
    except Exception as exc:
        artifact_status[key] = STATUS_FAILED
        errors.append(f"{supplier_label} CSV export failed: {exc}")
        return None


def _generate_digikey_cart_link(digikey_result, artifact_status, errors):
    """
    Builds the DigiKey FastAdd cart link from the SAME PurchasingLineResult
    _generate_supplier_csv() already computed for "digikey" -- never a
    second, independent selection (H4). No vendor API call.
    """
    if digikey_result is None or digikey_result.errors:
        artifact_status["digikey_cart_link"] = STATUS_FAILED
        return {
            "status": STATUS_FAILED,
            "url": "",
            "encoded_length": 0,
            "item_count": 0,
            "fallback_reason": "Invalid DigiKey purchasing data; see errors above.",
        }

    if not digikey_result.lines:
        artifact_status["digikey_cart_link"] = STATUS_NOT_REQUIRED
        return _empty_digikey_cart_link()

    try:
        link_result = build_digikey_fastadd_url(digikey_result.lines)
    except Exception as exc:
        artifact_status["digikey_cart_link"] = STATUS_FAILED
        errors.append(f"DigiKey cart link generation failed: {exc}")
        return {
            "status": STATUS_FAILED,
            "url": "",
            "encoded_length": 0,
            "item_count": 0,
            "fallback_reason": str(exc),
        }

    artifact_status["digikey_cart_link"] = link_result.status
    return {
        "status": link_result.status,
        "url": link_result.url,
        "encoded_length": link_result.encoded_length,
        "item_count": link_result.item_count,
        "fallback_reason": link_result.fallback_reason,
    }


def _regenerate_purchasing_artifacts(dataframe, run_id, output_folder, source_stem, artifact_status, outputs, errors):
    """
    Single shared implementation for building every purchasing-handoff
    artifact (DigiKey supplier CSV, DigiKey FastAdd cart link, Mouser
    supplier CSV) from the CURRENT canonical BOM state -- used by both a
    fresh run_bom_workflow() run and an explicit regenerate_purchasing()
    click, so the two paths can never diverge (H4/H6). No DigiKey
    MyLists API call anywhere in this function.

    Returns the digikey_cart_link dict for response["digikey_cart_link"].
    """
    digikey_result = _generate_supplier_csv(
        export_digikey_list,
        dataframe,
        run_id,
        output_folder,
        f"{source_stem}_digikey_list",
        artifact_status,
        "digikey_list_csv",
        outputs,
        errors,
        "DigiKey",
    )
    _generate_supplier_csv(
        export_mouser_list,
        dataframe,
        run_id,
        output_folder,
        f"{source_stem}_mouser_export",
        artifact_status,
        "mouser_export_csv",
        outputs,
        errors,
        "Mouser",
    )
    return _generate_digikey_cart_link(digikey_result, artifact_status, errors)


def regenerate_purchasing(response):
    """
    Explicit, operator-triggered regeneration of purchasing artifacts
    from the CURRENT canonical BOM state, via _regenerate_purchasing_artifacts()
    -- the exact same implementation run_bom_workflow() uses. Also
    re-exports the plain CSV artifacts (cleaned BOM, sourcing report,
    PartsBox import CSV) and rewrites run_summary.json, so downloads stop
    reflecting the pre-mutation BOM. The PartsBox unmatched CSV is NOT
    regenerated here -- see PERMANENT_ARTIFACT_KEYS -- and is left
    exactly as its current artifact_status says.

    Every stage below is wrapped in its own try/except and records its
    OWN artifact_status entry: one export failing must never crash this
    function, never mark an unrelated artifact current, and never touch
    canonical BOM state.

    Makes ZERO vendor API calls -- every artifact here is a local file
    write or a pure URL derivation. Safe to call from a plain rerun in
    principle, but still gated behind an explicit "Regenerate Purchasing"
    button in app.py so downloads don't silently change underneath an
    operator mid-review.
    """
    active_bom_state = response.get("_active_bom_state")
    if active_bom_state is None:
        return response

    artifact_status = response.setdefault("artifact_status", _initial_artifact_status())
    run_id = response.get("run", {}).get("run_id", "")

    run_info = response.get("run", {})
    source_file_name = run_info.get("source_file_name") or "bom"
    source_stem = Path(source_file_name).stem

    output_folder = os.path.dirname(response["outputs"].get("cleaned_csv") or "") or OUTPUT_FOLDER
    os.makedirs(output_folder, exist_ok=True)
    dataframe = active_bom_state.dataframe

    # Superseded by this attempt's outcome, not accumulated forever --
    # each stage below re-records its own current failure (if any).
    errors = []

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
        workbook_path = response["outputs"].get("cleaned_workbook") or build_output_paths(
            source_file_name, output_folder, workbook_suffix=OUTPUT_CLEAN_WORKBOOK_SUFFIX
        )[0]
        _regenerate_cleaned_workbook(active_bom_state, workbook_path)
        response["outputs"]["cleaned_workbook"] = workbook_path
        artifact_status["cleaned_workbook"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["cleaned_workbook"] = STATUS_FAILED
        errors.append(f"Cleaned workbook regeneration failed: {exc}")

    try:
        sourcing_report_path = export_sourcing_report(
            dataframe, output_folder, file_stem=f"{source_stem}_sourcing_report"
        )
        response["outputs"]["sourcing_report"] = sourcing_report_path
        artifact_status["sourcing_report"] = STATUS_CURRENT
    except Exception as exc:
        artifact_status["sourcing_report"] = STATUS_FAILED
        errors.append(f"Sourcing report regeneration failed: {exc}")

    project_name = str(run_info.get("project_name") or "").strip()
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

    response["digikey_cart_link"] = _regenerate_purchasing_artifacts(
        dataframe, run_id, output_folder, source_stem, artifact_status, response["outputs"], errors
    )

    response["purchasing_regeneration_errors"] = errors

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

        purchasing_errors = []

        if run_sourcing and (use_mouser_sourcing or use_digikey_sourcing):
            response["messages"].append("Running supplier sourcing.")
            supplier_mode = os.getenv("SUPPLIER_MODE", "mouser_then_digikey").strip().lower()
            digikey = DigiKeyClient()

            # The authoritative source-selection boundary passed to
            # apply_sourcing_decisions() below. A `lambda row: None`
            # lookup alone is NOT sufficient to disable a supplier --
            # sourcing_engine's cache reads happen before any lookup
            # callable is ever considered, so a disabled supplier's stale
            # cached result from a previous (enabled) run could otherwise
            # still win. See
            # Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md.
            if not use_mouser_sourcing and use_digikey_sourcing:
                enabled_sources = {"digikey"}
            elif use_mouser_sourcing and not use_digikey_sourcing:
                enabled_sources = {"mouser"}
            elif supplier_mode == "digikey_only":
                enabled_sources = {"digikey"}
            else:
                enabled_sources = {"mouser", "digikey"}

            if not use_mouser_sourcing and use_digikey_sourcing:
                response["messages"].append("Supplier mode: DigiKey only.")
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=lambda row: None,
                    digikey_lookup=digikey.find_best_match_for_row,
                    enabled_sources=enabled_sources,
                )
            elif use_mouser_sourcing and not use_digikey_sourcing:
                response["messages"].append("Supplier mode: Mouser only.")
                mouser = MouserClient()
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=mouser.find_best_match_for_row,
                    digikey_lookup=lambda row: None,
                    enabled_sources=enabled_sources,
                )
            elif supplier_mode == "digikey_only":
                response["messages"].append("Supplier mode: DigiKey only.")
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=lambda row: None,
                    digikey_lookup=digikey.find_best_match_for_row,
                    enabled_sources=enabled_sources,
                )
            else:
                response["messages"].append("Supplier mode: Mouser first, DigiKey fallback.")
                mouser = MouserClient()
                result.clean_bom = apply_sourcing_decisions(
                    result.clean_bom,
                    mouser_lookup=mouser.find_best_match_for_row,
                    digikey_lookup=digikey.find_best_match_for_row,
                    enabled_sources=enabled_sources,
                )

            sourcing_report_path = export_sourcing_report(
                result.clean_bom,
                output_folder,
                file_stem=f"{source_stem}_sourcing_report",
            )
            response["outputs"]["sourcing_report"] = sourcing_report_path
            response["messages"].append(f"Sourcing report exported to: {sourcing_report_path}")

            # No DigiKey MyLists call anywhere in this normal-flow path --
            # see the module docstring and
            # Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md.
            response["digikey_cart_link"] = _regenerate_purchasing_artifacts(
                result.clean_bom,
                run_id,
                output_folder,
                source_stem,
                response["artifact_status"],
                response["outputs"],
                purchasing_errors,
            )
            response["summary"]["mouser_export_items"] = build_purchasing_lines(
                result.clean_bom, "mouser", run_id=run_id
            ).item_count
            response["summary"]["digikey_list_items"] = build_purchasing_lines(
                result.clean_bom, "digikey", run_id=run_id
            ).item_count
            if response["outputs"].get("mouser_export_csv"):
                response["messages"].append(
                    f"Mouser export exported to: {response['outputs']['mouser_export_csv']}"
                )
            if response["outputs"].get("digikey_list_csv"):
                response["messages"].append(
                    f"DigiKey list exported to: {response['outputs']['digikey_list_csv']}"
                )
            response["errors"].extend(purchasing_errors)
        elif run_sourcing:
            response["messages"].append("Supplier sourcing skipped: no suppliers selected.")
            response["artifact_status"]["digikey_list_csv"] = STATUS_NOT_REQUIRED
            response["artifact_status"]["digikey_cart_link"] = STATUS_NOT_REQUIRED
            response["artifact_status"]["mouser_export_csv"] = STATUS_NOT_REQUIRED
        else:
            response["messages"].append("Supplier sourcing skipped.")
            response["artifact_status"]["digikey_list_csv"] = STATUS_NOT_REQUIRED
            response["artifact_status"]["digikey_cart_link"] = STATUS_NOT_REQUIRED
            response["artifact_status"]["mouser_export_csv"] = STATUS_NOT_REQUIRED

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


def start_manual_bom_workflow(run_id=None):
    """
    Creates an empty, schema-correct working BOM for when a part is
    added via Search before any file has been uploaded -- Search is the
    default/primary intake method and must not require an upload first.
    Uses bom_cleaner.STANDARD_COLUMNS (imported, not duplicated) so a BOM
    started this way and a BOM started by uploading a file always share
    identical DataFrame columns and can be freely merged later (see
    ActiveBomState.add_rows(), used when a file is uploaded after parts
    were already added manually).

    Deliberately does nothing else: no PartsBox project/storage, no
    sourcing, no exports -- there is nothing to process yet. The first
    row (and its sourcing/PartsBox match) is added by the caller via
    ActiveBomState.add_row() + review_actions.apply_replacement(), the
    exact same seam Find Replacement already uses, not a second
    "manually added row" pipeline.
    """
    response = _empty_result()
    run_id = run_id or new_run_id()

    response["run"] = {
        "run_id": run_id,
        "project_name": "",
        "build_quantity": 1,
        "source_file_name": "(manually added parts)",
    }
    response["success"] = True
    response["messages"].append(
        "Started a new working BOM from Search. Add parts, or upload a BOM file to add more."
    )

    empty_bom = pd.DataFrame(columns=STANDARD_COLUMNS).astype(object)
    active_bom_state = ActiveBomState(empty_bom, run_id)
    active_bom_state.dataframe["customer_reference"] = ""

    response["_active_bom_state"] = active_bom_state
    response["bom_rows"] = []
    response["review_items"] = []
    response["results_summary"] = active_bom_state.summary_counts()

    return response
