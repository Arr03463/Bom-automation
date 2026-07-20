"""Inventory endpoint — live PartsBox with cache-if-flaky fallback."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.deps import require_user
from db.models import User
from services.partsbox_inventory import get_inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("")
def inventory(user: User = Depends(require_user)) -> dict:
    return get_inventory()
