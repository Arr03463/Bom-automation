"""AutoBOM seed data — ported from the prototype's data.jsx, IDs preserved.

Role model (Phase 1 correction):
- Exactly THREE dev/demo login users, one clean single valid role each:
    u-aaron -> designer, u-maria -> production, u-grace -> admin.
- EVERY other prototype user is inert referential data: roles == [] so they are
  NOT login accounts, but their records exist so FKs resolve (BOM owners,
  pushback from/to, audit actors) and the demo looks alive.
- No legacy role strings (manager/readonly/executive) anywhere. Development
  users are inert too (role deferred behind DEV_ROLE_ENABLED).
- All ownership/actor references from the prototype are preserved unchanged.

Idempotent: parents upsert by PK (merge); line children are replaced per parent.
Run: `python -m db.seed`  (or import seed_all).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.models import (
    Audit, Bom, BomLine, Collection, CollectionItem, Configuration,
    Notification, Program, Project, Pushback, Request, Supplier, User,
)
from db.session import SessionLocal

NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)

# --------------------------------------------------------------------------- #
# Component catalog (for resolving line mfr/desc/price, mirrors data.jsx CATALOG)
# --------------------------------------------------------------------------- #
CATALOG = {
    "IRFB4110PBF": {"mfr": "Infineon", "desc": "MOSFET N-Ch 100V 180A TO-220AB",
                    "mouser": {"pn": "942-IRFB4110PBF", "price": 1.92}, "digikey": {"pn": "IRFB4110PBF-ND", "price": 1.87}},
    "TPS54560DDAR": {"mfr": "Texas Instruments", "desc": "Buck Converter 60V 5A SO-8 PowerPAD",
                     "mouser": {"pn": "595-TPS54560DDAR", "price": 2.41}, "digikey": {"pn": "296-38814-1-ND", "price": 2.58}},
    "UCC27201ADR": {"mfr": "Texas Instruments", "desc": "Half-Bridge Gate Driver 120V 3A SOIC-8",
                    "mouser": {"pn": "595-UCC27201ADR", "price": 1.74}, "digikey": {"pn": "296-28649-1-ND", "price": 1.69}},
    "LM2596S-5.0": {"mfr": "onsemi", "desc": "Buck Regulator 5V 3A TO-263",
                    "mouser": {"pn": "863-LM2596S-5.0", "price": 0}, "digikey": {"pn": "LM2596S-5.0-ND", "price": 0}},
    "C3216X7R1H105K160AB": {"mfr": "TDK", "desc": "Cap Ceramic 1uF 50V X7R 1206",
                            "mouser": {"pn": "810-C3216X7R1H105K", "price": 0.18}, "digikey": {"pn": "445-1421-1-ND", "price": 0.19}},
    "GRM188R71H104KA93D": {"mfr": "Murata", "desc": "Cap Ceramic 0.1uF 50V X7R 0603",
                           "mouser": {"pn": "81-GRM188R71H104KA93", "price": 0.012}, "digikey": {"pn": "490-1532-1-ND", "price": 0.011}},
    "STM32G431CBT6": {"mfr": "STMicroelectronics", "desc": "MCU Arm Cortex-M4 170MHz LQFP-48",
                      "mouser": {"pn": "511-STM32G431CBT6", "price": 4.12}, "digikey": {"pn": "497-STM32G431CBT6-ND", "price": 4.05}},
    "0039281043": {"mfr": "Molex", "desc": "Mini-Fit Jr. Header 4-pos 4.2mm R/A",
                   "mouser": {"pn": "538-39-28-1043", "price": 0.41}, "digikey": {"pn": "WM3702-ND", "price": 0.39}},
    "BAT54S-7-F": {"mfr": "Diodes Inc", "desc": "Schottky Diode Array 30V SOT-23",
                   "mouser": {"pn": "621-BAT54S-7-F", "price": 0.06}, "digikey": {"pn": "BAT54S-FDICT-ND", "price": 0.05}},
    "ERJ-3EKF1002V": {"mfr": "Panasonic", "desc": "Res 10k 1% 1/10W 0603",
                      "mouser": {"pn": "667-ERJ-3EKF1002V", "price": 0.004}, "digikey": {"pn": "P10.0KHCT-ND", "price": 0.003}},
}


def line(no, mpn, qty, status, note=None, source=None, source_by=None, ex_reason=None):
    """Resolve a line the way data.jsx line() does."""
    c = CATALOG.get(mpn, {})
    sup = "digikey" if status == "sourced-digikey" else "mouser" if status == "sourced-mouser" else None
    off = c.get(sup) if sup else None
    unit = off["price"] if off else None
    return dict(no=no, mpn=mpn, mfr=c.get("mfr", "-"), desc=c.get("desc", "-"), qty=qty, status=status,
                supplier=sup, supplier_pn=(off["pn"] if off else None), unit=unit,
                ext=(round(unit * qty, 2) if unit is not None else None),
                note=note, source=source, source_by=source_by, ex_reason=ex_reason)


# --------------------------------------------------------------------------- #
# Users — 3 login (single role) + inert referential (roles == [])
# --------------------------------------------------------------------------- #
# (id, name, email, roles, primary_role, overrides, active, intern, title, invited_by, last_active)
LOGIN_USERS = [
    ("u-aaron", "Aaron Jones", "aaron.jones@yanktech.com", ["designer"], "designer", [], True, False, "Senior Hardware Engineer", None, "2 min ago"),
    ("u-maria", "Maria Chen", "maria.chen@yanktech.com", ["production"], "production", [], True, False, "Production Engineer", "u-grace", "18 min ago"),
    ("u-grace", "Grace Hill", "grace.hill@yanktech.com", ["admin"], "admin", [], True, False, "IT / Systems Admin", None, "40 min ago"),
]
# Inert users: records exist for FK/actor resolution; NO valid roles; not login accounts.
INERT_USERS = [
    ("u-david", "David Okafor", "david.okafor@yanktech.com", "Procurement Lead", "u-grace", "1 h ago", True, False),
    ("u-sara", "Sara Lindqvist", "sara.l@yanktech.com", "Hardware Engineer", "u-grace", "Yesterday", True, False),
    ("u-tom", "Tom Becker", "tom.becker@yanktech.com", "Engineering Intern", "u-aaron", "3 h ago", True, True),
    ("u-priya", "Priya Nair", "priya.nair@yanktech.com", "Engineering Manager", None, "5 h ago", True, False),
    ("u-leo", "Leo Vargas", "leo.vargas@yanktech.com", "Operations Analyst", "u-grace", "2 days ago", True, False),
    ("u-quinn", "Quinn Alvarez", "quinn.a@yanktech.com", "Contractor (offboarded)", "u-grace", "3 weeks ago", False, False),
    ("u-noah", "Noah Park", "noah.park@yanktech.com", "Reliability Engineer", "u-grace", "7 min ago", True, False),
    ("u-ava", "Ava Patel", "ava.patel@yanktech.com", "Firmware Engineer", "u-grace", "22 min ago", True, False),
]


def _seed_users(db: Session) -> None:
    for (uid, name, email, roles, primary, overrides, active, intern, title, invited, last) in LOGIN_USERS:
        db.merge(User(id=uid, name=name, email=email, roles=roles, primary_role=primary,
                      overrides=overrides, active=active, intern=intern, title=title,
                      invited_by=invited, last_active=last, role_source="seed"))
    for (uid, name, email, title, invited, last, active, intern) in INERT_USERS:
        db.merge(User(id=uid, name=name, email=email, roles=[], primary_role=None, overrides=[],
                      active=active, intern=intern, title=title, invited_by=invited,
                      last_active=last, role_source="seed"))


# --------------------------------------------------------------------------- #
# Programs / Projects
# --------------------------------------------------------------------------- #
PROGRAMS = [
    ("terra-voyager", "Terra Voyager", "TV", "TV", "u-aaron", "Active", "Long-running traction-control platform contract. Multiple board revisions.", "Customer X", "Jan 2025", "Q4 2026", ["contract", "traction"], True),
    ("gatekeeper", "Gatekeeper R&D", "GK", "GK", "u-aaron", "Active", "Internal R&D initiative exploring next-gen gate-driver topologies.", None, "May 2025", None, ["r&d", "internal"], True),
    ("restock", "Build Wall Ops", "BW", "BW", "u-maria", "Active", "Recurring replenishment of build-wall working stock.", None, "Apr 2025", None, ["ops"], True),
    ("motor-control", "Motor Control", "MC", "MC", "u-aaron", "Active", "Brushless DC motor controller platform and derivatives.", None, "Jun 2025", None, ["production", "motor"], True),
]
PROJECTS = [
    ("tvca-rev2", "TVCA Rev 2", "R2", "u-aaron", "terra-voyager", "Traction voltage control assembly, second revision."),
    ("gate-eval", "Gate Driver Eval", "EVAL", "u-aaron", "gatekeeper", "Evaluation of half-bridge gate driver candidates."),
    ("wall-q2", "Wall Replenishment", "Q2", "u-maria", "restock", "Quarterly restock of build-wall passives & connectors."),
    ("bldc", "BLDC Motor Controller", "MC1", "u-aaron", "motor-control", "Brushless DC motor controller platform."),
    ("tvca-psu", "TVCA Power Supply v2", "PSU", "u-maria", "terra-voyager", "Auxiliary power supply board for TVCA Rev 2."),
    ("md-stage", "Motor Driver Stage", "MD", "u-maria", "motor-control", "Half-bridge motor driver power stage board."),
    ("sensor-a-draft", "Sensor Board Rev A (draft)", "SBA", "u-maria", "motor-control", "Sensor front-end board - draft revision under bring-up."),
]


def _seed_programs_projects(db: Session) -> None:
    for (pid, name, code, ident, owner, status, desc, cust, started, target, tags, notify) in PROGRAMS:
        db.merge(Program(id=pid, name=name, code=code, identifier=ident, owner_id=owner, status=status,
                         description=desc, customer=cust, started=started, target=target, tags=tags,
                         notify_on_equivalent_swap=notify))
    for (pid, name, ident, lead, program_id, desc) in PROJECTS:
        db.merge(Project(id=pid, name=name, identifier=ident, lead_id=lead, program_id=program_id,
                         description=desc, status="active"))


# --------------------------------------------------------------------------- #
# Collections (Designer only — dev collections deferred)
# --------------------------------------------------------------------------- #
COLLECTIONS = [
    dict(id="COL-031", name="TVCA Connector Research", project_id="tvca-rev2", program_id="terra-voyager", state="active",
         owner_id="u-aaron", role="designer", desc="Evaluating power + signal interconnect options for the TVCA Rev 2 main board.",
         updated_by="Aaron Jones", req_id=None,
         items=[line(1, "0039281043", 12, "sourced-mouser"), line(2, "IRFB4110PBF", 8, "sourced-digikey"),
                line(3, "TPS54560DDAR", 4, "sourced-mouser"),
                line(4, "C3216X7R1H105K160AB", 40, "needs-review", note="Supplier data >24h old - re-check before ordering."),
                line(5, "UCC27201ADR", 6, "check-wall")]),
    dict(id="COL-028", name="Buck Converter Investigation", project_id="tvca-rev2", program_id="terra-voyager", state="order-requested",
         owner_id="u-aaron", role="designer", desc="R&D buy for buck-converter bring-up boards.", updated_by="Aaron Jones", req_id="REQ-018",
         items=[line(1, "TPS54560DDAR", 10, "sourced-mouser"), line(2, "GRM188R71H104KA93D", 200, "sourced-digikey"),
                line(3, "STM32G431CBT6", 5, "sourced-mouser")]),
    dict(id="COL-024", name="Gate Driver Options", project_id="gate-eval", program_id="gatekeeper", state="active",
         owner_id="u-aaron", role="designer", desc="Comparing half-bridge gate driver candidates for the TVCA power stage.", updated_by="Aaron Jones", req_id=None,
         items=[line(1, "UCC27201ADR", 6, "needs-review", note="Zero stock at recommended supplier (Mouser) - must be resolved before Request to Order."),
                line(2, "IRFB4110PBF", 12, "sourced-digikey")]),
    dict(id="COL-019", name="Wall Replenishment Q2", project_id="wall-q2", program_id="restock", state="ordered",
         owner_id="u-aaron", role="designer", desc="Restock of common passives and connectors for the build wall.", updated_by="David Okafor", req_id="REQ-009",
         items=[line(1, "GRM188R71H104KA93D", 5000, "sourced-digikey"), line(2, "C3216X7R1H105K160AB", 2000, "sourced-mouser"),
                line(3, "0039281043", 300, "sourced-mouser")]),
    dict(id="COL-033", name="Sensor Front-End", project_id="bldc", program_id="motor-control", state="active",
         owner_id="u-aaron", role="designer", desc="New research space - no parts added yet.", updated_by="Aaron Jones", req_id=None, items=[]),
]


def _seed_collections(db: Session) -> None:
    for c in COLLECTIONS:
        db.merge(Collection(id=c["id"], name=c["name"], project_id=c["project_id"], program_id=c["program_id"],
                            state=c["state"], owner_id=c["owner_id"], role=c["role"], description=c["desc"],
                            req_id=c["req_id"], updated_by=c["updated_by"]))
        db.execute(delete(CollectionItem).where(CollectionItem.collection_id == c["id"]))
        for it in c["items"]:
            db.add(CollectionItem(collection_id=c["id"], line_no=it["no"], mpn=it["mpn"], mfr=it["mfr"],
                                  description=it["desc"], qty=it["qty"], status=it["status"], supplier=it["supplier"],
                                  supplier_pn=it["supplier_pn"], unit_price=it["unit"], ext_price=it["ext"], note=it["note"]))


# --------------------------------------------------------------------------- #
# BOMs (+ lines) and the BOM-052 Push-Back
# --------------------------------------------------------------------------- #
BOMS = [
    dict(id="BOM-055", name="Sensor Board Rev A", project_id="bldc", state="validated", owner_id="u-maria", role="production",
         build_qty=25, overage=5, source_collection_id="COL-033",
         validation={"errors": 0, "warnings": 2, "notes": ["Line 4: quantity inferred from reference designators (4 -> 4).", "Lines 6-7: duplicate MPN consolidated."]},
         items=[line(1, "STM32G431CBT6", 25, "validated"), line(2, "GRM188R71H104KA93D", 500, "validated"),
                line(3, "ERJ-3EKF1002V", 800, "validated"), line(4, "BAT54S-7-F", 50, "validated"), line(5, "TPS54560DDAR", 25, "validated")]),
    dict(id="BOM-052", name="TVCA Main BOM v3", project_id="tvca-rev2", state="exceptions", owner_id="u-aaron", role="production",
         build_qty=50, overage=10, source_collection_id="COL-031", validation=None,
         items=[line(1, "0039281043", 50, "sourced-mouser", source="COL-031", source_by="Aaron Jones"),
                line(2, "IRFB4110PBF", 200, "needs-review", source="COL-031", source_by="Aaron Jones", ex_reason="Possible EOL - confirm lifecycle or replace."),
                line(3, "UCC27201ADR", 100, "needs-review", source="COL-031", source_by="Aaron Jones", ex_reason="Zero stock at recommended supplier."),
                line(4, "C3216X7R1H105K160AB", 400, "needs-review", source="COL-031", source_by="Aaron Jones", ex_reason="Stale pricing - re-check."),
                line(5, "GRM188R71H104KA93D", 2000, "sourced-digikey"), line(6, "ERJ-3EKF1002V", 3000, "sourced-mouser"),
                line(7, "TPS54560DDAR", 50, "sourced-mouser")]),
    dict(id="BOM-051", name="Motor Driver Stage", project_id="md-stage", state="results", owner_id="u-maria", role="production",
         build_qty=30, overage=10, source_collection_id=None, validation=None,
         items=[line(1, "IRFB4110PBF", 120, "sourced-mouser"), line(2, "UCC27201ADR", 60, "sourced-digikey"),
                line(3, "STM32G431CBT6", 30, "sourced-mouser"), line(4, "GRM188R71H104KA93D", 600, "sourced-digikey"),
                line(5, "ERJ-3EKF1002V", 900, "sourced-mouser")]),
    dict(id="BOM-048", name="Power Supply v2", project_id="tvca-psu", state="submitted", owner_id="u-maria", role="production",
         build_qty=40, overage=5, source_collection_id=None, validation=None,
         items=[line(1, "TPS54560DDAR", 40, "sourced-mouser"), line(2, "C3216X7R1H105K160AB", 320, "sourced-mouser"),
                line(3, "GRM188R71H104KA93D", 800, "sourced-digikey"), line(4, "BAT54S-7-F", 80, "sourced-digikey")]),
    dict(id="BOM-060", name="Sensor Board Rev A - draft", project_id="sensor-a-draft", state="draft", owner_id="u-maria", role="production",
         build_qty=None, overage=None, source_collection_id=None, validation=None, items=[]),
]


def _seed_boms(db: Session) -> None:
    for b in BOMS:
        db.merge(Bom(id=b["id"], name=b["name"], project_id=b["project_id"], state=b["state"], version=1,
                     owner_id=b["owner_id"], role=b["role"], build_qty=b["build_qty"], overage=b["overage"],
                     source_collection_id=b["source_collection_id"], validation=b["validation"]))
        db.execute(delete(BomLine).where(BomLine.bom_id == b["id"]))
        for it in b["items"]:
            db.add(BomLine(bom_id=b["id"], line_no=it["no"], mpn=it["mpn"], mfr=it["mfr"], description=it["desc"],
                           qty=it["qty"], status=it["status"], supplier=it["supplier"], supplier_pn=it["supplier_pn"],
                           unit_price=it["unit"], ext_price=it["ext"], note=it["note"], ex_reason=it["ex_reason"],
                           source=it["source"], source_by=it["source_by"]))

    # BOM-052 Push-Back (Maria -> Aaron), extracted from the prototype's inline pushback object.
    db.merge(Pushback(
        id="PB-052", bom_id="BOM-052", reason="eol", urgency="blocking",
        from_user_id="u-maria", to_user_id="u-aaron", state="open",
        note=("IRFB4110PBF may be discontinued - please confirm or supply a replacement. "
              "UCC27201ADR is zero-stock at the recommended supplier."),
        loop=1,
        flagged_lines=[
            {"lineNo": 2, "exReason": "Possible EOL - confirm lifecycle or replace.", "comments": []},
            {"lineNo": 3, "exReason": "Zero stock at recommended supplier.", "comments": []},
            {"lineNo": 4, "exReason": "Stale pricing - re-check.", "comments": []},
        ],
        added_component_request=None, recommendation=None, resolved_at_version_id=None,
    ))


# --------------------------------------------------------------------------- #
# Requests (bucket entries) — items snapshotted from source collection/bom
# --------------------------------------------------------------------------- #
def _items_snapshot(entity: dict) -> list:
    return [dict(no=i["no"], mpn=i["mpn"], mfr=i["mfr"], desc=i["desc"], qty=i["qty"], status=i["status"],
                 supplier=i["supplier"], supplier_pn=i["supplier_pn"], unit=i["unit"], ext=i["ext"])
            for i in entity["items"]]


def _seed_requests(db: Session) -> None:
    by_id = {c["id"]: c for c in COLLECTIONS} | {b["id"]: b for b in BOMS}
    reqs = [
        ("REQ-018", "Buck Converter Investigation", "collection", "COL-028", "tvca-rev2", "u-aaron", "designer",
         "Yesterday", 28, True, "QUEUED_CRITICAL", "R&D bring-up - blocking bench work. Budget code TVCA-RND-02."),
        ("REQ-016", "Power Supply v2", "bom", "BOM-048", "tvca-psu", "u-maria", "production",
         "5h ago", 5, False, "QUEUED_MAIN", "Validated and fully sourced. PartsBox PB-PSU-V2 created. Production build qty 40 + 5% overage."),
        ("REQ-012", "Motor Driver Stage", "bom", "BOM-051", "md-stage", "u-maria", "production",
         "Jun 16", 2, False, "WRITTEN", "All lines sourced. Written to the Daily Purchasing List."),
        ("REQ-009", "Wall Replenishment Q2", "collection", "COL-019", "wall-q2", "u-aaron", "designer",
         "May 30", 0, False, "PURCHASED", "Standard quarterly restock."),
    ]
    for (rid, title, kind, src, proj, frm, frole, sub, age, crit, bstate, note) in reqs:
        db.merge(Request(id=rid, title=title, kind=kind, source_id=src, source_type=kind, project_id=proj,
                         from_user_id=frm, from_role=frole, submitted=sub, age=age, critical=crit,
                         bucket_state=bstate, note=note, resubmit=False,
                         items_snapshot=_items_snapshot(by_id[src]) if src in by_id else []))


# --------------------------------------------------------------------------- #
# Notifications (dev-routed filtered out) + Audit (non-development) + Suppliers + Config
# --------------------------------------------------------------------------- #
def _seed_notifications(db: Session) -> None:
    db.merge(Notification(id="n1", for_roles=["designer"], group="Today", unread=True, kind="action",
                          source_role="production", target_role="designer", action_label="Replace 3 parts", verb="Resolve",
                          body="TVCA Main BOM v3 - 3 lines flagged for engineering review.", who="Maria Chen", when="38m ago",
                          entity_id="BOM-052", entity_type="bom", type_label="BOM EXCEPTION",
                          routes={"designer": {"screen": "d.dashboard"}, "production": {"screen": "p.bomOverview", "id": "BOM-052"}},
                          go={"screen": "d.dashboard"}))
    db.merge(Notification(id="n3", for_roles=["production"], group="Today", unread=True, kind="fyi",
                          source_role="production", target_role="production", action_label="Awaiting designer response", verb="Track",
                          body="TVCA Main BOM v3 is waiting on replacements from Aaron Jones.", who="System", when="38m ago",
                          entity_id="BOM-052", entity_type="bom", type_label="REPLACEMENTS NEEDED",
                          routes={"production": {"screen": "p.bomOverview", "id": "BOM-052"}, "designer": {"screen": "d.dashboard"}},
                          go={"screen": "p.bomOverview", "id": "BOM-052"}))


def _seed_audit(db: Session) -> None:
    # Non-development audit history (matches data.jsx devClean: role != 'development').
    rows = [
        ("au1", "Today 14:22", "u-maria", "production", "BOM exception sent", "BOM-052", "bom", "SOURCING", "EXCEPTIONS"),
        ("au2", "Today 13:40", "u-david", "production", "Request submitted to bucket", "REQ-012", "request", "-", "QUEUED_MAIN"),
        ("au4", "Yesterday 16:55", "u-aaron", "designer", "Collection submitted to Purchasing", "COL-028", "collection", "ACTIVE", "ORDER REQUESTED"),
        ("au6", "Jun 13 11:02", "u-grace", "admin", "Role assigned (production)", "u-aaron", "user", "[designer]", "[designer, production]"),
    ]
    for (aid, ts, actor, role, action, ent, etype, before, after) in rows:
        db.merge(Audit(id=aid, ts=ts, actor_id=actor, role=role, action=action, entity_id=ent,
                       entity_type=etype, before=before, after=after))


def _seed_suppliers(db: Session) -> None:
    db.merge(Supplier(id="mouser", name="Mouser Electronics", enabled=True, priority=1, api_status="connected", mode="API + CSV fallback"))
    db.merge(Supplier(id="digikey", name="DigiKey", enabled=True, priority=2, api_status="connected", mode="API + CSV fallback"))


def _seed_configuration(db: Session) -> None:
    cfg = {
        "workflow": ("workflow", {"maxExceptionLoops": 3, "staleThresholdHours": 24, "overdueHours": 24,
                                  "autoOrder": False, "requireBudgetCode": True, "mouserFirst": True}),
        "settings": ("system", {"sessionTimeoutMin": 30, "requireSupervisorForInterns": True, "mfa": False}),
        "batch": ("batch", {"main": {"intervalMin": 360}, "critical": {"intervalMin": 180}}),
        "suppliers": ("suppliers", {"distributorPriority": "mouser", "freshnessThreshold": "24h",
                                    "alternatePartPolicy": "auto-suggest"}),
        "cpn": ("system", {"format": "{program.identifier}-{project.identifier}-{line}", "formatVersion": 1}),
        "cache": ("system", {"partsboxTtlSeconds": 60, "supplierCatalogTtlSeconds": 300, "datasheetTtlHours": 24}),
        "escalation": ("workflow", {"pushbackEscalationHours": 24}),
    }
    for key, (section, value) in cfg.items():
        db.merge(Configuration(key=key, section=section, value=value, updated_by="seed"))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def seed_all(db: Session) -> None:
    # Flush after each group so parent rows exist before FK-dependent children
    # are inserted (FKs are checked at statement time, not deferred).
    _seed_users(db); db.flush()
    _seed_programs_projects(db); db.flush()
    _seed_collections(db); db.flush()
    _seed_boms(db); db.flush()
    _seed_requests(db); db.flush()
    _seed_notifications(db)
    _seed_audit(db)
    _seed_suppliers(db)
    _seed_configuration(db)
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed_all(db)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
