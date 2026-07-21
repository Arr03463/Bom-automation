"""Entity write endpoints for Phase 3 UI wiring.

Every write AWAITs and returns the authoritative persisted object (the store
applies the return value — no optimistic reconcile). Push-back apply commits the
recommended lines to the master BOM AND increments the version (bom_versions row
+ pushbacks.resolved_at_version_id); the Decision Engine (routing/escalation/
gating/coverage) is Phase 4.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from api import serializers as SR
from auth.deps import require_user
from db.models import (
    Audit, Bom, BomLine, BomVersion, Collection, CollectionItem, Comment,
    Configuration, Notification, Program, Project, Pushback, PushbackReason,
    PushbackUrgency, Request, Supplier, User,
)
from db.session import get_db

router = APIRouter(tags=["entities"])
NOW = lambda: datetime.now(timezone.utc)


def _enum_val(raw, enum_cls, default: str) -> str:
    """Validate a client-supplied enum string at the API boundary.

    Enum columns reject unknown values at write time, which surfaces as a 500.
    Turn that into an honest 400 naming the allowed values — and accept a
    case-insensitive match, since the UI labels are Title Case ("Standard")
    while the stored values are lower ("standard").
    """
    allowed = {m.value for m in enum_cls}
    if raw is None or str(raw).strip() == "":
        return default
    val = str(raw).strip()
    if val in allowed:
        return val
    lowered = val.lower()
    if lowered in allowed:
        return lowered
    raise HTTPException(400, f"Invalid value {val!r}; expected one of {sorted(allowed)}")


def _users(db: Session) -> dict:
    return {u.id: u for u in db.query(User).all()}


def _num_id(db: Session, model, prefix: str, width: int = 3) -> str:
    nums = [int(m.group(1)) for (i,) in db.query(model.id).all()
            if (m := re.match(rf"{re.escape(prefix)}-0*(\d+)$", str(i)))]
    return f"{prefix}-{(max(nums) + 1) if nums else 1:0{width}d}"


def _slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "item").lower()).strip("-")[:32] or "item"
    sid, n = base, 2
    while db.get(Project, sid) or db.get(Program, sid):
        sid = f"{base}-{n}"; n += 1
    return sid


_audit_seq = [0]


def _audit(db, user, action, entity, before="—", after="—", etype=None):
    _audit_seq[0] += 1
    db.add(Audit(id=f"au-{int(NOW().timestamp())}-{_audit_seq[0]}",
                 ts="Today " + NOW().strftime("%H:%M"), actor_id=user.id,
                 role=(user.roles or [None])[0], action=action, entity_id=entity,
                 entity_type=etype, before=before, after=after))


# --------------------------------------------------------------------------- #
# Programs / Projects / Collections (create + edit)
# --------------------------------------------------------------------------- #
@router.post("/programs")
def create_program(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    pid = _slug(db, body.get("code") or body.get("name"))
    p = Program(id=pid, name=body["name"], code=body.get("code"), identifier=body.get("code") or body.get("identifier"),
                owner_id=user.id, status="Active", description=body.get("desc"), customer=body.get("customer"),
                tags=body.get("tags") or [], notify_on_equivalent_swap=True)
    db.add(p); _audit(db, user, "Program created", pid, after="ACTIVE", etype="program"); db.commit(); db.refresh(p)
    return SR.program(p, _users(db), [])


@router.post("/projects")
def create_project(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    pid = _slug(db, body.get("name"))
    pr = Project(id=pid, name=body["name"], identifier=body.get("identifier"), lead_id=user.id,
                 program_id=body.get("program_id") or None, description=body.get("desc"), status="active")
    db.add(pr); _audit(db, user, "Project created", pid, after="ACTIVE", etype="project"); db.commit(); db.refresh(pr)
    return SR.project(pr, _users(db))


@router.post("/projects/{project_id}/partsbox")
def create_project_partsbox(project_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    pr = db.get(Project, project_id)
    if not pr:
        raise HTTPException(404, "Project not found")
    # PartsBox project-box creation is wired with inventory (item 6); record the ref.
    ref = f"PB-{project_id.upper()[:12]}"
    _audit(db, user, "PartsBox project box created", project_id, after=ref, etype="project")
    db.commit()
    out = SR.project(pr, _users(db)); out["partsbox"] = ref
    return out


@router.post("/collections")
def create_collection(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if not body.get("program"):
        raise HTTPException(400, "Program is required for a Collection.")
    cid = _num_id(db, Collection, "COL")
    c = Collection(id=cid, name=body["name"], project_id=body.get("project") or None, program_id=body["program"],
                   state="active", owner_id=user.id, role="designer", category=body.get("category"),
                   description=body.get("desc"), updated_by=user.name)
    db.add(c); _audit(db, user, "Collection created", cid, after="ACTIVE", etype="collection"); db.commit(); db.refresh(c)
    out = SR.collection(c, []); out["creator"] = user.name
    return out


@router.patch("/collections/{cid}")
def update_collection(cid: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    c = db.get(Collection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    if "name" in body: c.name = body["name"]
    if "desc" in body: c.description = body["desc"]
    if "program" in body: c.program_id = body["program"]
    if "project" in body: c.project_id = body["project"] or None
    c.updated_by = user.name
    db.commit(); db.refresh(c)
    return _collection_full(db, c)


def _collection_full(db, c):
    items = db.query(CollectionItem).filter(CollectionItem.collection_id == c.id).all()
    out = SR.collection(c, items)
    out["creator"] = db.get(User, c.owner_id).name if db.get(User, c.owner_id) else None
    return out


@router.post("/collections/{cid}/items")
def add_item(cid: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    c = db.get(Collection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    existing = db.query(CollectionItem).filter(CollectionItem.collection_id == cid).all()
    next_no = (max([i.line_no for i in existing]) + 1) if existing else 1
    db.add(CollectionItem(collection_id=cid, line_no=next_no, mpn=body["mpn"], mfr=body.get("mfr"),
                          description=body.get("desc"), qty=body.get("qty") or 1, status="needs-review",
                          note=body.get("note")))
    _audit(db, user, "Part added to collection", cid, after=body["mpn"], etype="collection")
    db.commit(); db.refresh(c)
    return _collection_full(db, c)


@router.patch("/collections/{cid}/items/{no}")
def update_item(cid: str, no: int, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    it = db.query(CollectionItem).filter(CollectionItem.collection_id == cid, CollectionItem.line_no == no).first()
    if not it:
        raise HTTPException(404, "Line not found")
    if "qty" in body:
        it.qty = body["qty"]
        if it.unit_price is not None:
            it.ext_price = round(float(it.unit_price) * (body["qty"] or 0), 4)
    if "note" in body: it.note = body["note"]
    db.commit()
    return _collection_full(db, db.get(Collection, cid))


@router.delete("/collections/{cid}/items/{no}")
def remove_item(cid: str, no: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    it = db.query(CollectionItem).filter(CollectionItem.collection_id == cid, CollectionItem.line_no == no).first()
    if it:
        db.delete(it); db.commit()
    return _collection_full(db, db.get(Collection, cid))


@router.post("/collections/{cid}/request-order")
def request_to_order(cid: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    c = db.get(Collection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    items = db.query(CollectionItem).filter(CollectionItem.collection_id == cid).all()
    rid = _num_id(db, Request, "REQ")
    critical = bool(body.get("critical"))
    snapshot = [SR.collection_item(i) for i in sorted(items, key=lambda x: x.line_no)]
    db.add(Request(id=rid, title=c.name, kind="collection", source_id=cid, source_type="collection",
                   project_id=c.project_id, from_user_id=user.id, from_role="designer", submitted="just now",
                   age=0, critical=critical, bucket_state="QUEUED_CRITICAL" if critical else "QUEUED_MAIN",
                   note=body.get("note"), items_snapshot=snapshot))
    c.state = "order-requested"; c.req_id = rid
    _audit(db, user, "Collection submitted to Purchasing", cid, before="ACTIVE", after="ORDER REQUESTED", etype="collection")
    db.commit()
    return {"collection": _collection_full(db, c), "request": SR.request(db.get(Request, rid), _users(db))}


# --------------------------------------------------------------------------- #
# Push-back handshake: send -> resolve (recommend) -> apply (+ version bump)
# --------------------------------------------------------------------------- #
@router.post("/boms/{bom_id}/pushback")
def send_pushback(bom_id: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    bom = db.get(Bom, bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    pb_id = _num_id(db, Pushback, "PB")
    program = None
    pr = db.get(Project, bom.project_id)
    to_user = None
    if pr and pr.program_id:
        prog = db.get(Program, pr.program_id)
        to_user = prog.owner_id if prog else None
    db.add(Pushback(id=pb_id, bom_id=bom_id,
                    reason=_enum_val(body.get("reason"), PushbackReason, "other"),
                    urgency=_enum_val(body.get("urgency"), PushbackUrgency, "standard"),
                    from_user_id=user.id, to_user_id=to_user,
                    state="open", note=body.get("note"), loop=1,
                    flagged_lines=body.get("flaggedLines") or [],
                    added_component_request=body.get("addedComponentRequest")))
    bom.state = "exceptions"
    # flag the lines
    for fl in (body.get("flaggedLines") or []):
        li = db.query(BomLine).filter(BomLine.bom_id == bom_id, BomLine.line_no == fl.get("lineNo")).first()
        if li:
            li.status = "needs-review"; li.ex_reason = fl.get("exReason")
    db.add(Notification(id=f"n-{pb_id}", for_roles=["designer"], group="Today", unread=True, kind="action",
                        source_role="production", target_role="designer", action_label="Resolve exceptions",
                        verb="Resolve", body=f"{bom.name} - lines flagged for engineering review.",
                        who=user.name, when="just now", entity_id=bom_id, entity_type="bom", type_label="BOM EXCEPTION",
                        routes={"designer": {"screen": "d.dashboard"}, "production": {"screen": "p.bomOverview", "id": bom_id}},
                        go={"screen": "d.dashboard"}))
    _audit(db, user, "BOM exception sent", bom_id, before="RESULTS", after="EXCEPTIONS", etype="bom")
    db.commit()
    return get_bom_full(db, bom_id)


def _open_pushback(db: Session, bom_id: str, *, pushback_id: str | None = None,
                   with_recommendation: bool = False) -> Pushback | None:
    """Pick the open push-back deterministically.

    Both halves of the handshake used `.first()` with NO ORDER BY. With more
    than one open push-back on a BOM, Postgres returns an arbitrary row, so
    Designer's recommendation could attach to one push-back while Production's
    Apply read a different one — the handshake failed at random with a
    misleading "No recommendation to apply." Order by id (zero-padded, so
    lexicographic == chronological) and let Apply target the push-back that
    actually carries a recommendation.
    """
    q = db.query(Pushback).filter(Pushback.bom_id == bom_id, Pushback.state == "open")
    if pushback_id:
        return q.filter(Pushback.id == pushback_id).first()
    if with_recommendation:
        q = q.filter(Pushback.recommendation.isnot(None))
    return q.order_by(Pushback.id).first()


@router.post("/boms/{bom_id}/resolve-pushback")
def resolve_pushback(bom_id: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    pb = _open_pushback(db, bom_id, pushback_id=body.get("pushbackId"))
    if not pb:
        raise HTTPException(404, "No open push-back on this BOM")
    pb.recommendation = {"picks": body.get("recommendations") or [], "note": body.get("note"),
                         "by": user.name, "when": "just now"}
    bom = db.get(Bom, pb.bom_id)
    db.add(Notification(id=f"n-rec-{pb.id}", for_roles=["production"], group="Today", unread=True, kind="action",
                        source_role="designer", target_role="production", action_label="Apply replacements",
                        verb="Apply", body=f"Replacements recommended for {bom.name if bom else pb.bom_id}.",
                        who=user.name, when="just now", entity_id=pb.bom_id, entity_type="bom",
                        type_label="REPLACEMENTS RECOMMENDED",
                        routes={"production": {"screen": "p.dashboard"}, "designer": {"screen": "p.bomOverview", "id": pb.bom_id}},
                        go={"screen": "p.dashboard"}))
    _audit(db, user, "Push-back resolved (recommendation)", pb.bom_id, after="RECOMMENDED", etype="bom")
    db.commit()
    return get_bom_full(db, pb.bom_id)


@router.post("/boms/{bom_id}/apply-recommendation")
def apply_recommendation(bom_id: str, body: dict = Body(default=None), user: User = Depends(require_user), db: Session = Depends(get_db)):
    bom = db.get(Bom, bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    pb = _open_pushback(db, bom_id, pushback_id=(body or {}).get("pushbackId"),
                        with_recommendation=True)
    if not pb or not pb.recommendation:
        raise HTTPException(400, "No recommendation to apply.")
    picks = (pb.recommendation or {}).get("picks") or []
    # Commit the recommended replacements onto the master BOM lines.
    for pick in picks:
        li = db.query(BomLine).filter(BomLine.bom_id == bom_id, BomLine.line_no == pick.get("lineNo")).first()
        if li:
            if pick.get("mpn"): li.mpn = pick["mpn"]
            if pick.get("mfr"): li.mfr = pick["mfr"]
            li.status = "normalised"; li.ex_reason = None; li.supplier = None; li.supplier_pn = None
    # Version increment: write a bom_versions row and link the push-back to it.
    new_version = (bom.version or 1) + 1
    ver_id = _num_id(db, BomVersion, "V")
    db.add(BomVersion(id=ver_id, bom_id=bom_id, version=new_version,
                      reason={"applied_recommendation": pb.recommendation, "pushback_id": pb.id},
                      actor_id=user.id, ts=NOW()))
    bom.version = new_version
    bom.state = "normalised"
    pb.state = "resolved"
    pb.resolved_at_version_id = ver_id
    _audit(db, user, "Applied recommendation -> BOM version bump", bom_id,
           before=f"v{new_version-1}", after=f"v{new_version}", etype="bom")
    db.commit()
    return get_bom_full(db, bom_id)


@router.patch("/boms/{bom_id}/lines/{no}")
def edit_bom_line(bom_id: str, no: int, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    li = db.query(BomLine).filter(BomLine.bom_id == bom_id, BomLine.line_no == no).first()
    if not li:
        raise HTTPException(404, "Line not found")
    for f_api, f_db in (("qty", "qty"), ("note", "note"), ("description", "description"), ("mpn", "mpn"), ("mfr", "mfr")):
        if f_api in body:
            setattr(li, f_db, body[f_api])
    db.commit()
    return get_bom_full(db, bom_id)


@router.post("/boms/{bom_id}/submit")
def submit_bom(bom_id: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    bom = db.get(Bom, bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    rid = _num_id(db, Request, "REQ")
    critical = bool(body.get("critical"))
    snapshot = [SR.bom_line(li) for li in sorted(bom.lines, key=lambda x: x.line_no)]
    db.add(Request(id=rid, title=bom.name, kind="bom", source_id=bom_id, source_type="bom", project_id=bom.project_id,
                   from_user_id=user.id, from_role="production", submitted="just now", age=0, critical=critical,
                   bucket_state="QUEUED_CRITICAL" if critical else "QUEUED_MAIN", note=body.get("note"),
                   items_snapshot=snapshot))
    bom.state = "submitted"
    _audit(db, user, "BOM submitted to Purchasing", bom_id, before="RESULTS", after="SUBMITTED", etype="bom")
    db.commit()
    return {"bom": get_bom_full(db, bom_id), "request": SR.request(db.get(Request, rid), _users(db))}


def get_bom_full(db, bom_id):
    bom = db.get(Bom, bom_id)
    pb = db.query(Pushback).filter(Pushback.bom_id == bom_id, Pushback.state != "cancelled").first()
    return SR.bom(bom, sorted(bom.lines, key=lambda x: x.line_no), pb, _users(db))


# --------------------------------------------------------------------------- #
# Comments / notifications / admin
# --------------------------------------------------------------------------- #
@router.post("/comments")
def add_comment(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    cid = f"cmt-{int(NOW().timestamp()*1000)}"
    c = Comment(id=cid, entity_type=body.get("entityType", "generic"), entity_id=body["entityId"],
                thread_level="overall", user_id=user.id, name=user.name, role=(user.roles or [None])[0],
                body=body["body"], ts=NOW())
    db.add(c); db.commit()
    return {"id": cid, "entityId": body["entityId"],
            "comment": {"id": cid, "userId": user.id, "name": user.name, "role": c.role, "when": "just now", "body": c.body}}


@router.post("/notifications/{nid}/read")
def mark_read(nid: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n: n.unread = False; db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(require_user), db: Session = Depends(get_db)):
    roles = set(user.roles or [])
    for n in db.query(Notification).all():
        if roles & set(n.for_roles or []):
            n.unread = False
    db.commit()
    return {"ok": True}


@router.patch("/users/{uid}")
def update_user(uid: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if "admin" not in (user.roles or []):
        raise HTTPException(403, "Admin only")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if "roles" in body:
        valid = {"designer", "production", "admin", "development"}
        u.roles = [r for r in body["roles"] if r in valid]
        if u.roles and (not u.primary_role or u.primary_role not in u.roles):
            u.primary_role = u.roles[0]
    if "overrides" in body: u.overrides = body["overrides"]
    if "active" in body: u.active = bool(body["active"])
    _audit(db, user, "User updated", uid, etype="user")
    db.commit(); db.refresh(u)
    return SR.user_full(u)


@router.patch("/config")
def update_config(body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if "admin" not in (user.roles or []):
        raise HTTPException(403, "Admin only")
    key = body["key"]
    cfg = db.get(Configuration, key) or Configuration(key=key, section=body.get("section", "system"), value={})
    cfg.value = {**(cfg.value or {}), **(body.get("value") or {})}
    cfg.updated_by = user.name
    db.merge(cfg); _audit(db, user, "Config updated", key, etype="config"); db.commit()
    return {"key": key, "value": cfg.value}


@router.patch("/suppliers/{sid}")
def toggle_supplier(sid: str, body: dict = Body(...), user: User = Depends(require_user), db: Session = Depends(get_db)):
    if "admin" not in (user.roles or []):
        raise HTTPException(403, "Admin only")
    s = db.get(Supplier, sid)
    if not s:
        raise HTTPException(404, "Supplier not found")
    if "enabled" in body: s.enabled = bool(body["enabled"])
    db.commit()
    return SR.supplier(s)
