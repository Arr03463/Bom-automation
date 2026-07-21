"""Build creation — master BOM + per-line overlay -> PartsBox consumption.

A Build is a physical assembly of the PCB. A Project has many Builds over time,
each referencing the ONE master BOM with a per-line overlay (CLAUDE.md):

  used     - populated normally  -> PartsBox consumes the master's component
  skipped  - omitted this build  -> NO consumption
  deferred - not populated now, intent to add later via rework -> NO consumption
             now; the future rework fires its own consumption
  rework   - populated with a DIFFERENT component -> PartsBox consumes the
             actual substitute, NOT the master's stated component

Rework state is per-Build, not master-BOM: it records what actually happened on
THIS assembly. The master BOM is never mutated here.

Two hard rules enforced below:
- Run Build is BLOCKED while any push-back on the master BOM is unresolved.
  Admin force-waive overrides, with a required reason (Bounded Admin Authority).
- Only 'used' and 'rework' lines consume stock. Getting this wrong silently
  decrements real inventory in PartsBox, which is not cheaply reversible.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from sqlalchemy.orm import Session

from db.models import Bom, BomLine, Pushback

log = logging.getLogger("autobom.build")

CONSUMING_STATES = ("used", "rework")
NON_CONSUMING_STATES = ("skipped", "deferred")
VALID_STATES = CONSUMING_STATES + NON_CONSUMING_STATES

MIN_WAIVE_REASON = 10   # Bounded Admin: destructive/override actions need a real reason


class BuildGateError(RuntimeError):
    """Run Build is blocked (unresolved push-back) and was not force-waived."""


def build_gate(db: Session, bom_id: str, *, force_waive_reason: Optional[str] = None) -> dict:
    """Is this BOM allowed to build?

    CLAUDE.md: while ANY push-back is unresolved on the master BOM, Run Build is
    blocked; Admin force-waive overrides with a reason logged to the
    Force-Waivers log.
    """
    open_pbs = db.query(Pushback).filter(Pushback.bom_id == bom_id,
                                         Pushback.state == "open").all()
    if not open_pbs:
        return {"allowed": True, "waived": False, "blockedBy": []}

    ids = [p.id for p in open_pbs]
    if force_waive_reason is None:
        raise BuildGateError(
            f"Run Build is blocked: {len(ids)} unresolved push-back(s) on this master BOM "
            f"({', '.join(ids)}). An Admin may force-waive with a reason."
        )
    reason = (force_waive_reason or "").strip()
    if len(reason) < MIN_WAIVE_REASON:
        raise BuildGateError(
            f"Force-waive requires an audit reason of at least {MIN_WAIVE_REASON} characters."
        )
    return {"allowed": True, "waived": True, "blockedBy": ids, "reason": reason}


def _line_qty_for_build(line_qty: int, bom_build_qty: int, build_qty: int) -> tuple[int, bool]:
    """Scale a master-BOM line quantity to THIS build's quantity.

    BomLine.qty is stored as the total for the BOM's own build_qty (qty_per_board
    x bom.build_qty), and there is no qty_per_board column. When a Build runs at
    the BOM's quantity - the common case - use the stored qty verbatim and do no
    arithmetic at all. Only scale when they differ, and report when the per-board
    quantity was not integral so the caller can surface it rather than silently
    rounding a real stock decrement.
    """
    line_qty = int(line_qty or 0)
    bom_build_qty = int(bom_build_qty or 1) or 1
    build_qty = int(build_qty or 1) or 1
    if build_qty == bom_build_qty:
        return line_qty, False
    per_board = line_qty / bom_build_qty
    scaled = math.ceil(per_board * build_qty)
    return scaled, (per_board != int(per_board))


def consumption_plan(bom: Bom, lines: list[BomLine], overlay: dict, build_qty: int) -> dict:
    """Turn the master BOM + overlay into an explicit consumption plan.

    Pure function: no DB writes, no API calls. The plan is what a dry run shows
    and what the live call executes, so both paths are provably identical.
    """
    overlay = overlay or {}
    consume, skipped, deferred, rework, warnings = [], [], [], [], []

    for line in sorted(lines, key=lambda x: x.line_no or 0):
        ov = overlay.get(str(line.line_no)) or overlay.get(line.line_no) or {}
        state = str(ov.get("state") or "used").strip().lower()
        if state not in VALID_STATES:
            raise ValueError(
                f"Line {line.line_no}: invalid overlay state {state!r}; "
                f"expected one of {sorted(VALID_STATES)}"
            )

        if state in NON_CONSUMING_STATES:
            entry = {"lineNo": line.line_no, "mpn": line.mpn, "mfr": line.mfr,
                     "state": state, "note": ov.get("note")}
            (skipped if state == "skipped" else deferred).append(entry)
            continue

        if state == "rework":
            mpn = (ov.get("mpn") or "").strip()
            if not mpn:
                raise ValueError(f"Line {line.line_no}: rework requires the substitute MPN.")
            mfr = (ov.get("mfr") or "").strip() or None
            rtype = (ov.get("reworkType") or "realtime").strip().lower()
            if rtype not in ("realtime", "post_hoc"):
                raise ValueError(f"Line {line.line_no}: reworkType must be realtime or post_hoc.")
            qty = ov.get("qty")
        else:
            mpn, mfr, rtype, qty = line.mpn, line.mfr, None, ov.get("qty")

        if qty is None:
            qty, fractional = _line_qty_for_build(line.qty, bom.build_qty, build_qty)
            if fractional:
                warnings.append(
                    f"Line {line.line_no}: {line.qty} for a build of {bom.build_qty} is not a "
                    f"whole per-board quantity; rounded up to {qty} for a build of {build_qty}."
                )
        qty = int(qty or 0)
        if qty <= 0:
            warnings.append(f"Line {line.line_no}: quantity resolves to {qty}; not consumed.")
            continue

        entry = {"lineNo": line.line_no, "mpn": mpn, "mfr": mfr, "qty": qty, "state": state}
        if state == "rework":
            entry.update({"reworkType": rtype, "replaces": {"mpn": line.mpn, "mfr": line.mfr},
                          "note": ov.get("note"), "ticketId": ov.get("ticketId")})
            rework.append(entry)
        consume.append(entry)

    return {
        "consume": consume,                  # what PartsBox will decrement
        "skipped": skipped, "deferred": deferred, "rework": rework,
        "warnings": warnings,
        "summary": {"lines": len(lines), "consumed": len(consume), "skipped": len(skipped),
                    "deferred": len(deferred), "rework": len(rework),
                    "units": sum(e["qty"] for e in consume)},
    }
