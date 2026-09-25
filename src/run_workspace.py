import os
import re
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "runs"


def resolve_runs_root():
    """
    AUTOBOM_RUNS_ROOT lets a deployment put runtime data outside the
    source checkout (e.g. C:\\AutoBOM\\prod\\data\\runs) instead of being
    forced to use runs/ inside the repo -- useful for separating a
    release checkout from persistent runtime state, and for keeping
    production/development data apart when both run from different
    checkouts on the same machine. Falls back to the in-repo default
    (RUNS_ROOT) when unset, so existing behavior/tests are unaffected.
    Read at call time (not baked into a module-level constant) so a
    change takes effect without re-importing this module.
    """
    override = os.getenv("AUTOBOM_RUNS_ROOT", "").strip()
    return Path(override) if override else RUNS_ROOT


def new_run_id():
    return uuid.uuid4().hex


def safe_upload_name(file_name):
    name = Path(file_name).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("_") or "uploaded_bom"
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix}"


def build_run_workspace(run_id=None, runs_root=None, cleanup=True):
    """
    Create an isolated input/output directory pair for one BOM run.

    Every run gets its own directory under runs/<run_id>/, so two sessions
    uploading a file with the same name never share a path.

    Also the one safe, predictable point where old run directories are
    reaped (see run_retention.cleanup_old_runs): once per new run
    kick-off, never mid-workflow. cleanup=False lets callers (tests, or a
    future maintenance script) opt out explicitly. A cleanup failure is
    caught by cleanup_old_runs() itself and never blocks workspace
    creation -- run isolation must not depend on retention succeeding.
    """
    run_id = run_id or new_run_id()
    run_root = Path(runs_root) if runs_root else resolve_runs_root()
    run_dir = run_root / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if cleanup:
        try:
            from run_retention import cleanup_old_runs

            cleanup_old_runs(runs_root=run_root, active_run_id=run_id)
        except Exception:
            pass

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
