import os
import re
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
SRC_FOLDER = PROJECT_ROOT / "src"
INPUT_FOLDER = PROJECT_ROOT / "input"

load_dotenv(REPO_ROOT / ".env", override=True)

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from workflow_runner import run_bom_workflow  # noqa: E402


def safe_upload_name(file_name):
    name = Path(file_name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("_") or "uploaded_bom"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def save_uploaded_file(uploaded_file):
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    output_path = INPUT_FOLDER / safe_upload_name(uploaded_file.name)

    with output_path.open("wb") as file_handle:
        file_handle.write(uploaded_file.getbuffer())

    return output_path


def show_download(label, file_path):
    if not file_path:
        return

    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return

    with path.open("rb") as file_handle:
        st.download_button(
            label=label,
            data=file_handle,
            file_name=path.name,
            mime="application/octet-stream",
        )


st.set_page_config(page_title="BOM Automation Tool", layout="wide")
st.title("BOM Automation Tool")

uploaded_file = st.file_uploader("Upload BOM", type=["csv", "xlsx"])

left, right = st.columns(2)
with left:
    build_quantity = st.number_input("Build quantity", min_value=1, value=1, step=1)
    project_name = st.text_input("PartsBox project name")
    project_description = st.text_input("Project description")

with right:
    run_partsbox = st.checkbox("Run PartsBox", value=True)
    run_sourcing = st.checkbox("Run supplier sourcing", value=True)
    use_mouser_sourcing = st.checkbox(
        "Use Mouser sourcing",
        value=True,
        disabled=not run_sourcing,
    )
    use_digikey_sourcing = st.checkbox(
        "Use DigiKey sourcing",
        value=True,
        disabled=not run_sourcing,
    )
    run_mouser_cart = st.checkbox("Create Mouser cart", value=False)
    run_digikey_mylist = st.checkbox("Create DigiKey MyList", value=False)

if st.button("Run BOM Automation", type="primary"):
    if uploaded_file is None:
        st.error("Upload a CSV or XLSX BOM before running.")
    else:
        source_path = save_uploaded_file(uploaded_file)

        with st.spinner("Running BOM automation..."):
            result = run_bom_workflow(
                source_file_path=source_path,
                build_quantity=int(build_quantity),
                project_name=project_name,
                project_description=project_description,
                run_partsbox=run_partsbox,
                run_sourcing=run_sourcing,
                run_mouser_cart=run_mouser_cart,
                run_digikey_mylist=run_digikey_mylist,
                use_mouser_sourcing=run_sourcing and use_mouser_sourcing,
                use_digikey_sourcing=run_sourcing and use_digikey_sourcing,
            )

        if result.get("success"):
            st.success("BOM automation completed.")
        else:
            st.warning("BOM automation finished with errors.")

        summary = result.get("summary", {})
        metric_columns = st.columns(6)
        metric_columns[0].metric("Mouser sourced", summary.get("mouser_sourced", 0))
        metric_columns[1].metric("DigiKey sourced", summary.get("digikey_sourced", 0))
        metric_columns[2].metric("Manual / wall review", summary.get("manual_review", 0))
        metric_columns[3].metric("Mouser cart items", summary.get("mouser_cart_items", 0))
        metric_columns[4].metric("DigiKey list items", summary.get("digikey_list_items", 0))
        metric_columns[5].metric(
            "PartsBox entries added",
            summary.get("partsbox_entries_added", 0),
        )

        for error in result.get("errors", []):
            st.error(error)

        for message in result.get("messages", []):
            st.info(message)

        warnings = result.get("warnings", [])
        if warnings:
            with st.expander(f"Warnings ({len(warnings)})"):
                for warning in warnings:
                    st.write(warning)

        st.subheader("Outputs")
        outputs = result.get("outputs", {})
        download_labels = {
            "cleaned_workbook": "Download cleaned workbook",
            "cleaned_csv": "Download cleaned CSV",
            "sourcing_report": "Download sourcing report",
            "digikey_list_csv": "Download DigiKey list CSV",
            "partsbox_import_csv": "Download PartsBox import CSV",
            "partsbox_unmatched_csv": "Download PartsBox unmatched CSV",
            "run_summary": "Download run summary",
        }

        for key, label in download_labels.items():
            show_download(label, outputs.get(key))
