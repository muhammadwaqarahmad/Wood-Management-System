"""Dashboard summary — one call that gathers everything the dashboard
shows for a period: balance-sheet positions (banks, cash, receivable,
payable, loans) plus the flows inside the range (sales, purchases, profit,
business/house expenses) and a bucketed series for charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from timber.core import bank_service, expense_service, loan_service
from timber.core.calculations import money
from timber.core.ledger import receivable_and_payable
from timber.core.reports import list_trades

ZERO = Decimal("0.00")


@dataclass
class SeriesPoint:
    label: str          # bucket label: 2026-07-04 / 2026-07 / 2026
    sales: Decimal
    purchases: Decimal
    profit: Decimal
    expenses: Decimal   # business + house within the bucket


def _bucket(day: date, mode: str) -> str:
    if mode == "day":
        return day.isoformat()
    if mode == "month":
        return f"{day.year:04d}-{day.month:02d}"
    return f"{day.year:04d}"


def _bucket_mode(start: date | None, end: date | None) -> str:
    """Choose the chart granularity from the span: daily up to ~2 months,
    monthly up to ~2 years, yearly beyond."""
    if start is None or end is None:
        return "month"
    span = (end - start).days
    if span <= 62:
        return "day"
    if span <= 750:
        return "month"
    return "year"


def dashboard_summary(
    session: Session, start: date | None = None, end: date | None = None
) -> dict:
    # --- balance-sheet positions (as of now) -------------------------
    receivable, payable = receivable_and_payable(session)  # one balance pass
    balances = bank_service.all_balances(session)
    cash = money(sum((b.closing for b in balances if b.is_cash), ZERO))
    bank_total = money(sum((b.closing for b in balances if not b.is_cash), ZERO))
    available = money(bank_total + cash)
    # Money already in the bank but not yet attributed to a party. It is a
    # subset of the balances above, shown separately so it stays visible.
    from timber.core.unknown_payment_service import total_unknown

    unclaimed = total_unknown(session)
    from timber.db.models.loan import LOAN_GIVEN

    loans_out = loan_service.total_loans_outstanding(session)          # we owe
    loans_given = loan_service.total_loans_outstanding(session, LOAN_GIVEN)

    # --- flows within the range --------------------------------------
    trades = list_trades(session, start, end)
    sales = money(sum((t.sale_bill for t in trades), ZERO))
    purchases = money(sum((t.purchase_bill for t in trades), ZERO))
    profit = money(sum((t.profit for t in trades), ZERO))
    exp_business = expense_service.total_expenses(
        session, operating_only=True, kind="business", start=start, end=end
    )
    exp_house = expense_service.total_expenses(
        session, operating_only=True, kind="house", start=start, end=end
    )

    # Net position: what we have + what we'll receive (incl. loans we gave
    # out) − what we must give (incl. loans we took).
    net_worth = money(available + receivable + loans_given - payable - loans_out)

    # --- chart series --------------------------------------------------
    mode = _bucket_mode(
        start or (min((t.txn_date for t in trades), default=None)),
        end or (max((t.txn_date for t in trades), default=None)),
    )
    buckets: dict[str, SeriesPoint] = {}

    def _point(label: str) -> SeriesPoint:
        if label not in buckets:
            buckets[label] = SeriesPoint(label, ZERO, ZERO, ZERO, ZERO)
        return buckets[label]

    for t in trades:
        p = _point(_bucket(t.txn_date, mode))
        p.sales = money(p.sales + t.sale_bill)
        p.purchases = money(p.purchases + t.purchase_bill)
        p.profit = money(p.profit + t.profit)
    for row in expense_service.list_expenses(
        session, limit=100000, start=start, end=end
    ):
        p = _point(_bucket(row.txn_date, mode))
        p.expenses = money(p.expenses + row.amount)

    series = [buckets[k] for k in sorted(buckets)]

    # --- the plus/minus summary table ---------------------------------
    # sign: +1 = adds to our position, -1 = reduces it, 0 = subtotal/result.
    table = [
        {"key": "banks", "amount": float(bank_total), "sign": 1},
        {"key": "cash", "amount": float(cash), "sign": 1},
        {"key": "receivable", "amount": float(receivable), "sign": 1},
        {"key": "loans_given", "amount": float(loans_given), "sign": 1},
        {"key": "payable", "amount": float(payable), "sign": -1},
        {"key": "loans", "amount": float(loans_out), "sign": -1},
        {"key": "net_worth", "amount": float(net_worth), "sign": 0},
    ]

    return {
        "cards": {
            "sales": float(sales),
            "purchases": float(purchases),
            "profit": float(profit),
            "trades": len(trades),
            "expBusiness": float(exp_business),
            "expHouse": float(exp_house),
            "expTotal": float(money(exp_business + exp_house)),
            "receivable": float(receivable),
            "payable": float(-payable),         # display rule: to give = negative
            "loans": float(-loans_out),          # we must repay = negative
            "loansGiven": float(loans_given),    # they owe us = positive
            "bankTotal": float(bank_total),
            "cash": float(cash),
            "available": float(available),
            "unclaimed": float(unclaimed),      # unattributed, subset of banks
            "netProfit": float(money(profit - exp_business)),
            "netWorth": float(net_worth),
        },
        "table": table,
        "series": [
            {
                "label": p.label,
                "sales": float(p.sales),
                "purchases": float(p.purchases),
                "profit": float(p.profit),
                "expenses": float(p.expenses),
            }
            for p in series
        ],
        "banks": [
            {"name": b.name, "balance": float(b.closing)} for b in balances
        ],
        "bucket": mode,
    }
