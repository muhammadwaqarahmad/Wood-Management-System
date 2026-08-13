"""Payments — money received from factories / paid to suppliers.

Read: list saved payments. Write (create / void): reuses the desktop's tested
``payment_service`` so the numbers are identical everywhere. Writes require the
MANAGE_PAYMENTS permission (same rule as the desktop).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.bank_service import ensure_not_overdrawn
from timber.core.current_user import CurrentUser
from timber.core.payment_service import create_payment, list_payments, void_payment
from timber.core.permissions import Permission
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import METHOD_CASH, PAYMENT_OUT

router = APIRouter(prefix="/payments", tags=["payments"])

_KIND = {"supplier": PARTY_BAPARI, "factory": PARTY_FACTORY}


class PaymentIn(BaseModel):
    """A payment to record. Mirrors ``payment_service.create_payment`` — the
    received date drives the ledger; the entry date is when it was booked."""

    txn_date: date
    party_id: int
    amount: float
    entry_date: date | None = None
    direction: str | None = None          # None -> natural for the party type
    method: str = METHOD_CASH
    bank_account_id: int | None = None
    party_bank_id: int | None = None
    reference_no: str | None = None
    notes: str | None = None
    split_side: str | None = None


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


@router.post("")
def create(
    body: PaymentIn,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_permission(Permission.MANAGE_PAYMENTS)),
) -> dict:
    """Record a payment (reuses the desktop's ``create_payment``)."""
    try:
        payment = create_payment(
            session,
            txn_date=body.txn_date,
            entry_date=body.entry_date,
            party_id=body.party_id,
            amount=body.amount,
            direction=body.direction,
            method=body.method,
            bank_account_id=body.bank_account_id,
            party_bank_id=body.party_bank_id,
            reference_no=body.reference_no,
            notes=body.notes,
            split_side=body.split_side,
            created_by=user.id,
        )
        # Same guard as the desktop: money LEAVING us can't overdraw the account.
        if payment.direction == PAYMENT_OUT and body.bank_account_id:
            ensure_not_overdrawn(session, body.bank_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Return the id; the client refetches the list (jsonable is for the
    # lightweight read-row objects, not raw ORM models).
    return {"id": payment.id}


@router.post("/{payment_id}/void")
def void(
    payment_id: int,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_permission(Permission.MANAGE_PAYMENTS)),
) -> dict:
    """Void a saved payment (reverses it in the ledger and the bank)."""
    try:
        void_payment(session, payment_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
