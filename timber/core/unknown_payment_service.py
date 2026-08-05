"""Unknown (unattributed) receipts.

Record money that arrived in a bank account before we know who sent it; it
counts as cash straight away but sits in no party's ledger. When a party
claims it (and we verify), :func:`claim_unknown_payment` turns it into a
normal incoming payment for that party and removes the unknown record — so
the bank total is unchanged, the money simply becomes attributed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from timber.core.audit import log_action
from timber.core.calculations import money
from timber.db.models import BankAccount, Party, UnknownPayment
from timber.db.models.payment import METHOD_ONLINE, PAYMENT_IN, PAYMENT_OUT

ZERO = Decimal("0.00")


def create_unknown_payment(
    session: Session,
    *,
    txn_date: date,
    amount: Any,
    bank_account_id: int,
    direction: str = PAYMENT_IN,
    method: str = METHOD_ONLINE,
    reference_no: str | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> UnknownPayment:
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    if direction not in (PAYMENT_IN, PAYMENT_OUT):
        raise ValueError("Invalid payment direction.")
    if not bank_account_id or session.get(BankAccount, bank_account_id) is None:
        raise ValueError("Please select the account the money arrived in.")
    up = UnknownPayment(
        txn_date=txn_date, amount=amt, bank_account_id=bank_account_id,
        direction=direction,
        method=method, reference_no=(reference_no or None),
        notes=(notes or None), created_by=created_by,
    )
    session.add(up)
    session.flush()
    log_action(session, created_by, "create", "unknown_payments", up.id, str(amt))
    return up


def claim_unknown_payment(
    session: Session,
    unknown_id: int,
    party_id: int,
    created_by: int | None = None,
) -> "Payment":  # noqa: F821
    """Attribute an unknown receipt to a party: create a normal INCOMING
    payment for them (from the same account, same amount/date) and remove
    the unknown record. Net bank change is zero; the party is credited."""
    from timber.core.payment_service import create_payment

    up = session.get(UnknownPayment, unknown_id)
    if up is None or up.is_void:
        raise ValueError("Unknown payment not found.")
    party = session.get(Party, party_id)
    if party is None:
        raise ValueError("Please select who this payment belongs to.")

    # Carry the unknown's own direction across, whatever the party type: an
    # unknown receipt claimed by a SUPPLIER is money they sent back, which the
    # party ledger now treats as raising what we owe rather than settling it.
    payment = create_payment(
        session,
        txn_date=up.txn_date,
        party_id=party_id,
        amount=up.amount,
        direction=up.direction or PAYMENT_IN,
        method=up.method,
        bank_account_id=up.bank_account_id,
        reference_no=up.reference_no,
        notes=up.notes,
        created_by=created_by,
    )
    log_action(
        session, created_by, "claim", "unknown_payments", up.id,
        f"-> {party.name} payment {payment.id}",
    )
    session.delete(up)
    session.flush()
    return payment


def void_unknown_payment(session: Session, unknown_id: int, created_by=None) -> None:
    up = session.get(UnknownPayment, unknown_id)
    if up is None:
        raise ValueError("Unknown payment not found.")
    up.is_void = True
    session.flush()
    log_action(session, created_by, "void", "unknown_payments", unknown_id)


@dataclass
class UnknownRow:
    id: int
    txn_date: date
    amount: Decimal
    account_name: str
    method: str
    reference: str
    notes: str
    direction: str = PAYMENT_IN


def list_unknown_payments(session: Session, limit: int = 500) -> list[UnknownRow]:
    rows: list[UnknownRow] = []
    for up in session.scalars(
        select(UnknownPayment)
        .where(UnknownPayment.is_void.is_(False))
        .order_by(UnknownPayment.txn_date, UnknownPayment.id)
        .limit(limit)
    ):
        rows.append(UnknownRow(
            up.id, up.txn_date, money(up.amount),
            up.bank_account.name if up.bank_account else "—",
            up.method, up.reference_no or "", up.notes or "",
            up.direction or PAYMENT_IN,
        ))
    return rows


def total_unknown(session: Session) -> Decimal:
    """Net unattributed money: unclaimed receipts less unexplained debits."""
    from sqlalchemy import case

    signed = case(
        (UnknownPayment.direction == PAYMENT_IN, UnknownPayment.amount),
        else_=-UnknownPayment.amount,
    )
    total = session.scalar(
        select(func.coalesce(func.sum(signed), 0)).where(
            UnknownPayment.is_void.is_(False)
        )
    )
    return money(total or 0)
