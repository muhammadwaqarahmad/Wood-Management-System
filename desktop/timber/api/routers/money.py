"""Money — bank accounts & balances, bank book, transfers, expenses, cheques,
loans. Reads + writes over the same desktop services; writes require
MANAGE_PAYMENTS and keep the desktop's overdraw guards."""
from __future__ import annotations

import os
import tempfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from timber.api.deps import get_current_user, get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.bank_ledger import bank_daily_book, bank_statement
from timber.core.bank_service import (
    all_account_balances,
    all_balances,
    create_account,
    create_transfer,
    delete_transfer,
    ensure_not_overdrawn,
    list_transfers,
    total_cash_position,
    update_account,
    update_transfer,
)
from timber.core.current_user import CurrentUser
from timber.core.expense_service import (
    create_expense,
    list_expenses,
    update_expense,
    void_expense,
)
from timber.core.loan_service import (
    create_loan,
    delete_loan,
    list_loans,
    repay_loan,
    total_loans_outstanding,
)
from timber.core.payment_service import (
    bounce_cheque,
    cheque_balance,
    clear_cheque,
    list_cheques,
)
from timber.core.permissions import Permission
from timber.db.models import BankAccount, Loan
from timber.db.models.loan import LOAN_GIVEN

router = APIRouter(prefix="/money", tags=["money"])

_MANAGE = require_permission(Permission.MANAGE_PAYMENTS)
_SETTINGS = require_permission(Permission.MANAGE_SETTINGS)


@router.get("/accounts")
def accounts(
    include_inactive: bool = False,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Every bank account (and Cash) with its current balance. Same columns
    the desktop Bank Accounts table shows — including IBAN, branch, and today's
    rolling opening (yesterday's closing). ``include_inactive`` matches the
    desktop management screen (which lists inactive accounts too); the money
    dropdowns leave it off so they only offer active accounts."""
    balances = all_balances(session, active_only=not include_inactive)
    # Today's opening = the balance carried in from before today, in ONE batched
    # call for every account (not one query each) — same as the desktop.
    openings = all_account_balances(session, before=date.today())
    return [
        {
            "id": b.id,
            "name": b.name,
            "closing": float(b.closing),
            "is_cash": b.is_cash,
            "is_active": b.is_active,
            "bank_name": b.bank_name,
            "account_number": b.account_number,
            "iban": b.iban,
            "branch": b.branch,
            "opening": float(b.opening),                       # configured opening
            "opening_today": float(openings.get(b.id, b.opening)),
        }
        for b in balances
    ]


@router.get("/summary")
def money_summary(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The three KPI tiles atop the desktop Bank Accounts screen."""
    return {
        "cash_position": float(total_cash_position(session)),
        "cheque_balance": float(cheque_balance(session)),
        "total_loans": float(total_loans_outstanding(session)),
    }


@router.get("/accounts/{account_id}")
def account_detail(
    account_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Full detail for the edit dialog — bilingual names + all fields."""
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise HTTPException(404, "Account not found")
    return {
        "id": acct.id, "name": acct.name,
        "name_en": acct.name_en, "name_ur": acct.name_ur,
        "bank_name": acct.bank_name or "", "account_number": acct.account_number or "",
        "iban": acct.iban or "", "branch": acct.branch or "",
        "opening_balance": float(acct.opening_balance),
        "is_active": bool(acct.is_active),
    }


@router.get("/accounts/{account_id}/book")
def bank_book(
    account_id: int,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Both Bank Book views for one account in one call: the per-transaction
    ``statement`` (with opening/closing/totals) and the ``daily`` summary
    (each day's closing carries to the next day's opening) — so the web can
    switch views without another round-trip, exactly like the desktop screen."""
    try:
        st = bank_statement(session, account_id, start, end)
        book = bank_daily_book(session, account_id, start, end)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Account not found")
    return {
        "account_name": st.account_name,
        "opening": float(st.opening),
        "closing": float(st.closing),
        "total_in": float(st.total_in),
        "total_out": float(st.total_out),
        "entries": jsonable(st.entries),
        "daily": [
            {
                "day": r.day.isoformat(), "opening": float(r.opening),
                "money_in": float(r.money_in), "money_out": float(r.money_out),
                "closing": float(r.closing),
            }
            for r in book.rows
        ],
    }


@router.get("/accounts/{account_id}/book/export")
def bank_book_export(
    account_id: int,
    fmt: str = "pdf",
    view: str = "statement",
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download one account's Bank Book as PDF/Excel — the daily summary or the
    per-transaction statement, exactly what the desktop screen exports."""
    from timber.core.report_data import bank_daily_report, bank_statement_report

    builder = bank_daily_report if view == "daily" else bank_statement_report
    try:
        report = builder(session, account_id, start, end)
    except (ValueError, AttributeError):
        raise HTTPException(404, "Account not found")
    # reportlab / openpyxl are heavy — import only when someone actually exports.
    from timber.core import excel_export, pdf_export

    is_xlsx = fmt == "xlsx"
    writer = excel_export if is_xlsx else pdf_export
    suffix = "xlsx" if is_xlsx else "pdf"
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if is_xlsx else "application/pdf")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + suffix)
    tmp.close()
    try:
        writer.write(report, tmp.name)
    except Exception as exc:  # noqa: BLE001
        os.unlink(tmp.name)
        raise HTTPException(500, f"Export failed: {exc}")
    return FileResponse(
        tmp.name, filename=f"bank_book.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )


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


# ------------------------------------------------------------------ writes ---
# All reuse the desktop services and require MANAGE_PAYMENTS. Money-out paths
# keep the desktop's "can't overdraw an account" guard.

class ExpenseIn(BaseModel):
    txn_date: date
    category: str
    amount: float
    kind: str = "business"
    bank_account_id: int | None = None
    note: str | None = None


class TransferIn(BaseModel):
    txn_date: date
    from_account_id: int
    to_account_id: int
    amount: float
    note: str | None = None


class LoanIn(BaseModel):
    txn_date: date
    lender_name: str
    amount: float
    direction: str = "taken"
    bank_account_id: int | None = None
    expected_return_date: date | None = None
    notes: str | None = None


class RepayIn(BaseModel):
    txn_date: date
    amount: float
    bank_account_id: int | None = None
    notes: str | None = None


# --- expenses ---
@router.post("/expenses")
def create_expense_ep(body: ExpenseIn, session: Session = Depends(get_session),
                      user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        exp = create_expense(
            session, txn_date=body.txn_date, category=body.category,
            amount=body.amount, kind=body.kind,
            bank_account_id=body.bank_account_id, note=body.note,
            created_by=user.id,
        )
        ensure_not_overdrawn(session, body.bank_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": exp.id}


@router.put("/expenses/{expense_id}")
def update_expense_ep(expense_id: int, body: ExpenseIn,
                      session: Session = Depends(get_session),
                      user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        update_expense(
            session, expense_id, txn_date=body.txn_date, category=body.category,
            amount=body.amount, kind=body.kind,
            bank_account_id=body.bank_account_id, note=body.note,
            created_by=user.id,
        )
        ensure_not_overdrawn(session, body.bank_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/expenses/{expense_id}/void")
def void_expense_ep(expense_id: int, session: Session = Depends(get_session),
                    user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        void_expense(session, expense_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


# --- transfers ---
@router.post("/transfers")
def create_transfer_ep(body: TransferIn, session: Session = Depends(get_session),
                       user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        t = create_transfer(
            session, txn_date=body.txn_date, from_account_id=body.from_account_id,
            to_account_id=body.to_account_id, amount=body.amount, note=body.note,
            created_by=user.id,
        )
        ensure_not_overdrawn(session, body.from_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": t.id}


@router.put("/transfers/{transfer_id}")
def update_transfer_ep(transfer_id: int, body: TransferIn,
                       session: Session = Depends(get_session),
                       user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        update_transfer(
            session, transfer_id, txn_date=body.txn_date,
            from_account_id=body.from_account_id, to_account_id=body.to_account_id,
            amount=body.amount, note=body.note, created_by=user.id,
        )
        ensure_not_overdrawn(session, body.from_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/transfers/{transfer_id}")
def delete_transfer_ep(transfer_id: int, session: Session = Depends(get_session),
                       user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        delete_transfer(session, transfer_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


# --- loans ---
@router.post("/loans")
def create_loan_ep(body: LoanIn, session: Session = Depends(get_session),
                   user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        loan = create_loan(
            session, txn_date=body.txn_date, lender_name=body.lender_name,
            amount=body.amount, direction=body.direction,
            bank_account_id=body.bank_account_id,
            expected_return_date=body.expected_return_date, notes=body.notes,
            created_by=user.id,
        )
        # Lending money out can't overdraw the account.
        if body.direction == LOAN_GIVEN:
            ensure_not_overdrawn(session, body.bank_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": loan.id}


@router.post("/loans/{loan_id}/repay")
def repay_loan_ep(loan_id: int, body: RepayIn,
                  session: Session = Depends(get_session),
                  user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        loan = session.get(Loan, loan_id)
        repay_loan(
            session, loan_id=loan_id, txn_date=body.txn_date, amount=body.amount,
            bank_account_id=body.bank_account_id, notes=body.notes,
            created_by=user.id,
        )
        # Repaying a TAKEN loan sends money out — never overdraw.
        if loan is not None and loan.direction != LOAN_GIVEN:
            ensure_not_overdrawn(session, body.bank_account_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/loans/{loan_id}")
def delete_loan_ep(loan_id: int, session: Session = Depends(get_session),
                   user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        delete_loan(session, loan_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


# --- cheques ---
@router.post("/cheques/{payment_id}/clear")
def clear_cheque_ep(payment_id: int, session: Session = Depends(get_session),
                    user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        clear_cheque(session, payment_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/cheques/{payment_id}/bounce")
def bounce_cheque_ep(payment_id: int, session: Session = Depends(get_session),
                     user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        bounce_cheque(session, payment_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


# --- bank accounts (create / edit) — MANAGE_SETTINGS ---
class AccountIn(BaseModel):
    name_en: str | None = None
    name_ur: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    iban: str | None = None
    branch: str | None = None
    opening_balance: float | None = None


@router.post("/accounts")
def create_account_ep(body: AccountIn, session: Session = Depends(get_session),
                      user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        acct = create_account(
            session, name_en=body.name_en, name_ur=body.name_ur,
            bank_name=body.bank_name, account_number=body.account_number,
            iban=body.iban, branch=body.branch,
            opening_balance=body.opening_balance or 0, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": acct.id}


@router.put("/accounts/{account_id}")
def update_account_ep(account_id: int, body: AccountIn,
                      session: Session = Depends(get_session),
                      user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        update_account(
            session, account_id, name_en=body.name_en, name_ur=body.name_ur,
            bank_name=body.bank_name, account_number=body.account_number,
            iban=body.iban, branch=body.branch,
            opening_balance=body.opening_balance, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
