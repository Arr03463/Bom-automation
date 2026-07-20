"""BOM endpoints — real file upload (multipart -> bom_cleaner -> real BOM) + read.

The upload path takes the user's actual file bytes, runs the Phase 2 bom_cleaner
server-side (dedup, designator expansion, required-qty), and creates a real BOM
with real lines. No simulated/canned path.
"""

from __future__ import annotations

import math
import os
import re
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from api import serializers as SR
from auth.deps import require_user
from db.models import Bom, BomLine, Project, User
from db.session import get_db
from services import bom_cleaner

router = APIRouter(prefix="/boms", tags=["boms"])


def next_bom_id(db: Session) -> str:
    nums = [int(m.group(1)) for (bid,) in db.query(Bom.id).all()
            if (m := re.match(r"BOM-0*(\d+)$", bid))]
    return f"BOM-{(max(nums) + 1) if nums else 100:03d}"


def _cell(v):
    """Coerce pandas/NaN cells to clean Python values."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def _to_int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _warn_list(w):
    """bom_cleaner.warnings may be a list or a pandas object — normalize to
    a short list of strings (avoids DataFrame truthiness ambiguity)."""
    if w is None:
        return []
    def _clean(items):
        out = []
        for x in items:
            s = str(x).strip()
            if not s or s.lower().endswith((".csv", ".xlsx")) or s.startswith("tmp"):
                continue  # drop empties and the temp source-filename cell
            out.append(s)
        return out[:20]
    if hasattr(w, "empty"):        # DataFrame / Series
        try:
            if w.empty:
                return []
            return _clean(w.astype(str).values.flatten().tolist())
        except Exception:
            return []
    if isinstance(w, (list, tuple)):
        return _clean(w)
    return _clean([w])


@router.get("/{bom_id}")
def get_bom(bom_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    bom = db.get(Bom, bom_id)
    if bom is None:
        raise HTTPException(404, "BOM not found")
    from db.models import Pushback
    users_by_id = {u.id: u for u in db.query(User).all()}
    pb = db.query(Pushback).filter(Pushback.bom_id == bom_id, Pushback.state != "cancelled").first()
    return SR.bom(bom, sorted(bom.lines, key=lambda x: x.line_no), pb, users_by_id)


@router.post("/upload")
async def upload_bom(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    name: str = Form(...),
    build_qty: int = Form(...),
    overage: int = Form(10),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(400, "Unknown project")
    # One master BOM per project (Model B re-upload ceremony is Phase 4).
    if db.query(Bom).filter(Bom.project_id == project_id).first():
        raise HTTPException(400, "This project already has a master BOM.")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file.")
    ext = os.path.splitext(file.filename or "")[1].lower() or ".csv"
    if ext not in (".csv", ".xlsx"):
        raise HTTPException(400, "Unsupported file type. Upload a CSV or XLSX.")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        try:
            result = bom_cleaner.process_bom_file(tmp.name)
        except Exception as exc:
            raise HTTPException(400, f"Could not parse the BOM file: {exc}")
        clean = bom_cleaner.apply_project_quantities(result.clean_bom, build_quantity=build_qty)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    if clean is None or len(clean) == 0:
        raise HTTPException(400, "No usable BOM lines found in the file.")

    bom_id = next_bom_id(db)
    bom = Bom(id=bom_id, name=name, project_id=project_id, state="validated", version=1,
              owner_id=user.id, role="production", build_qty=build_qty, overage=overage,
              validation={"errors": 0, "warnings": len(_warn_list(result.warnings)),
                          "notes": _warn_list(result.warnings),
                          "columnMapping": {str(k): str(v) for k, v in dict(result.mapped_columns or {}).items()}})
    db.add(bom)
    db.flush()

    line_no = 0
    for _, row in clean.iterrows():
        mpn = _cell(row.get("mpn"))
        if not mpn:
            continue
        line_no += 1
        qty = _to_int(row.get("required_qty")) or _to_int(row.get("qty_per_board"))
        db.add(BomLine(
            bom_id=bom_id, line_no=line_no, mpn=mpn, mfr=_cell(row.get("manufacturer")),
            description=_cell(row.get("description")), qty=qty, status="normalised",
            note=_cell(row.get("designators")),
        ))
    db.commit()
    db.refresh(bom)

    users_by_id = {u.id: u for u in db.query(User).all()}
    payload = SR.bom(bom, sorted(bom.lines, key=lambda x: x.line_no), None, users_by_id)
    payload["_upload"] = {"filename": file.filename, "rows": line_no,
                          "columnMapping": {str(k): str(v) for k, v in dict(result.mapped_columns or {}).items()},
                          "warnings": _warn_list(result.warnings)}
    return payload
