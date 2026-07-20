"""Live sourcing endpoints.

GET /api/sourcing/boms/{id}/run streams per-line results as Server-Sent Events
(EventSource is GET-only). The stream drives the SourcingProgressScreen; the
final `done` event carries the authoritative serialized BOM the store applies.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth.deps import require_user
from db.models import User
from db.session import SessionLocal
from services.sourcing_runner import iterate_sourcing

router = APIRouter(prefix="/sourcing", tags=["sourcing"])


@router.get("/boms/{bom_id}/run")
def run_sourcing(bom_id: str, user: User = Depends(require_user)):
    def event_stream():
        # Use a dedicated session for the life of the stream.
        db: Session = SessionLocal()
        try:
            for event in iterate_sourcing(db, bom_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # never break the stream with a raw 500 mid-render
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
