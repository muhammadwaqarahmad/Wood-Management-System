"""Weekly settlement for a factory's WEEKLY (left) side.

The client clears the weekly side week by week. Each month is split into
weeks by day-of-month — 1–7, 8–14, 15–21, 22–end. For each week:

    carried_out = carried_in + charged − paid

where ``charged`` is the weekly-side value of loads received that week and
``paid`` is the weekly-side payments received that week (placed by their
RECEIVED date). Any unpaid balance rolls into the next week's ``carried_in``.

Built on :func:`factory_split_statement` so the weekly numbers always
reconcile with the sub-ledger's weekly side (per-wood split + freight).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from timber.core.calculations import money
from timber.core.split_ledger import factory_split_statement

ZERO = Decimal("0.00")


@dataclass
class WeekRow:
    start: date
    end: date
    carried_in: Decimal
    charged: Decimal
    paid: Decimal
    carried_out: Decimal

    @property
    def label(self) -> str:
        return f"{self.start.day}–{self.end.day}"


@dataclass
class WeeklySettlement:
    factory_name: str
    year: int
    month: int
    opening: Decimal                       # weekly balance carried INTO the month
    weeks: list[WeekRow] = field(default_factory=list)
    closing: Decimal = ZERO                # carried out of the last week
    total_charged: Decimal = ZERO
    total_paid: Decimal = ZERO


def _week_bounds(year: int, month: int) -> list[tuple[date, date]]:
    """The four day-of-month weeks for a month (last one runs to month end)."""
    last = calendar.monthrange(year, month)[1]
    spans = [(1, 7), (8, 14), (15, 21), (22, last)]
    return [(date(year, month, a), date(year, month, b)) for a, b in spans]


def week_label(d: date) -> str:
    """The day-of-month week a date falls in, e.g. "1–7", "8–14", "22–31"."""
    for a, b in _week_bounds(d.year, d.month):
        if a <= d <= b:
            return f"{a.day}–{b.day}"
    return ""


def weekly_settlement(
    session: Session, factory_id: int, year: int, month: int
) -> WeeklySettlement:
    st = factory_split_statement(session, factory_id)  # all-time, left side
    bounds = _week_bounds(year, month)
    month_start, month_end = bounds[0][0], bounds[-1][1]

    # Weekly balance carried INTO the month = pre-app opening (sits on the left)
    # plus the net weekly movement of everything dated before the month.
    opening = money(st.opening_left)
    charged = [ZERO] * len(bounds)
    paid = [ZERO] * len(bounds)
    for e in st.entries:
        if e.txn_date < month_start:
            if e.kind == "load":
                opening = money(opening + e.left_net)
            else:
                opening = money(opening - e.left_payment)
            continue
        if e.txn_date > month_end:
            continue
        for i, (a, b) in enumerate(bounds):
            if a <= e.txn_date <= b:
                if e.kind == "load":
                    charged[i] = money(charged[i] + e.left_net)
                else:
                    paid[i] = money(paid[i] + e.left_payment)
                break

    weeks: list[WeekRow] = []
    carry = opening
    for i, (a, b) in enumerate(bounds):
        carried_out = money(carry + charged[i] - paid[i])
        weeks.append(WeekRow(a, b, carry, charged[i], paid[i], carried_out))
        carry = carried_out

    return WeeklySettlement(
        factory_name=st.factory_name, year=year, month=month,
        opening=opening, weeks=weeks, closing=carry,
        total_charged=money(sum(charged, ZERO)),
        total_paid=money(sum(paid, ZERO)),
    )
