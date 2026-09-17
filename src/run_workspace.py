import re
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"


def new_run_id():
    return uuid.uuid4().hex


def safe_upload_name(file_name):
    name = Path(file_name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("_") or "uploaded_bom"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def build_run_workspace(run_id=None, runs_root=None):
    """
    Create an isolated input/output directory pair for one BOM run.

    Every run gets its own directory under runs/<run_id>/, so two sessions
    uploading a file with the same name never share a path.
    """
    run_id = run_id or new_run_id()
    run_root = Path(runs_root) if runs_root else RUNS_ROOT
    run_dir = run_root / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "input_dir": input_dir,
        "output_dir": output_dir,
    }


def save_uploaded_file(input_dir, file_name, file_bytes):
    input_dir = Path(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_path = input_dir / safe_upload_name(file_name)

    with output_path.open("wb") as file_handle:
        file_handle.write(file_bytes)

    return output_path
