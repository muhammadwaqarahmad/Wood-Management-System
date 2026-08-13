"""Dashboard aggregations — summary cards, trends, breakdowns, alerts.

All read-only, Session-based, returning lightweight values so the UI
just renders them. Money is Decimal throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from timber.core.calculations import money
from timber.core.ledger import total_payable, total_receivable
from timber.core.reports import party_summaries
from timber.db.models import (
    BapariTxn,
    CombinedTxn,
    FactoryTxn,
    Location,
    Payment,
    WoodType,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT

ZERO = Decimal("0.00")
NONE_LABEL = "—"


@dataclass
class DashboardCards:
    receivable: Decimal
    payable: Decimal
    net: Decimal
    total_profit: Decimal       # expected (accrual) — recognised at sale
    collected_profit: Decimal   # realised — only as the factory pays
    cash_in: Decimal
    cash_out: Decimal


def collected_profit(session: Session) -> Decimal:
    """Profit actually realised: for each trade, its profit times the
    fraction of that sale the factory has already paid (FIFO-allocated).
    A fully-paid sale contributes its whole profit; an unpaid one, zero.
    """
    from timber.core.calculations import balance_amount
    from timber.core.payment_service import allocated_by_load

    # Fetch only the four values the arithmetic needs, not whole trade + load
    # objects. The per-load maths below is byte-for-byte the same — this only
    # stops us shipping ~15 columns × every trade across the wire (which is
    # most of this call's cost over a cloud link).
    rows = session.execute(
        select(CombinedTxn.profit, FactoryTxn.id,
               FactoryTxn.bill, FactoryTxn.freight)
        .join(FactoryTxn, CombinedTxn.factory_txn_id == FactoryTxn.id)
    ).all()
    paid_map = allocated_by_load(session, "factory", [r[1] for r in rows])
    total = ZERO
    for profit, factory_id, bill, freight in rows:
        amount = balance_amount(bill, freight)
        if amount <= 0:
            total += profit
            continue
        paid = paid_map.get(factory_id, ZERO)
        fraction = paid / amount
        if fraction > 1:
            fraction = Decimal("1")
        total += profit * fraction
    return money(total)


def _sum_payments(session: Session, direction: str) -> Decimal:
    # One SUM on the server instead of pulling every payment row to add up.
    return money(session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.direction == direction, Payment.is_void.is_(False)
        )
    ))


def dashboard_cards(session: Session) -> DashboardCards:
    receivable = total_receivable(session)
    payable = total_payable(session)
    total_profit = money(
        session.scalar(select(func.coalesce(func.sum(CombinedTxn.profit), 0)))
    )
    return DashboardCards(
        receivable=receivable,
        payable=payable,
        net=money(receivable - payable),
        total_profit=total_profit,
        collected_profit=collected_profit(session),
        cash_in=_sum_payments(session, PAYMENT_IN),
        cash_out=_sum_payments(session, PAYMENT_OUT),
    )


def monthly_profit(session: Session, months: int = 6) -> list[tuple[str, Decimal]]:
    """Profit per calendar month for the last ``months`` months."""
    keys = _recent_months(months)
    # Only the window is needed — fetch just that, not all history. Grouping
    # stays in Python so the month bucketing is identical across SQLite and
    # Postgres (no dialect-specific date functions).
    start = date(keys[0][0], keys[0][1], 1)
    data: dict[tuple[int, int], Decimal] = {}
    for txn_date, profit in session.execute(
        select(CombinedTxn.txn_date, CombinedTxn.profit)
        .where(CombinedTxn.txn_date >= start)
    ):
        key = (txn_date.year, txn_date.month)
        data[key] = data.get(key, ZERO) + profit
    return [(f"{y}-{m:02d}", money(data.get((y, m), ZERO))) for y, m in keys]


def _recent_months(months: int) -> list[tuple[int, int]]:
    today = date.today()
    year, month = today.year, today.month
    keys: list[tuple[int, int]] = []
    for _ in range(months):
        keys.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()
    return keys


def monthly_cash_flow(
    session: Session, months: int = 6
) -> list[tuple[str, Decimal, Decimal]]:
    """Money in vs out per month (label, in, out)."""
    keys = _recent_months(months)
    start = date(keys[0][0], keys[0][1], 1)
    data: dict[tuple[int, int], list[Decimal]] = {}
    for txn_date, direction, amount in session.execute(
        select(Payment.txn_date, Payment.direction, Payment.amount)
        .where(Payment.is_void.is_(False), Payment.txn_date >= start)
    ):
        slot = data.setdefault((txn_date.year, txn_date.month), [ZERO, ZERO])
        if direction == PAYMENT_IN:
            slot[0] += amount
        else:
            slot[1] += amount
    result = []
    for y, m in keys:
        inv, outv = data.get((y, m), [ZERO, ZERO])
        result.append((f"{y}-{m:02d}", money(inv), money(outv)))
    return result


def _profit_by(session: Session, attr: str, names: dict) -> list[tuple[str, Decimal]]:
    # Group + sum on the server (profit is a stored column, so SUM is exact),
    # instead of pulling every trade and its load to add up in Python.
    col = getattr(BapariTxn, attr)
    grouped = session.execute(
        select(col, func.coalesce(func.sum(CombinedTxn.profit), 0))
        .join(BapariTxn, CombinedTxn.bapari_txn_id == BapariTxn.id)
        .group_by(col)
    ).all()
    rows = [(names.get(k, NONE_LABEL), money(v)) for k, v in grouped]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def profit_by_location(session: Session) -> list[tuple[str, Decimal]]:
    names = {loc.id: loc.name for loc in session.scalars(select(Location))}
    return _profit_by(session, "location_id", names)


def profit_by_wood_type(session: Session) -> list[tuple[str, Decimal]]:
    names = {w.id: w.name for w in session.scalars(select(WoodType))}
    return _profit_by(session, "wood_type_id", names)


def top_parties(
    session: Session, party_type: str, n: int = 5
) -> list[tuple[str, Decimal]]:
    summaries = party_summaries(session, party_type)
    summaries.sort(key=lambda s: s.balance, reverse=True)
    return [(s.name, s.balance) for s in summaries[:n]]


@dataclass
class Alert:
    name: str
    party_type: str
    balance: Decimal


def outstanding_alerts(session: Session, limit: int = 10) -> list[Alert]:
    """Parties with a non-zero balance, largest first (both sides)."""
    alerts: list[Alert] = []
    for ptype in (PARTY_FACTORY, PARTY_BAPARI):
        for s in party_summaries(session, ptype):
            if s.balance != ZERO:
                alerts.append(Alert(s.name, ptype, s.balance))
    alerts.sort(key=lambda a: abs(a.balance), reverse=True)
    return alerts[:limit]
