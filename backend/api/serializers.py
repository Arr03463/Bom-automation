"""ORM -> prototype (data.jsx) shapes.

The frontend store expects the exact field names data.jsx produced (camelCase,
name strings for actors, nested items/pushback). These serializers are the
inverse of db/seed.py so screens render unchanged against real data.
"""

from __future__ import annotations

import enum
from typing import Optional

from db.models import (
    Audit, Bom, BomLine, Collection, CollectionItem, Configuration,
    Notification, Program, Project, Pushback, Request, Supplier, User,
)


def ev(x):
    """Enum columns return Enum members; emit their string .value."""
    return x.value if isinstance(x, enum.Enum) else x


def _name(users_by_id: dict, uid: Optional[str]) -> str:
    u = users_by_id.get(uid)
    return u.name if u else (uid or "")


# --------------------------------------------------------------------------- #
# Line items -> the prototype `line()` shape
# --------------------------------------------------------------------------- #
def _num(v):
    return float(v) if v is not None else None


def bom_line(li: BomLine) -> dict:
    return {
        "no": li.line_no, "mpn": li.mpn, "mfr": li.mfr, "desc": li.description,
        "qty": li.qty, "status": li.status, "supplier": li.supplier,
        "supplierPn": li.supplier_pn, "unit": _num(li.unit_price), "ext": _num(li.ext_price),
        "note": li.note, "exReason": li.ex_reason, "source": li.source, "sourceBy": li.source_by,
        "replacement": li.replacement, "stale": False,
    }


def collection_item(ci: CollectionItem) -> dict:
    return {
        "no": ci.line_no, "mpn": ci.mpn, "mfr": ci.mfr, "desc": ci.description,
        "qty": ci.qty, "status": ci.status, "supplier": ci.supplier,
        "supplierPn": ci.supplier_pn, "unit": _num(ci.unit_price), "ext": _num(ci.ext_price),
        "note": ci.note, "stale": False,
    }


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
def user_full(u: User) -> dict:
    """Full record (Admin) — roles/overrides/active included."""
    return {
        "id": u.id, "name": u.name, "email": u.email, "roles": u.roles or [],
        "primaryRole": u.primary_role, "overrides": u.overrides or [], "active": u.active,
        "intern": u.intern, "title": u.title, "invitedBy": u.invited_by,
        "lastActive": u.last_active, "created": None, "roleSource": ev(u.role_source),
    }


def user_dir(u: User) -> dict:
    """Directory record (non-Admin) — no role/permission detail leaked."""
    return {"id": u.id, "name": u.name, "email": u.email, "title": u.title, "active": u.active}


def program(p: Program, users_by_id: dict, project_ids: list[str]) -> dict:
    return {
        "id": p.id, "name": p.name, "code": p.code, "identifier": p.identifier,
        "owner": _name(users_by_id, p.owner_id), "status": ev(p.status), "desc": p.description,
        "customer": p.customer, "started": p.started, "target": p.target, "tags": p.tags or [],
        "notifyOnEquivalentSwap": p.notify_on_equivalent_swap, "projects": project_ids,
    }


def project(pr: Project, users_by_id: dict) -> dict:
    return {
        "id": pr.id, "name": pr.name, "identifier": pr.identifier,
        "lead": _name(users_by_id, pr.lead_id), "program_id": pr.program_id,
        "desc": pr.description, "status": ev(pr.status), "created": None,
        "partsbox": None,
    }


def collection(c: Collection, items: list[CollectionItem]) -> dict:
    return {
        "id": c.id, "name": c.name, "project": c.project_id, "program": c.program_id,
        "state": ev(c.state), "ownerId": c.owner_id, "role": c.role, "category": c.category,
        "desc": c.description, "notes": c.notes, "reqId": c.req_id, "updatedBy": c.updated_by,
        "updated": None, "created": None,
        "creator": None,   # filled by caller via owner name
        "items": [collection_item(i) for i in sorted(items, key=lambda x: x.line_no)],
    }


def pushback(pb: Pushback, users_by_id: dict) -> dict:
    return {
        "by": _name(users_by_id, pb.from_user_id), "to": _name(users_by_id, pb.to_user_id),
        "reason": ev(pb.reason), "urgency": ev(pb.urgency), "state": ev(pb.state),
        "note": pb.note, "loop": pb.loop, "flaggedLines": pb.flagged_lines or [],
        "addedComponentRequest": pb.added_component_request, "recommendation": pb.recommendation,
        "resolvedAtVersionId": pb.resolved_at_version_id, "comments": [],
    }


def bom(b: Bom, lines: list[BomLine], pb: Optional[Pushback], users_by_id: dict) -> dict:
    return {
        "id": b.id, "name": b.name, "project": b.project_id, "state": ev(b.state),
        "version": b.version, "ownerId": b.owner_id, "creator": _name(users_by_id, b.owner_id),
        "role": b.role, "buildQty": b.build_qty, "overage": b.overage,
        "sourceCollection": b.source_collection_id, "partsbox": b.partsbox_ref,
        "validation": b.validation, "updated": None, "created": None,
        "pushback": pushback(pb, users_by_id) if pb else None,
        "items": [bom_line(li) for li in sorted(lines, key=lambda x: x.line_no)],
    }


def request(r: Request, users_by_id: dict) -> dict:
    items = r.items_snapshot or []
    # snapshot keys already match the line shape (no/mpn/mfr/desc/qty/...).
    return {
        "id": r.id, "title": r.title, "kind": ev(r.kind), "sourceId": r.source_id,
        "project": r.project_id, "from": _name(users_by_id, r.from_user_id), "fromRole": r.from_role,
        "submitted": r.submitted, "age": r.age, "critical": r.critical,
        "bucketState": ev(r.bucket_state), "note": r.note, "resubmit": r.resubmit, "items": items,
    }


def notification(n: Notification) -> dict:
    return {
        "id": n.id, "forRoles": n.for_roles or [], "group": n.group, "unread": n.unread,
        "kind": ev(n.kind), "sourceRole": n.source_role, "targetRole": n.target_role,
        "actionLabel": n.action_label, "verb": n.verb, "body": n.body, "who": n.who, "when": n.when,
        "entity": n.entity_id, "type": n.type_label, "actorRole": n.source_role,
        "routes": n.routes, "go": n.go,
    }


def audit(a: Audit, users_by_id: dict) -> dict:
    return {
        "id": a.id, "ts": a.ts, "user": _name(users_by_id, a.actor_id), "role": a.role,
        "action": a.action, "entity": a.entity_id, "before": a.before, "after": a.after,
    }


def supplier(s: Supplier) -> dict:
    return {
        "id": s.id, "name": s.name, "enabled": s.enabled, "priority": s.priority,
        "api": s.api_status, "mode": s.mode,
        "color": "#1A56DB" if s.id == "mouser" else "#D91F1F",
    }
