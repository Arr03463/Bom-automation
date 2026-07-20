"""GET /api/bootstrap — the session user's AUTHORIZED slice, shaped like the
prototype's seedState() so the frontend store hydrates from it directly.

Role-scoped now (carries to production unchanged): Admin sees full user records
and all audit; Designer/Production see a people-directory + entity-scoped audit.
The purchasing bucket and org structure (programs/projects) are intentionally
shared surfaces. Inventory is empty here — PartsBox hydration is wired later.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api import serializers as S
from auth.deps import require_user
from db.models import (
    Audit, Bom, BomLine, Collection, CollectionItem, Configuration,
    Notification, Program, Project, Pushback, Request, Supplier, User,
)
from db.session import get_db

router = APIRouter(tags=["bootstrap"])


def _config_map(db: Session) -> dict:
    return {c.key: (c.value or {}) for c in db.query(Configuration).all()}


def _system(cfg: dict) -> dict:
    workflow = cfg.get("workflow", {})
    settings_cfg = cfg.get("system", {})
    batch = cfg.get("batch", {"main": {"intervalMin": 360}, "critical": {"intervalMin": 180}})
    return {
        "status": [
            {"id": "app", "label": "Application", "state": "green", "detail": "All services operational"},
            {"id": "mouser", "label": "Mouser API", "state": "green", "detail": "Connected"},
            {"id": "digikey", "label": "DigiKey API", "state": "green", "detail": "Connected"},
            {"id": "partsbox", "label": "PartsBox API", "state": "green", "detail": "Connected"},
            {"id": "db", "label": "Database", "state": "green", "detail": "Healthy"},
        ],
        "workflow": {
            "maxExceptionLoops": workflow.get("maxExceptionLoops", 3),
            "staleThresholdHours": workflow.get("staleThresholdHours", 24),
            "overdueHours": workflow.get("overdueHours", 24),
            "autoOrder": workflow.get("autoOrder", False),
            "requireBudgetCode": workflow.get("requireBudgetCode", True),
            "mouserFirst": workflow.get("mouserFirst", True),
        },
        "settings": {
            "sessionTimeoutMin": settings_cfg.get("sessionTimeoutMin", 30),
            "requireSupervisorForInterns": settings_cfg.get("requireSupervisorForInterns", True),
            "defaultRole": None,
            "mfa": settings_cfg.get("mfa", False),
        },
        "batch": {
            "main": {"intervalMin": batch.get("main", {}).get("intervalMin", 360),
                     "nextRunMin": 142, "lastRun": "2h ago", "writing": False},
            "critical": {"intervalMin": batch.get("critical", {}).get("intervalMin", 180),
                         "nextRunMin": 47, "lastRun": "2h ago", "writing": False},
        },
        "jobs": [],
        "stuck": [],
    }


@router.get("/bootstrap")
def bootstrap(user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    is_admin = "admin" in (user.roles or [])

    users = db.query(User).all()
    users_by_id = {u.id: u for u in users}

    # Users: Admin -> full records; others -> directory, but the CURRENT user
    # always gets their full record (their own roles/caps drive the UI).
    if is_admin:
        users_out = [S.user_full(u) for u in users]
    else:
        users_out = [S.user_full(u) if u.id == user.id else S.user_dir(u) for u in users]

    # Programs (+ their project id lists) and projects (object keyed by id).
    projects = db.query(Project).all()
    proj_by_program = defaultdict(list)
    for pr in projects:
        if pr.program_id:
            proj_by_program[pr.program_id].append(pr.id)
    programs_out = [S.program(p, users_by_id, proj_by_program.get(p.id, []))
                    for p in db.query(Program).all()]
    projects_out = {pr.id: S.project(pr, users_by_id) for pr in projects}

    # Collections (+ items). Designer collections only (dev deferred).
    items_by_col = defaultdict(list)
    for ci in db.query(CollectionItem).all():
        items_by_col[ci.collection_id].append(ci)
    collections_out = []
    for c in db.query(Collection).filter(Collection.role != "development").all():
        cd = S.collection(c, items_by_col.get(c.id, []))
        cd["creator"] = users_by_id[c.owner_id].name if c.owner_id in users_by_id else None
        collections_out.append(cd)

    # BOMs (+ lines + pushback).
    lines_by_bom = defaultdict(list)
    for li in db.query(BomLine).all():
        lines_by_bom[li.bom_id].append(li)
    pb_by_bom = {}
    for pb in db.query(Pushback).filter(Pushback.state != "cancelled").all():
        pb_by_bom.setdefault(pb.bom_id, pb)
    boms_out = [S.bom(b, lines_by_bom.get(b.id, []), pb_by_bom.get(b.id), users_by_id)
                for b in db.query(Bom).all()]

    # Requests (shared bucket), notifications (role-matched), suppliers, audit.
    requests_out = [S.request(r, users_by_id) for r in db.query(Request).all()]
    user_roles = set(user.roles or [])
    notifications_out = [S.notification(n) for n in db.query(Notification).all()
                         if user_roles & set(n.for_roles or [])]
    suppliers_out = [S.supplier(s) for s in db.query(Supplier).all()]

    audit_rows = db.query(Audit).all()
    if is_admin:
        audit_out = [S.audit(a, users_by_id) for a in audit_rows]
    else:
        visible = {b["id"] for b in boms_out} | {c["id"] for c in collections_out} | set(projects_out)
        audit_out = [S.audit(a, users_by_id) for a in audit_rows if a.entity_id in visible]

    cfg = _config_map(db)
    return {
        "users": users_out,
        "programs": programs_out,
        "projects": projects_out,
        "collections": collections_out,
        "boms": boms_out,
        "requests": requests_out,
        "notifications": notifications_out,
        "suppliers": suppliers_out,
        "audit": audit_out,
        "system": _system(cfg),
        "inventory": [],          # PartsBox hydration wired in a later step
        "investigations": [], "recommendations": [], "reworks": [], "firmwares": [],
        "comments": {}, "datasheets": {},
        "seq": {"req": 100, "po": 3000, "bom": 100, "col": 100, "inv": 100, "rec": 100},
    }
