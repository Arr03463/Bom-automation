"""Inventory endpoint — live PartsBox with cache-if-flaky fallback."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.deps import require_user
from db.models import User
from services.partsbox_inventory import get_inventory, get_inventory_stats

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/stats")
def inventory_stats(user: User = Depends(require_user)) -> dict:
    """Aggregate counts only — what the header tiles need.

    Declared BEFORE the "" route: FastAPI matches in declaration order, and a
    later literal path can be shadowed by an earlier parameterised one.

    This is the eager, hydration-time call. The full ~1MB part list is fetched
    lazily by the Inventory screen instead.
    """
    return get_inventory_stats()


@router.get("")
def inventory(user: User = Depends(require_user)) -> dict:
    return get_inventory()
