"""Master data — reference lists (wood types). Read-only.

Parties (suppliers/factories) are already served by /parties; this adds the
other reference table the desktop Master Data page manages.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.core.current_user import CurrentUser
from timber.db.models import WoodType

router = APIRouter(prefix="/master", tags=["master"])


@router.get("/wood-types")
def wood_types(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """All wood types with their default rates, active first then by name."""
    rows = session.scalars(
        select(WoodType).order_by(WoodType.is_active.desc(), WoodType.name)
    ).all()
    return {
        "wood_types": [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description or "",
                "default_supplier_rate": float(w.default_supplier_rate or 0),
                "default_factory_rate": float(w.default_factory_rate or 0),
                "is_active": bool(w.is_active),
            }
            for w in rows
        ]
    }
