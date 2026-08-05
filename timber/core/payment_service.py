"""Payment services — record money received from factories or paid to
baparis. Validates, audits, flushes; the caller commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from timber.core.audit import log_action
from timber.core.calculations import balance_amount, money
from timber.db.models import (
    BapariTxn,
    FactoryTxn,
    Party,
    Payment,
    PaymentAllocation,
)
from timber.db.models.party import PARTY_BAPARI
from timber.db.models.payment import (
    CHEQUE_BOUNCED,
    CHEQUE_CLEARED,
    CHEQUE_PENDING,
    METHOD_BANK,
    METHOD_CASH,
    METHOD_CHEQUE,
    METHOD_ONLINE,
    natural_direction,
    PAYMENT_IN,
    PAYMENT_OUT,
)

VALID_METHODS = {METHOD_CASH, METHOD_ONLINE, METHOD_BANK, METHOD_CHEQUE}

ZERO = Decimal("0.00")


def create_payment(
    session: Session,
    *,
    txn_date: date,
    party_id: int,
    amount: Any,
    direction: str | None = None,
    method: str = METHOD_CASH,
    bank_name: str | None = None,
    bank_account_id: int | None = None,
    party_bank_id: int | None = None,
    reference_no: str | None = None,
    notes: str | None = None,
    split_side: str | None = None,
    created_by: int | None = None,
) -> Payment:
    party = session.get(Party, party_id) if party_id else None
    if party is None:
        raise ValueError("Please select a party.")

    try:
        amt = money(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Amount must be a number.")
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")

    # Infer direction from the party type if not given:
    # pay OUT to a bapari, receive IN from a factory.
    if direction is None:
        direction = PAYMENT_OUT if party.party_type == PARTY_BAPARI else PAYMENT_IN
    if direction not in (PAYMENT_IN, PAYMENT_OUT):
        raise ValueError("Invalid payment direction.")

    if method not in VALID_METHODS:
        raise ValueError(f"Unknown payment method: {method!r}")

    # Cash flows through the dedicated Cash account so it has a balance too.
    if method == METHOD_CASH and bank_account_id is None:
        from timber.core.bank_service import cash_account

        bank_account_id = cash_account(session).id
    elif bank_account_id is not None:
        from timber.db.models import BankAccount

        if session.get(BankAccount, bank_account_id) is None:
            raise ValueError("Bank account not found.")

    payment = Payment(
        txn_date=txn_date,
        party_id=party_id,
        direction=direction,
        amount=amt,
        method=method,
        bank_name=(bank_name or None),
        bank_account_id=bank_account_id,
        party_bank_id=party_bank_id,
        reference_no=(reference_no or None),
        notes=(notes or None),
        # A cheque starts PENDING: it settles the party now but only moves
        # the bank balance once it clears.
        cheque_status=CHEQUE_PENDING if method == METHOD_CHEQUE else None,
        split_side=split_side if split_side in ("left", "right") else None,
        created_by=created_by,
    )
    session.add(payment)
    session.flush()
    log_action(
        session, created_by, "create", "payments", payment.id,
        f"{direction} {amt} via {method}",
    )
    # Recompute FIFO allocations for the party (advance-aware).
    reallocate_party(session, party_id)
    return payment


def update_payment(
    session: Session,
    payment_id: int,
    *,
    txn_date: date,
    amount: Any,
    direction: str | None = None,
    method: str = METHOD_CASH,
    bank_account_id: int | None = None,
    party_bank_id: int | None = None,
    reference_no: str | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("Payment not found.")
    # Omitted direction leaves the stored one alone, so existing callers that
    # never knew about it keep working.
    if direction is not None and direction not in (PAYMENT_IN, PAYMENT_OUT):
        raise ValueError("Invalid payment direction.")
    try:
        amt = money(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Amount must be a number.")
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    if method not in VALID_METHODS:
        raise ValueError(f"Unknown payment method: {method!r}")
    if method == METHOD_CASH and bank_account_id is None:
        from timber.core.bank_service import cash_account
        bank_account_id = cash_account(session).id
    elif bank_account_id is not None:
        from timber.db.models import BankAccount
        if session.get(BankAccount, bank_account_id) is None:
            raise ValueError("Bank account not found.")

    payment.txn_date = txn_date
    payment.amount = amt
    if direction is not None:
        payment.direction = direction
    payment.method = method
    payment.bank_account_id = bank_account_id
    payment.party_bank_id = party_bank_id
    payment.reference_no = (reference_no or None)
    payment.notes = (notes or None)
    session.flush()
    log_action(session, created_by, "update", "payments", payment_id, f"{amt} via {method}")
    reallocate_party(session, payment.party_id)
    return payment


def void_payment(
    session: Session, payment_id: int, created_by: int | None = None
) -> None:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("Payment not found.")
    payment.is_void = True
    session.flush()
    # Recompute allocations so the freed loads show outstanding again.
    reallocate_party(session, payment.party_id)
    log_action(session, created_by, "void", "payments", payment_id)


# --- cheques --------------------------------------------------------
def _require_cheque(session: Session, payment_id: int) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is None or payment.method != METHOD_CHEQUE:
        raise ValueError("Cheque not found.")
    return payment


def clear_cheque(session: Session, payment_id: int, cleared_date=None, created_by=None) -> Payment:
    """Mark a pending cheque CLEARED -> it now moves the bank balance."""
    from datetime import date as _date

    payment = _require_cheque(session, payment_id)
    payment.cheque_status = CHEQUE_CLEARED
    payment.cleared_date = cleared_date or _date.today()
    session.flush()
    log_action(session, created_by, "clear", "payments", payment_id)
    return payment


def bounce_cheque(session: Session, payment_id: int, created_by=None) -> Payment:
    """Mark a cheque BOUNCED -> it reverses (party owes again, no bank move)."""
    payment = _require_cheque(session, payment_id)
    payment.cheque_status = CHEQUE_BOUNCED
    payment.cleared_date = None
    session.flush()
    reallocate_party(session, payment.party_id)  # party balance re-opens
    log_action(session, created_by, "bounce", "payments", payment_id)
    return payment


@dataclass
class ChequeRow:
    id: int
    txn_date: date
    party_name: str
    direction: str          # in (received) / out (issued)
    amount: Decimal
    account_name: str
    reference: str
    status: str
    cleared_date: date | None


def list_cheques(session: Session, status: str | None = None, limit: int = 1000) -> list[ChequeRow]:
    query = (
        select(Payment)
        .options(joinedload(Payment.party), joinedload(Payment.bank_account))
        .where(Payment.method == METHOD_CHEQUE, Payment.is_void.is_(False))
        .order_by(Payment.txn_date, Payment.id)
        .limit(limit)
    )
    if status:
        query = query.where(Payment.cheque_status == status)
    rows: list[ChequeRow] = []
    for p in session.scalars(query):
        rows.append(ChequeRow(
            p.id, p.txn_date, p.party.name if p.party else "—", p.direction,
            money(p.amount), p.bank_account.name if p.bank_account else "—",
            p.reference_no or "", p.cheque_status or CHEQUE_PENDING, p.cleared_date,
        ))
    return rows


def cheque_balance(session: Session) -> Decimal:
    """Net value of PENDING cheques: received (in) positive, issued (out)
    negative — i.e. money that will land / leave once cheques clear."""
    total = Decimal("0")
    for p in session.scalars(
        select(Payment).where(
            Payment.method == METHOD_CHEQUE,
            Payment.is_void.is_(False),
            Payment.cheque_status == CHEQUE_PENDING,
        )
    ):
        total += p.amount if p.direction == PAYMENT_IN else -p.amount
    return money(total)


# --- FIFO load allocation -------------------------------------------
def _kind_for(party_type: str) -> str:
    return "bapari" if party_type == PARTY_BAPARI else "factory"


def _model_for(kind: str):
    return BapariTxn if kind == "bapari" else FactoryTxn


def _allocated_to_load(session: Session, kind: str, txn_id: int) -> Decimal:
    total = session.scalar(
        select(func.sum(PaymentAllocation.amount)).where(
            PaymentAllocation.kind == kind, PaymentAllocation.txn_id == txn_id
        )
    )
    return money(total or 0)


def allocated_by_load(session: Session, kind: str, txn_ids) -> dict:
    """Paid-so-far for MANY loads in one grouped query — the per-load
    variant above is O(N) queries when a ledger renders years of rows."""
    txn_ids = list(txn_ids)
    if not txn_ids:
        return {}
    rows = session.execute(
        select(PaymentAllocation.txn_id, func.sum(PaymentAllocation.amount))
        .where(PaymentAllocation.kind == kind, PaymentAllocation.txn_id.in_(txn_ids))
        .group_by(PaymentAllocation.txn_id)
    ).all()
    return {tid: money(total or 0) for tid, total in rows}


@dataclass
class OutstandingLoad:
    txn_id: int
    txn_date: date
    amount: Decimal
    paid: Decimal
    outstanding: Decimal
    days: int  # days since the load date


def party_outstanding_loads(session: Session, party_id: int) -> list[OutstandingLoad]:
    """Each of the party's loads with how much is paid vs outstanding,
    plus how many days old it is, oldest first."""
    party = session.get(Party, party_id)
    if party is None:
        return []
    kind = _kind_for(party.party_type)
    model = _model_for(kind)
    today = date.today()
    load_rows = session.execute(
        select(model.id, model.txn_date, model.bill, model.freight)
        .where(model.party_id == party_id, model.is_void.is_(False))
        .order_by(model.txn_date, model.id)
    ).all()
    paid_map = allocated_by_load(session, kind, [r[0] for r in load_rows])
    rows: list[OutstandingLoad] = []
    for load_id, txn_date, bill, freight in load_rows:
        amount = balance_amount(bill, freight)
        paid = paid_map.get(load_id, ZERO)
        rows.append(
            OutstandingLoad(
                load_id, txn_date, amount, paid, money(amount - paid),
                (today - txn_date).days,
            )
        )
    return rows


def all_parties_outstanding_loads(
    session: Session, party_type: str
) -> dict[int, list[OutstandingLoad]]:
    """Same rows as :func:`party_outstanding_loads`, but for EVERY party of a
    side in TWO queries instead of ~3 per party.

    The Reports page needs each party's loads to age its overdue buckets; doing
    that one party at a time was an N+1 (~200 queries with the client's ~95
    parties, i.e. tens of seconds on a cloud database). Returns
    ``{party_id: [OutstandingLoad, ...]}`` with the same ordering (oldest
    first) so the results are identical to the per-party call.
    """
    kind = _kind_for(party_type)
    model = _model_for(kind)
    today = date.today()
    load_rows = session.execute(
        select(model.party_id, model.id, model.txn_date, model.bill, model.freight)
        .where(model.is_void.is_(False))
        .order_by(model.party_id, model.txn_date, model.id)
    ).all()
    paid_map = allocated_by_load(session, kind, [r[1] for r in load_rows])
    out: dict[int, list[OutstandingLoad]] = {}
    for party_id, load_id, txn_date, bill, freight in load_rows:
        amount = balance_amount(bill, freight)
        paid = paid_map.get(load_id, ZERO)
        out.setdefault(party_id, []).append(
            OutstandingLoad(
                load_id, txn_date, amount, paid, money(amount - paid),
                (today - txn_date).days,
            )
        )
    return out


def reallocate_party(session: Session, party_id: int) -> None:
    """Recompute all FIFO allocations for a party from scratch: each
    payment (oldest first) is applied to loads (oldest first). Running
    this whenever a payment OR a load changes means advances paid before
    a load is created still settle that load. Leftover = advance.
    """
    party = session.get(Party, party_id)
    if party is None:
        return
    kind = _kind_for(party.party_type)
    model = _model_for(kind)

    # Everything below works on plain tuples + one bulk insert: with years
    # of history this runs on every save, so ORM-object hydration and
    # row-by-row adds are too expensive.
    session.flush()
    pay_ids = list(session.scalars(select(Payment.id).where(Payment.party_id == party_id)))
    if pay_ids:
        session.execute(
            delete(PaymentAllocation).where(PaymentAllocation.payment_id.in_(pay_ids))
        )

    load_rows = session.execute(
        select(model.id, model.bill, model.freight)
        .where(model.party_id == party_id, model.is_void.is_(False))
        .order_by(model.txn_date, model.id)
    ).all()
    remaining_load = {rid: balance_amount(bill, freight) for rid, bill, freight in load_rows}
    order = [rid for rid, _b, _f in load_rows]

    # A positive opening balance is the party's oldest debt; payments must
    # clear it FIRST before they settle any load. Otherwise a payment (or
    # advance) would skip the old balance and wrongly mark a new load paid.
    opening_remaining = max(money(party.opening_balance), Decimal("0"))

    all_pay_rows = session.execute(
        select(Payment.id, Payment.amount, Payment.direction)
        .where(
            Payment.party_id == party_id,
            Payment.is_void.is_(False),
            Payment.cheque_status.is_distinct_from(CHEQUE_BOUNCED),  # exclude bounced (NULL-safe)
        )
        .order_by(Payment.txn_date, Payment.id)
    ).all()

    # Only natural-direction payments settle loads. A reverse one (a supplier
    # refunding us) is money that came BACK, so it cannot be allocated to a
    # bill — instead it shrinks the pool the real payments have to spend, which
    # re-opens the most recent bills. Netting here is what keeps the allocation
    # table agreeing with party_balance: both end up using the same net figure.
    natural = natural_direction(party.party_type)
    pay_rows = [(pid, amt) for pid, amt, d in all_pay_rows if d == natural]
    refunded = sum((money(amt) for _pid, amt, d in all_pay_rows if d != natural),
                   Decimal("0"))
    settling = sum((money(amt) for _pid, amt in pay_rows), Decimal("0"))
    # Never below zero: refunds beyond what was ever paid just leave the loads
    # fully outstanding, they do not create negative allocations.
    budget = max(money(settling - refunded), Decimal("0"))

    allocations: list[dict] = []
    start = 0  # loads before this index are fully settled — skip rescanning
    for pay_id, amount in pay_rows:
        # Spend from the refund-netted budget, not the raw amount.
        remaining = min(money(amount), budget)
        budget = money(budget - remaining)
        if opening_remaining > 0:
            take = min(remaining, opening_remaining)
            opening_remaining = money(opening_remaining - take)
            remaining = money(remaining - take)
        i = start
        while i < len(order) and remaining > 0:
            load_id = order[i]
            outstanding = remaining_load.get(load_id, Decimal("0"))
            if outstanding <= 0:
                if i == start:
                    start += 1
                i += 1
                continue
            take = min(remaining, outstanding)
            allocations.append(
                dict(payment_id=pay_id, kind=kind, txn_id=load_id, amount=take)
            )
            remaining_load[load_id] = money(outstanding - take)
            remaining = money(remaining - take)
            i += 1
    if allocations:
        from sqlalchemy import insert

        session.execute(insert(PaymentAllocation), allocations)
    session.flush()


def party_bank_label(pb) -> str:
    """Short label for a party's bank account."""
    if pb is None:
        return "—"
    parts = [pb.bank_name, pb.account_number or pb.iban]
    return " ".join(p for p in parts if p) or (pb.account_title or "—")


@dataclass
class PaymentRow:
    id: int
    txn_date: date
    party_name: str
    amount: Decimal
    method: str
    account_name: str
    party_account: str
    reference: str


def list_payments(
    session: Session,
    party_type: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = 1000,
) -> list[PaymentRow]:
    """Non-void payments for parties of the given type (newest first),
    optionally limited to a date range."""
    rows: list[PaymentRow] = []
    query = (
        select(Payment)
        .join(Party, Payment.party_id == Party.id)
        .options(
            joinedload(Payment.party),
            joinedload(Payment.bank_account),
            joinedload(Payment.party_bank),
        )
        .where(Party.party_type == party_type, Payment.is_void.is_(False))
    )
    if start is not None:
        query = query.where(Payment.txn_date >= start)
    if end is not None:
        query = query.where(Payment.txn_date <= end)
    query = query.order_by(Payment.txn_date, Payment.id).limit(limit)
    for p in session.scalars(query):
        rows.append(
            PaymentRow(
                p.id, p.txn_date, p.party.name, p.amount, p.method,
                p.bank_account.name if p.bank_account else "—",
                party_bank_label(p.party_bank),
                p.reference_no or "",
            )
        )
    return rows
