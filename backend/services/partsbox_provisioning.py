"""Provision a Project's PartsBox artifacts: project + Production storage box.

Baseline is the POC (`poc/src/partsbox_client.py`), whose create_project /
create_storage_location calls are proven; this adds the platform concerns the
POC never had — idempotency, per-artifact status, dry-run honesty, and the
filter gap.

THREE artifacts are required per Project (see the module docstring of the API
route for the product rule):

  1. PartsBox project        -> named with the HUMAN name ("aedvdv"), not the
                                reference/identifier ("TV-df").
  2. PartsBox storage box    -> name BYTE-IDENTICAL to the project name, tagged
                                ["Production"]. The tag goes on the LOCATION,
                                not the project.
  3. Per-project build filter -> location name == project name AND tags contains
                                "Production".

Artifact 3 CANNOT be automated. The PartsBox API exposes no filter/preset/saved-
search operation of any kind (verified against https://partsbox.com/api.html —
part/*, stock/*, lot/*, storage/*, project/* only). Filter presets are a UI-only
feature. So rather than fake it, we report `filter.status = "manual_required"`
and the UI shows a one-step action; a human confirms it and we record that.

Dry run: when PARTSBOX_DRY_RUN is on, the client echoes write payloads instead
of sending them. We NEVER record a dry-run echo as a real id — the result is
reported as `dry_run` and the Project stays un-provisioned. Anything else would
be exactly the "fabricated success" this replaces.
"""

from __future__ import annotations

import logging

from services.partsbox_client import PartsBoxClient

log = logging.getLogger("autobom.partsbox")

PRODUCTION_TAG = "Production"


def _record(resp):
    """Unwrap a create/find response to the underlying record dict."""
    if not isinstance(resp, dict):
        return None
    if resp.get("dry_run"):
        return None
    data = resp.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else None
    # Some operations return the record at the top level.
    return resp if any(str(k).startswith(("project/", "storage/")) for k in resp) else None


def _id_of(record, kind: str):
    if not isinstance(record, dict):
        return None
    return record.get(f"{kind}/id") or record.get("id")


def _is_dry(resp) -> bool:
    return isinstance(resp, dict) and bool(resp.get("dry_run"))


def plan(name: str) -> dict:
    """Exactly what would be sent to PartsBox — for pre-flight approval."""
    return {
        "project": {"operation": "project/create", "project/name": name},
        "storage": {"operation": "storage/create", "storage/name": name,
                    "storage/tags": [PRODUCTION_TAG]},
        "filter": {"operation": None, "reason": "PartsBox exposes no filter/preset API",
                   "condition": f'location name == "{name}" AND tags contains "{PRODUCTION_TAG}"'},
    }


def provision(name: str, client: PartsBoxClient | None = None) -> dict:
    """Create (or adopt) the PartsBox project + Production storage box for `name`.

    Idempotent: an existing project/location with the same name is reused rather
    than duplicated, so a retry after a partial failure completes the missing
    half instead of creating a second box.

    Returns a status dict — never raises. The caller persists whatever actually
    succeeded, so a partial result stays visibly partial.
    """
    client = client or PartsBoxClient()
    name = (name or "").strip()
    out = {
        "name": name,
        "dryRun": bool(getattr(client, "dry_run", False)),
        "project": {"status": "pending", "id": None},
        "storage": {"status": "pending", "id": None},
        # No API exists for this one — see module docstring.
        "filter": {"status": "manual_required", "automatable": False,
                   "condition": f'location name == "{name}" AND tags contains "{PRODUCTION_TAG}"'},
        "error": None,
    }
    if not name:
        out["error"] = "Project name is empty — nothing to create in PartsBox."
        out["project"]["status"] = out["storage"]["status"] = "failed"
        return out

    # ---- 1. Project ------------------------------------------------------- #
    try:
        existing = client.find_project_by_name(name)
        if existing:
            out["project"] = {"status": "exists", "id": _id_of(existing, "project")}
        else:
            resp = client.create_project(name)
            if _is_dry(resp):
                out["project"]["status"] = "dry_run"
            else:
                rec = _record(resp)
                out["project"] = {"status": "created", "id": _id_of(rec, "project")}
    except Exception as exc:
        log.warning("PartsBox project provisioning failed for %r: %s", name, exc)
        out["project"]["status"] = "failed"
        out["error"] = f"PartsBox project creation failed: {exc}"
        return out   # no storage box without a project

    # ---- 2. Storage location (byte-identical name, Production tag) --------- #
    try:
        existing = client.find_storage_by_name(name)
        if existing:
            out["storage"] = {"status": "exists", "id": _id_of(existing, "storage")}
        else:
            resp = client.create_storage_location(name, tags=[PRODUCTION_TAG])
            if _is_dry(resp):
                out["storage"]["status"] = "dry_run"
            else:
                rec = _record(resp)
                out["storage"] = {"status": "created", "id": _id_of(rec, "storage")}
    except Exception as exc:
        log.warning("PartsBox storage provisioning failed for %r: %s", name, exc)
        out["storage"]["status"] = "failed"
        out["error"] = f"PartsBox storage location creation failed: {exc}"

    return out


def is_complete(result: dict) -> bool:
    """True only when both automatable artifacts really exist in PartsBox."""
    ok = ("created", "exists")
    return (result.get("project", {}).get("status") in ok
            and result.get("storage", {}).get("status") in ok)


# --------------------------------------------------------------------------- #
# BOM -> PartsBox project entries (the "Create PartsBox project & import" step)
# --------------------------------------------------------------------------- #
def provision_bom(project_name: str, lines, client: PartsBoxClient | None = None) -> dict:
    """Provision the Project's PartsBox box, then import the BOM lines into it.

    The whole matching/entry-building pipeline is the POC's, already ported to
    services/partsbox_project_builder (build_project_entries ->
    find_part_by_mpn_and_manufacturer -> project/add-entries). This wires it to
    a real Project + storage box and reports what actually happened.

    Replaces a pure client-side illusion: the UI ran a 1100ms setTimeout, set
    `bom.partsbox = "PB-052"` in browser memory, and displayed the BOM's own
    line count as "N lines imported". Nothing was ever sent to PartsBox.

    One box per PCB Project (CLAUDE.md), so the PartsBox project is named after
    the Project, not the BOM — re-importing a revised BOM reuses the same box.
    """
    from services.partsbox_project_builder import build_project_entries

    client = client or PartsBoxClient()
    result = provision(project_name, client=client)
    result["entriesAdded"] = 0
    result["unmatched"] = 0
    result["entries"] = {"status": "pending"}
    result["url"] = client.project_web_url(result["project"].get("id"))

    project_id = result["project"].get("id")
    if not project_id:
        # Dry run, or the project step failed — never claim an import.
        result["entries"]["status"] = "dry_run" if result.get("dryRun") else "skipped"
        return result

    try:
        import pandas as pd
        df = pd.DataFrame([{
            "mpn": (l.mpn or ""),
            "manufacturer": (l.mfr or ""),
            "description": (l.description or ""),
            # The POC's quantity rule reads qty_per_board; a BOM line's qty IS
            # the per-board quantity.
            "qty_per_board": l.qty,
            "designators": getattr(l, "designators", "") or "",
        } for l in lines])

        entries, unmatched_rows = build_project_entries(df, client)
        entries = [e for e in entries if e]
        result["unmatched"] = len(unmatched_rows)

        if not entries:
            result["entries"]["status"] = "empty"
            return result

        resp = client.add_project_entries(project_id, entries)
        if _is_dry(resp):
            result["entries"]["status"] = "dry_run"
        else:
            result["entries"]["status"] = "added"
            result["entriesAdded"] = len(entries)
    except Exception as exc:
        log.warning("PartsBox entry import failed for %r: %s", project_name, exc)
        result["entries"]["status"] = "failed"
        result["error"] = f"PartsBox line import failed: {exc}"

    return result
