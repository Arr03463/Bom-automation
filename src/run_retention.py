import os
import shutil
import time
from pathlib import Path

from run_workspace import resolve_runs_root

DEFAULT_RETENTION_DAYS = 14
DEFAULT_MAX_RUNS = 200


def _retention_days():
    try:
        value = float(os.getenv("AUTOBOM_RUN_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return value if value > 0 else 0


def _max_runs():
    try:
        value = int(os.getenv("AUTOBOM_MAX_RUNS", DEFAULT_MAX_RUNS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RUNS
    return value if value > 0 else 0


def cleanup_old_runs(runs_root=None, active_run_id=None, retention_days=None, max_runs=None):
    """
    Deletes old runs/<run_id> directories based on an age policy
    (AUTOBOM_RUN_RETENTION_DAYS) and/or a count policy (AUTOBOM_MAX_RUNS,
    keeping only the newest N by directory mtime -- a total cap that
    includes the active run, since it is always the newest). Either
    policy can be disabled by setting its value to 0.

    Never deletes active_run_id -- the run this call site is currently
    working with, regardless of its age or position. This is NOT a
    guarantee that every other currently-open browser session's run is
    protected: cleanup has no registry of what other sessions are doing
    and will reap an older run that's still open in someone else's tab if
    it crosses the age/count threshold (Codex F4). Deliberately not
    solved with a session registry here -- that's disproportionate
    complexity for a small internal tool; use conservative
    AUTOBOM_RUN_RETENTION_DAYS/AUTOBOM_MAX_RUNS defaults instead, and see
    Documentation/AutoBOM_Deployment_Guide.md for the documented
    tradeoff. Never raises: every
    failure (a missing directory, a permissions error, a file busy on
    Windows, an unexpected exception) is caught and returned in
    result["errors"] instead of propagating, so a retention problem can
    never crash a BOM run or a page load. Intended to be called only at a
    predictable, safe boundary -- today, once per new run kick-off (see
    run_workspace.build_run_workspace()) -- never from inside an
    in-progress workflow.
    """
    result = {"deleted": [], "kept": [], "errors": []}

    try:
        runs_root = Path(runs_root) if runs_root else resolve_runs_root()
        retention_days = _retention_days() if retention_days is None else retention_days
        max_runs = _max_runs() if max_runs is None else max_runs

        if not runs_root.exists():
            return result

        entries = [path for path in runs_root.iterdir() if path.is_dir()]
        now = time.time()

        def mtime(path):
            try:
                return path.stat().st_mtime
            except OSError:
                return now

        entries.sort(key=mtime, reverse=True)
        cutoff = now - (retention_days * 86400) if retention_days else None

        for index, path in enumerate(entries):
            run_id = path.name
            if run_id == active_run_id:
                result["kept"].append(run_id)
                continue

            too_old = cutoff is not None and mtime(path) < cutoff
            over_count = bool(max_runs) and index >= max_runs

            if not (too_old or over_count):
                result["kept"].append(run_id)
                continue

            try:
                shutil.rmtree(path)
                result["deleted"].append(run_id)
            except OSError as exc:
                result["errors"].append(f"{run_id}: {exc}")
    except Exception as exc:  # noqa: BLE001 - retention must never crash a run
        result["errors"].append(str(exc))

    return result
