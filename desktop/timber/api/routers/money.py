"""Money — bank accounts & balances, bank book, transfers, expenses, cheques,
loans. Read-only views of the desktop Money section, from the same services."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.bank_ledger import bank_statement
from timber.core.bank_service import all_balances, list_transfers
from timber.core.current_user import CurrentUser
from timber.core.expense_service import list_expenses
from timber.core.loan_service import list_loans
from timber.core.payment_service import list_cheques

router = APIRouter(prefix="/money", tags=["money"])


@router.get("/accounts")
def accounts(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Every bank account (and Cash) with its current balance."""
    return [
        {
            "id": b.id,
            "name": b.name,
            "closing": float(b.closing),
            "is_cash": b.is_cash,
            "is_active": b.is_active,
            "bank_name": b.bank_name,
            "account_number": b.account_number,
        }
        for b in all_balances(session)
    ]


@router.get("/accounts/{account_id}/book")
def bank_book(
    account_id: int,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Running statement for one account (every money-in / money-out event)."""
    try:
        st = bank_statement(session, account_id, start, end)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Account not found")
    return {
        "account_name": st.account_name,
        "opening": float(st.opening),
        "closing": float(st.closing),
        "total_in": float(st.total_in),
        "total_out": float(st.total_out),
        "entries": jsonable(st.entries),
    }


@router.get("/transfers")
def transfers(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return jsonable(list_transfers(session, start=start, end=end))


@router.get("/expenses")
def expenses(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return jsonable(list_expenses(session, start=start, end=end))


@router.get("/cheques")
def cheques(
    status: str | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Cheques, optionally filtered by status (pending / cleared / bounced)."""
    return jsonable(list_cheques(session, status=status))


@router.get("/loans")
def loans(
    direction: str | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return jsonable(list_loans(session, direction=direction))
