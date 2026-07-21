"""Supplier endpoints (thin, Phase 2 verification surface).

Supplier-primary MPN/keyword search + B2-guarded validation + a connectivity
status snapshot. The full two-mode parametric search (PartsBox overlay,
ParametricFilters) ships with the search UI in a later phase.

These hit live Mouser/DigiKey when SUPPLIER_DRY_RUN=false; in dry-run they return
offline mocks. No purchasing/order surface exists here — search + validate only.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from config import settings
from services.digikey_client import DigiKeyClient
from services.mouser_client import MouserClient
from services.sourcing_engine import validate_mpn
from services.supplier_base import scrub_secrets

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SearchRequest(BaseModel):
    query: str
    manufacturer: Optional[str] = ""
    required_qty: Optional[int] = None


class ValidateRequest(BaseModel):
    mpn: str
    manufacturer: Optional[str] = ""


def _result(res):
    return asdict(res) if res else None


@router.post("/search")
def search(req: SearchRequest) -> dict:
    """Best-match at each supplier (supplier-primary). Never places an order."""
    mouser = MouserClient()
    digikey = DigiKeyClient()
    out = {"query": req.query, "mouser": None, "digikey": None, "errors": {}}
    try:
        out["mouser"] = _result(mouser.find_best_match(req.query, req.manufacturer or "", req.required_qty))
    except Exception as exc:  # surface supplier errors without failing the whole call
        # scrub_secrets, never str(exc): a network-level failure stringifies with
        # the full request URL, and Mouser's apiKey lives in that query string.
        out["errors"]["mouser"] = scrub_secrets(exc)
    try:
        out["digikey"] = _result(digikey.find_best_match(req.query, req.manufacturer or "", req.required_qty))
    except Exception as exc:
        out["errors"]["digikey"] = scrub_secrets(exc)
    return out


@router.post("/validate-mpn")
def validate(req: ValidateRequest) -> dict:
    """B2-guarded: does this MPN exist at any supplier?"""
    return validate_mpn(req.mpn, req.manufacturer or "")


@router.get("/status")
def status() -> dict:
    """Non-secret connectivity/config snapshot (Admin observability)."""
    return {
        "dry_run": os.getenv("SUPPLIER_DRY_RUN", "true").lower() == "true",
        "supplier_mode": os.getenv("SUPPLIER_MODE", "mouser_then_digikey"),
        "digikey_env": os.getenv("DIGIKEY_ENV", "production"),
        "configured": {
            "mouser_search": settings.mouser_search_enabled,
            "mouser_cart": settings.mouser_cart_enabled,
            "digikey": settings.digikey_enabled,
            "partsbox": settings.partsbox_enabled,
        },
        "cart_dry_run": os.getenv("MOUSER_CART_DRY_RUN", "true").lower() == "true",
        "mylists_enabled": os.getenv("DIGIKEY_MYLISTS_ENABLED", "false").lower() == "true",
        "purchasing_sheet": "live" if settings.graph_enabled else "console-fallback",
    }
