"""Payments — money received from factories / paid to suppliers.

Read-only: the mobile app lists saved payments. Creating/editing payments
stays on the desktop app, so there is deliberately no POST/PUT/DELETE here.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.payment_service import list_payments
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

router = APIRouter(prefix="/payments", tags=["payments"])

_KIND = {"supplier": PARTY_BAPARI, "factory": PARTY_FACTORY}


@router.get("")
def payments(
    kind: str = Query(..., description="'supplier' or 'factory'"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(500, ge=1, le=2000),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Saved (non-void) payments for one side, newest first."""
    ptype = _KIND.get(kind)
    if ptype is None:
        raise HTTPException(422, "kind must be 'supplier' or 'factory'")
    rows = list_payments(session, ptype, start, end, limit=limit)
    rows.reverse()  # newest first for the phone
    return {"payments": jsonable(rows)}
