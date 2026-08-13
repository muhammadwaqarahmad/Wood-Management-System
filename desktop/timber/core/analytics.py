"""Business analytics: margins, best/worst by dimension, trends,
expense breakdown, party scorecards, and the dashboard action panel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from timber.core.calculations import money
from timber.db.models import (
    BapariTxn,
    CombinedTxn,
    Expense,
    FactoryTxn,
    Party,
    Payment,
    PaymentAllocation,
)
from timber.db.models.combined_txn import PAYER_US

ZERO = Decimal("0.00")


def _txn_loads():
    """Eager-load both legs of a trade (+ their party / wood / location) so the
    analytics loops don't issue a query per row (N+1) when there's real data."""
    return (
        joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.party),
        joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.wood_type),
        joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.location),
        joinedload(CombinedTxn.factory_txn).joinedload(FactoryTxn.party),
    )


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return money(part / whole * 100) if whole else ZERO


# --- overall + by-dimension profit ----------------------------------
@dataclass
class ProfitSummary:
    sales: Decimal
    purchases: Decimal
    own_expense: Decimal
    profit: Decimal
    margin_pct: Decimal


def profit_summary(session: Session) -> ProfitSummary:
    sales = purchases = own = profit = ZERO
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads())):
        sales += c.factory_txn.net_amount
        purchases += c.bapari_txn.net_amount
        own += c.own_expense
        profit += c.profit
    return ProfitSummary(
        money(sales), money(purchases), money(own), money(profit), _pct(profit, sales)
    )


@dataclass
class DimRow:
    name: str
    count: int
    muds: Decimal
    sales: Decimal
    profit: Decimal
    margin_pct: Decimal


def profit_by(session: Session, dim: str) -> list[DimRow]:
    """dim in {'factory','bapari','wood','location'} — sorted best first."""
    agg: dict = {}
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads())):
        b, f = c.bapari_txn, c.factory_txn
        if dim == "factory":
            key, name, muds = f.party_id, f.party.name, f.muds
        elif dim == "bapari":
            key, name, muds = b.party_id, b.party.name, b.muds
        elif dim == "wood":
            key = b.wood_type_id
            name = b.wood_type.name if b.wood_type else "—"
            muds = b.muds
        else:  # location
            key = b.location_id
            name = b.location.name if b.location else "—"
            muds = b.muds
        d = agg.setdefault(key, [name, 0, ZERO, ZERO, ZERO])
        d[1] += 1
        d[2] += muds
        d[3] += f.net_amount
        d[4] += c.profit
    rows = [
        DimRow(d[0], d[1], money(d[2]), money(d[3]), money(d[4]), _pct(d[4], d[3]))
        for d in agg.values()
    ]
    rows.sort(key=lambda r: r.profit, reverse=True)
    return rows


# --- trends over time -----------------------------------------------
def _recent_months(months: int) -> list[tuple[int, int]]:
    today = date.today()
    y, m = today.year, today.month
    keys = []
    for _ in range(months):
        keys.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    keys.reverse()
    return keys


@dataclass
class TrendRow:
    label: str
    profit: Decimal
    muds: Decimal
    sales: Decimal
    expense_ratio: Decimal  # own expense as % of sales


def monthly_trends(session: Session, months: int = 6) -> list[TrendRow]:
    data: dict = {}
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads())):
        key = (c.txn_date.year, c.txn_date.month)
        d = data.setdefault(key, [ZERO, ZERO, ZERO, ZERO])
        d[0] += c.profit
        d[1] += c.factory_txn.muds
        d[2] += c.factory_txn.net_amount
        d[3] += c.own_expense
    rows = []
    for y, m in _recent_months(months):
        profit, muds, sales, own = data.get((y, m), [ZERO, ZERO, ZERO, ZERO])
        rows.append(
            TrendRow(f"{y}-{m:02d}", money(profit), money(muds), money(sales),
                     _pct(own, sales))
        )
    return rows


# --- expense breakdown ----------------------------------------------
@dataclass
class ExpenseShare:
    category: str
    amount: Decimal
    pct_of_margin: Decimal


def expense_breakdown(session: Session) -> list[ExpenseShare]:
    """Operational expenses + our own per-load charges, each as a % of
    gross margin (sales − purchases)."""
    cats: dict[str, Decimal] = {}
    for e in session.scalars(select(Expense).where(Expense.is_void.is_(False))):
        cats[e.category] = cats.get(e.category, ZERO) + e.amount

    gross = ZERO
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads())):
        gross += c.factory_txn.net_amount - c.bapari_txn.net_amount
        if c.loading_payer == PAYER_US:
            cats["loading"] = cats.get("loading", ZERO) + c.loading_amount
        if c.freight_payer == PAYER_US:
            cats["freight"] = cats.get("freight", ZERO) + c.freight_amount
        if c.unloading_payer == PAYER_US:
            cats["unloading"] = cats.get("unloading", ZERO) + c.unloading_amount

    rows = [
        ExpenseShare(cat, money(amt), _pct(amt, gross))
        for cat, amt in cats.items() if amt > 0
    ]
    rows.sort(key=lambda r: r.amount, reverse=True)
    return rows


# --- scorecards ------------------------------------------------------
@dataclass
class Scorecard:
    name: str
    loads: int
    muds: Decimal
    value: Decimal       # sales (factory) or purchases (bapari)
    profit: Decimal
    balance: Decimal     # receivable / payable
    avg_delay_days: int  # avg days between load and its payments
    collected_pct: Decimal


def _scorecards(session: Session, party_type: str) -> list[Scorecard]:
    from timber.core.ledger import all_party_balances
    from timber.core.payment_service import party_outstanding_loads

    is_factory = party_type == "factory"
    kind = "factory" if is_factory else "bapari"

    # ONE pass over all trades -> per-party totals. This used to re-scan the
    # WHOLE CombinedTxn table once PER party (an N x M scan that got very slow
    # with real trade history); now it's a single grouped scan.
    agg: dict[int, list] = {}
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads())):
        txn = c.factory_txn if is_factory else c.bapari_txn
        if txn is None:
            continue
        tot4 = agg.setdefault(txn.party_id, [0, ZERO, ZERO, ZERO])
        tot4[0] += 1
        tot4[1] += txn.muds
        tot4[2] += txn.net_amount
        tot4[3] += c.profit

    balances = all_party_balances(session)  # one batched pass, not per party
    rows: list[Scorecard] = []
    for p in session.scalars(
        select(Party).where(Party.party_type == party_type, Party.is_active.is_(True))
    ):
        loads = party_outstanding_loads(session, p.id)  # all loads (paid+unpaid)
        if not loads:
            continue
        billed = sum((o.amount for o in loads), ZERO)
        paid = sum((o.paid for o in loads), ZERO)
        load_dates = {o.txn_id: o.txn_date for o in loads}

        count, muds, value, profit = agg.get(p.id, [0, ZERO, ZERO, ZERO])

        # weighted avg payment delay
        tot_wt = tot = ZERO
        for a in session.scalars(
            select(PaymentAllocation).where(
                PaymentAllocation.kind == kind,
                PaymentAllocation.txn_id.in_(load_dates.keys()),
            )
        ):
            pay = session.get(Payment, a.payment_id)
            if pay is None or pay.is_void:
                continue
            tot += (pay.txn_date - load_dates[a.txn_id]).days * a.amount
            tot_wt += a.amount
        avg_delay = int(tot / tot_wt) if tot_wt else 0

        rows.append(
            Scorecard(
                p.name, count, money(muds), money(value), money(profit),
                balances.get(p.id, ZERO),
                avg_delay, _pct(paid, billed),
            )
        )
    rows.sort(key=lambda r: r.profit, reverse=True)
    return rows


def factory_scorecards(session: Session) -> list[Scorecard]:
    return _scorecards(session, "factory")


def bapari_scorecards(session: Session) -> list[Scorecard]:
    return _scorecards(session, "bapari")


# --- dashboard action panel -----------------------------------------
@dataclass
class ActionPanel:
    today_profit: Decimal
    overdue_total: Decimal
    advances_total: Decimal
    cash_position: Decimal
    low_accounts: list[tuple[str, Decimal]]  # accounts with negative balance


def action_panel(session: Session) -> ActionPanel:
    from timber.core.bank_service import all_balances, total_cash_position
    from timber.core.reports import advance_register, overdue_report

    today = date.today()
    today_profit = ZERO
    for c in session.scalars(select(CombinedTxn).options(*_txn_loads()).where(CombinedTxn.txn_date == today)):
        today_profit += c.profit

    overdue_total = sum((r.outstanding for r in overdue_report(session)), ZERO)
    advances_total = sum((r.advance for r in advance_register(session)), ZERO)
    low = [(b.name, b.closing) for b in all_balances(session) if b.closing < 0]
    return ActionPanel(
        money(today_profit), money(overdue_total), money(advances_total),
        total_cash_position(session), low,
    )
