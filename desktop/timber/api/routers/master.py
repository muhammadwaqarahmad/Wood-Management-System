"""Master data — reference lists (locations, wood types).

Read + write. Writes reuse ``admin_service`` lookup helpers; add/rename/rates/
activate need MANAGE_SETTINGS, hard delete needs DELETE_RECORD (same as desktop).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session, require_permission
from timber.core.admin_service import (
    create_lookup,
    delete_lookup,
    rename_lookup,
    set_lookup_active,
    set_lookup_rates,
)
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.db.models import Location, WoodType

router = APIRouter(prefix="/master", tags=["master"])

_LOOKUP = {"location": Location, "wood_type": WoodType}
_SETTINGS = require_permission(Permission.MANAGE_SETTINGS)
_DELETE = require_permission(Permission.DELETE_RECORD)


def _model(kind: str):
    model = _LOOKUP.get(kind)
    if model is None:
        raise HTTPException(422, "kind must be 'location' or 'wood_type'")
    return model


class NameIn(BaseModel):
    name: str


class RatesIn(BaseModel):
    supplier_rate: float | None = None
    factory_rate: float | None = None


@router.get("/locations")
def locations(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """All locations (cities), active first then by name."""
    rows = session.scalars(
        select(Location).order_by(Location.is_active.desc(), Location.name)
    ).all()
    return {
        "locations": [
            {"id": r.id, "name": r.name, "is_active": bool(r.is_active)}
            for r in rows
        ]
    }


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


# ------------------------------------------------------------------ writes ---

@router.post("/{kind}")
def create(kind: str, body: NameIn, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        obj = create_lookup(session, _model(kind), body.name, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": obj.id}


@router.put("/{kind}/{obj_id}")
def rename(kind: str, obj_id: int, body: NameIn,
           session: Session = Depends(get_session),
           user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        rename_lookup(session, _model(kind), obj_id, body.name, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{kind}/{obj_id}/rates")
def rates(kind: str, obj_id: int, body: RatesIn,
          session: Session = Depends(get_session),
          user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        set_lookup_rates(session, _model(kind), obj_id,
                         supplier_rate=body.supplier_rate,
                         factory_rate=body.factory_rate, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{kind}/{obj_id}/active")
def set_active(kind: str, obj_id: int, active: bool,
               session: Session = Depends(get_session),
               user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        set_lookup_active(session, _model(kind), obj_id, active, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/{kind}/{obj_id}")
def delete(kind: str, obj_id: int, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_DELETE)) -> dict:
    try:
        delete_lookup(session, _model(kind), obj_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
