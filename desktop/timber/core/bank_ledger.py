"""Bank account statements — per-transaction running balance and a
day-by-day book where each day's closing carries to the next day's
opening.

An account's money events are: payments in/out tied to it, expenses paid
from it, and transfers to/from it. The running balance always starts at
the account's configured opening balance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from timber import i18n
from timber.core.calculations import money
from timber.db.models import AccountTransfer, BankAccount, Expense, Payment
from timber.db.models.payment import PAYMENT_IN

ZERO = Decimal("0.00")


@dataclass
class BankEvent:
    txn_date: date
    description: str
    source: str          # where the money came FROM
    destination: str     # where the money WENT to
    money_in: Decimal
    money_out: Decimal
    sort_key: tuple


def _events_for(session: Session, account_id: int) -> list[BankEvent]:
    """All money events for one account, oldest first, with the other
    side of each transaction (from / to)."""
    this = session.get(BankAccount, account_id)
    here = this.name if this else "—"
    events: list[BankEvent] = []

    for p in session.scalars(
        select(Payment)
        .options(joinedload(Payment.party))
        .where(
            Payment.bank_account_id == account_id, Payment.is_void.is_(False)
        )
    ):
        party = p.party.name if p.party else "—"
        if p.direction == PAYMENT_IN:
            desc = f"{i18n.tr('payment_in_desc')} {party}"
            events.append(BankEvent(p.txn_date, desc, party, here,
                                    money(p.amount), ZERO, (p.txn_date, 0, p.id)))
        else:
            desc = f"{i18n.tr('payment_out_desc')} {party}"
            events.append(BankEvent(p.txn_date, desc, here, party,
                                    ZERO, money(p.amount), (p.txn_date, 0, p.id)))

    for e in session.scalars(
        select(Expense).where(
            Expense.bank_account_id == account_id, Expense.is_void.is_(False)
        )
    ):
        label = e.category or i18n.tr("expenses")
        if e.note:
            label = f"{label} — {e.note}"
        to = f"{i18n.tr('expenses')}: {label}"
        events.append(BankEvent(e.txn_date, to, here, to,
                                ZERO, money(e.amount), (e.txn_date, 1, e.id)))

    for t in session.scalars(
        select(AccountTransfer)
        .options(joinedload(AccountTransfer.from_account))
        .where(AccountTransfer.to_account_id == account_id)
    ):
        src = t.from_account.name if t.from_account else "—"
        events.append(BankEvent(t.txn_date, f"{i18n.tr('transfer_in')}: {src}",
                                src, here, money(t.amount), ZERO,
                                (t.txn_date, 2, t.id)))
    for t in session.scalars(
        select(AccountTransfer)
        .options(joinedload(AccountTransfer.to_account))
        .where(AccountTransfer.from_account_id == account_id)
    ):
        dst = t.to_account.name if t.to_account else "—"
        events.append(BankEvent(t.txn_date, f"{i18n.tr('transfer_out')}: {dst}",
                                here, dst, ZERO, money(t.amount),
                                (t.txn_date, 3, t.id)))

    events.sort(key=lambda ev: ev.sort_key)
    return events


# --- per-transaction statement ---------------------------------------
@dataclass
class BankLedgerEntry:
    entry_date: date
    description: str
    source: str
    destination: str
    money_in: Decimal
    money_out: Decimal
    balance: Decimal


@dataclass
class BankStatement:
    account_id: int
    account_name: str
    opening: Decimal           # balance before the shown range
    entries: list[BankLedgerEntry]
    closing: Decimal
    total_in: Decimal
    total_out: Decimal


def bank_statement(
    session: Session,
    account_id: int,
    start: date | None = None,
    end: date | None = None,
) -> BankStatement:
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise ValueError("Account not found.")
    events = _events_for(session, account_id)

    running = money(acct.opening_balance)
    # Fold everything before `start` into the opening balance.
    opening = running
    entries: list[BankLedgerEntry] = []
    total_in = total_out = ZERO
    for ev in events:
        if start is not None and ev.txn_date < start:
            running = money(running + ev.money_in - ev.money_out)
            opening = running
            continue
        if end is not None and ev.txn_date > end:
            continue
        running = money(running + ev.money_in - ev.money_out)
        total_in += ev.money_in
        total_out += ev.money_out
        entries.append(
            BankLedgerEntry(ev.txn_date, ev.description, ev.source,
                            ev.destination, ev.money_in, ev.money_out, running)
        )
    return BankStatement(
        account_id, acct.name, money(opening), entries, money(running),
        money(total_in), money(total_out),
    )


# --- daily book (closing carries to next day's opening) --------------
@dataclass
class BankDayRow:
    day: date
    opening: Decimal
    money_in: Decimal
    money_out: Decimal
    closing: Decimal


@dataclass
class BankDailyBook:
    account_id: int
    account_name: str
    rows: list[BankDayRow]


def bank_daily_book(
    session: Session,
    account_id: int,
    start: date | None = None,
    end: date | None = None,
) -> BankDailyBook:
    """Per-day Opening / In / Out / Closing for one account. Each day's
    closing is the next active day's opening (continuity)."""
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise ValueError("Account not found.")
    events = _events_for(session, account_id)

    running = money(acct.opening_balance)
    # Group events by day in chronological order.
    by_day: dict[date, list[BankEvent]] = {}
    for ev in events:
        if end is not None and ev.txn_date > end:
            continue
        if start is not None and ev.txn_date < start:
            running = money(running + ev.money_in - ev.money_out)  # roll into opening
            continue
        by_day.setdefault(ev.txn_date, []).append(ev)

    rows: list[BankDayRow] = []
    for day in sorted(by_day):
        opening = running
        day_in = money(sum((e.money_in for e in by_day[day]), ZERO))
        day_out = money(sum((e.money_out for e in by_day[day]), ZERO))
        running = money(opening + day_in - day_out)
        rows.append(BankDayRow(day, opening, day_in, day_out, running))
    return BankDailyBook(account_id, acct.name, rows)
