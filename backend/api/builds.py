"""Build endpoints — Production's assembly action.

POST /api/builds/preview  - consumption plan only; NEVER touches PartsBox.
POST /api/builds          - create the Build (PartsBox build/create + QR).

Safety posture, deliberately conservative because this decrements REAL stock:
- The push-back gate is enforced server-side, not just in the UI.
- PartsBox writes honor PARTSBOX_DRY_RUN like every other write; a dry run
  returns the exact payload that a live call would send.
- The consumption plan is computed by ONE pure function used by both preview
  and create, so what you preview is provably what executes.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.deps import require_user
from db.models import Audit, Bom, BomLine, Build, Project, User
from db.session import get_db
from services.build_service import BuildGateError, build_gate, consumption_plan

log = logging.getLogger("autobom.build")
router = APIRouter(tags=["builds"])


def _next_build_id(db: Session) -> str:
    nums = [int(m.group(1)) for (i,) in db.query(Build.id).all()
            if (m := re.match(r"BLD-0*(\d+)$", str(i)))]
    return f"BLD-{(max(nums) + 1) if nums else 1:04d}"


def _load(db: Session, bom_id: str) -> tuple[Bom, list[BomLine]]:
    bom = db.get(Bom, bom_id)
    if bom is None:
        raise HTTPException(404, "BOM not found")
    lines = db.query(BomLine).filter(BomLine.bom_id == bom_id).all()
    if not lines:
        raise HTTPException(400, "This BOM has no lines to build.")
    return bom, lines


def _plan(db: Session, body: dict) -> tuple[Bom, dict, int]:
    bom, lines = _load(db, body.get("bomId"))
    build_qty = int(body.get("buildQty") or bom.build_qty or 1)
    if build_qty <= 0:
        raise HTTPException(400, "buildQty must be greater than zero.")
    try:
        plan = consumption_plan(bom, lines, body.get("overlay") or {}, build_qty)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return bom, plan, build_qty


def _resolve_partsbox_project(pb, bom: Bom, project: Project) -> str:
    """Find the PartsBox project this Build consumes from.

    Refuses to guess. build/create decrements real stock, so consuming against
    the wrong PartsBox project is worse than failing: it would silently drain
    another board's box. Resolution order:
      1. bom.partsbox_ref  - the explicit link, when one has been recorded
      2. PartsBox project whose name matches the AutoBOM project name (read-only)
      3. hard 400 explaining that the project box must exist first

    (There is no Project.partsbox_ref column yet; persisting the link belongs to
    the Inventory Activation work, where project boxes are actually created.)
    """
    if bom.partsbox_ref:
        return bom.partsbox_ref
    try:
        match = pb.find_project_by_name(project.name)
    except Exception as exc:                       # a lookup failure must not read as "not linked"
        raise HTTPException(502, f"Could not reach PartsBox to resolve the project box: {exc}") from exc
    pid = (match or {}).get("project/id") if isinstance(match, dict) else None
    if not pid:
        raise HTTPException(400, (
            f"No PartsBox project box found for {project.name!r}. Create the project box in "
            "PartsBox (or record its id on the BOM) before running a Build - AutoBOM will not "
            "guess which box to consume from."
        ))
    return pid


@router.post("/builds/preview")
def preview_build(body: dict = Body(...), user: User = Depends(require_user),
                  db: Session = Depends(get_db)) -> dict:
    """What would this Build consume? Read-only; never calls PartsBox."""
    bom, plan, build_qty = _plan(db, body)
    try:
        gate = build_gate(db, bom.id, force_waive_reason=body.get("forceWaiveReason"))
    except BuildGateError as exc:
        # A preview should still render when blocked - the UI needs to explain why.
        gate = {"allowed": False, "waived": False, "reason": str(exc)}
    return {"bomId": bom.id, "projectId": bom.project_id, "buildQty": build_qty,
            "gate": gate, **plan}


@router.post("/builds")
def create_build(body: dict = Body(...), user: User = Depends(require_user),
                 db: Session = Depends(get_db)) -> dict:
    bom, plan, build_qty = _plan(db, body)
    project = db.get(Project, bom.project_id)
    if project is None:
        raise HTTPException(400, "BOM has no project.")

    waive = body.get("forceWaiveReason")
    if waive and "admin" not in (user.roles or []):
        raise HTTPException(403, "Only an Admin may force-waive the push-back gate.")
    try:
        gate = build_gate(db, bom.id, force_waive_reason=waive)
    except BuildGateError as exc:
        raise HTTPException(409, str(exc)) from exc

    if not plan["consume"]:
        raise HTTPException(400, "Nothing to consume - every line is skipped or deferred.")

    from services.partsbox_client import PartsBoxClient
    pb = PartsBoxClient()
    pb_project_id = _resolve_partsbox_project(pb, bom, project)
    seq_no = db.query(Build).filter(Build.project_id == bom.project_id).count() + 1
    try:
        result = pb.create_build(
            pb_project_id, build_qty, plan["consume"],
            notes=f"AutoBOM build #{seq_no} of {bom.name} (v{bom.version})",
        )
    except Exception as exc:
        # PartsBox failure must NOT leave a phantom Build row behind.
        log.warning("build/create failed for %s: %s", bom.id, exc)
        raise HTTPException(502, f"PartsBox build/create failed: {exc}") from exc

    dry = bool(isinstance(result, dict) and result.get("dry_run"))
    pb_build_id = None
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        pb_build_id = data.get("build/id") or data.get("id")

    build_id = _next_build_id(db)
    qr_url = pb.build_qr_image_url(pb_build_id) if pb_build_id else None
    db.add(Build(id=build_id, project_id=bom.project_id, bom_id=bom.id, seq_no=seq_no,
                 state="dry-run" if dry else "created", build_qty=build_qty,
                 overlay={"overlay": body.get("overlay") or {}, "plan": plan,
                          "partsboxBuildId": pb_build_id, "gate": gate},
                 qr_url=qr_url, actor_id=user.id))
    db.add(Audit(id=f"au-build-{uuid.uuid4().hex[:10]}",
                 ts="Today " + datetime.now(timezone.utc).strftime("%H:%M"), actor_id=user.id,
                 role=(user.roles or ["production"])[0],
                 action=f"Build {build_id} created ({'dry-run' if dry else 'LIVE'}) - "
                        f"{plan['summary']['consumed']} lines, {plan['summary']['units']} units"
                        + (f" [FORCE-WAIVED: {gate.get('reason')}]" if gate.get("waived") else ""),
                 entity_id=bom.id, entity_type="bom",
                 before=f"v{bom.version}", after=build_id))
    db.commit()

    return {
        "id": build_id, "seqNo": seq_no, "bomId": bom.id, "projectId": bom.project_id,
        "buildQty": build_qty, "dryRun": dry, "gate": gate,
        "partsboxBuildId": pb_build_id,
        "qrUrl": qr_url,                                   # rendered inline when present
        "openInPartsBox": pb.build_web_url(pb_build_id),   # documented fallback
        **plan,
        "partsbox": result if dry else {"ok": True},
    }
