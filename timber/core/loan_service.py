"""Loans in BOTH directions, and their repayments.

* **Taken** — we borrow from family/friends: cash INTO an account; our
  repayments take it OUT. Outstanding = what we still owe.
* **Given** — we lend to someone: cash OUT of an account; their
  repayments bring it back IN. Outstanding = what they still owe us.

See bank_service.account_balance for the bank effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from timber.core.audit import log_action
from timber.core.calculations import money
from timber.db.models import BankAccount, Loan, LoanRepayment
from timber.db.models.loan import LOAN_GIVEN, LOAN_TAKEN

ZERO = Decimal("0.00")


def create_loan(
    session: Session,
    *,
    txn_date: date,
    lender_name: str,
    amount: Any,
    direction: str = LOAN_TAKEN,
    bank_account_id: int | None = None,
    expected_return_date: date | None = None,
    notes: str | None = None,
    created_by=None,
) -> Loan:
    lender_name = (lender_name or "").strip()
    if not lender_name:
        raise ValueError("Lender name is required.")
    if direction not in (LOAN_TAKEN, LOAN_GIVEN):
        raise ValueError(f"Unknown loan direction: {direction!r}")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    if bank_account_id and session.get(BankAccount, bank_account_id) is None:
        raise ValueError("Bank account not found.")
    loan = Loan(
        txn_date=txn_date, direction=direction, lender_name=lender_name,
        principal=amt, bank_account_id=bank_account_id,
        expected_return_date=expected_return_date,
        notes=(notes or None), created_by=created_by,
    )
    session.add(loan)
    session.flush()
    log_action(
        session, created_by, "create", "loans", loan.id,
        f"{direction} {lender_name} {amt}",
    )
    return loan


def repaid_total(session: Session, loan_id: int) -> Decimal:
    total = session.scalar(
        select(func.sum(LoanRepayment.amount)).where(LoanRepayment.loan_id == loan_id)
    )
    return money(total or 0)


def repaid_totals(session: Session, loan_ids=None) -> dict[int, Decimal]:
    """Repaid-so-far for MANY loans in one grouped query.

    Calling ``repaid_total`` per loan was an N+1: listing 300 loans issued 300
    extra statements, and on the cloud database each one is a round trip.
    """
    q = (
        select(LoanRepayment.loan_id, func.sum(LoanRepayment.amount))
        .group_by(LoanRepayment.loan_id)
    )
    if loan_ids is not None:
        ids = list(loan_ids)
        if not ids:
            return {}
        q = q.where(LoanRepayment.loan_id.in_(ids))
    return {lid: money(total or 0) for lid, total in session.execute(q).all()}


def loan_outstanding(session: Session, loan_id: int) -> Decimal:
    loan = session.get(Loan, loan_id)
    if loan is None:
        return ZERO
    return money(loan.principal - repaid_total(session, loan_id))


def repay_loan(
    session: Session,
    *,
    loan_id: int,
    txn_date: date,
    amount: Any,
    bank_account_id: int | None = None,
    notes: str | None = None,
    created_by=None,
) -> LoanRepayment:
    loan = session.get(Loan, loan_id)
    if loan is None or loan.is_void:
        raise ValueError("Loan not found.")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    outstanding = loan_outstanding(session, loan_id)
    if amt > outstanding:
        raise ValueError(f"Repayment exceeds the outstanding loan ({outstanding}).")
    if bank_account_id and session.get(BankAccount, bank_account_id) is None:
        raise ValueError("Bank account not found.")
    rep = LoanRepayment(
        loan_id=loan_id, txn_date=txn_date, amount=amt,
        bank_account_id=bank_account_id, notes=(notes or None), created_by=created_by,
    )
    session.add(rep)
    session.flush()
    log_action(session, created_by, "repay", "loans", loan_id, str(amt))
    return rep


def delete_loan(session: Session, loan_id: int, created_by=None) -> None:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise ValueError("Loan not found.")
    session.delete(loan)  # repayments cascade
    session.flush()
    log_action(session, created_by, "delete", "loans", loan_id)


@dataclass
class LoanRow:
    id: int
    txn_date: date
    lender_name: str
    principal: Decimal
    repaid: Decimal
    outstanding: Decimal
    account_name: str
    expected_return_date: date | None
    direction: str = LOAN_TAKEN


def list_loans(
    session: Session, limit: int = 500, direction: str | None = None
) -> list[LoanRow]:
    query = (
        select(Loan)
        .options(joinedload(Loan.bank_account))
        .where(Loan.is_void.is_(False))
    )
    if direction:
        query = query.where(Loan.direction == direction)
    loans = list(session.scalars(query.order_by(Loan.txn_date, Loan.id).limit(limit)))
    # One grouped query for every loan's repayments instead of one per loan.
    repaid_by_id = repaid_totals(session, [loan.id for loan in loans])
    rows: list[LoanRow] = []
    for loan in loans:
        repaid = repaid_by_id.get(loan.id, ZERO)
        rows.append(LoanRow(
            loan.id, loan.txn_date, loan.lender_name, money(loan.principal),
            repaid, money(loan.principal - repaid),
            loan.bank_account.name if loan.bank_account else "—",
            loan.expected_return_date,
            loan.direction or LOAN_TAKEN,
        ))
    return rows


def total_loans_outstanding(
    session: Session, direction: str = LOAN_TAKEN
) -> Decimal:
    """Outstanding total for one direction. Default TAKEN (what we owe
    lenders) — pass LOAN_GIVEN for what borrowers still owe us.

    Done as two SQL aggregates. Walking every loan and summing its repayments
    one at a time meant this single figure cost one query per loan, and it is
    shown on both the Loans page and the Bank Accounts page.
    """
    where = (Loan.is_void.is_(False), Loan.direction == direction)
    principal = session.scalar(
        select(func.coalesce(func.sum(Loan.principal), 0)).where(*where)
    ) or 0
    repaid = session.scalar(
        select(func.coalesce(func.sum(LoanRepayment.amount), 0))
        .join(Loan, LoanRepayment.loan_id == Loan.id)
        .where(*where)
    ) or 0
    return money(principal - repaid)
