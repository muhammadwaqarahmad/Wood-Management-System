"""Factory split sub-ledger.

Some factories pay in two streams. Each load's factory rate R is split:

* **RIGHT side** — a fixed per-factory portion S (``Party.split_rate``):
  ``weight × S``. The factory clears this side irregularly (30–60 days).
* **LEFT side** — the remaining rate: ``weight × (R − S)`` **plus the
  freight deduction** when the factory paid the driver. Cleared weekly.

The two sides always add up to the main factory ledger:
``left_net + right_amount = bill + freight = main-ledger gross``.

Payments carry ``Payment.split_side`` ("right" settles the right side;
anything else settles the left side).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.core.calculations import money
from timber.db.models import FactorySplitRate, FactoryTxn, Party, Payment, WoodType
from timber.db.models.payment import settles_debt
from timber.db.models.party import PARTY_FACTORY

ZERO = Decimal("0.00")


def split_rate_map(session: Session, factory_id: int) -> dict[int, Decimal]:
    """``{wood_type_id: split_rate}`` for a factory. A wood type absent from
    the map gets no split — its whole rate stays on the weekly (left) side."""
    rows = session.scalars(
        select(FactorySplitRate).where(FactorySplitRate.factory_id == factory_id)
    )
    return {r.wood_type_id: money(r.split_rate) for r in rows}


def traded_wood_types(session: Session, factory_id: int) -> list[tuple[int, str]]:
    """Distinct wood types this factory has actually traded (non-void loads),
    ordered by name — the woods worth setting a split rate for."""
    rows = session.execute(
        select(WoodType.id, WoodType.name)
        .join(FactoryTxn, FactoryTxn.wood_type_id == WoodType.id)
        .where(FactoryTxn.party_id == factory_id, FactoryTxn.is_void.is_(False))
        .distinct()
        .order_by(WoodType.name)
    ).all()
    return [(int(r[0]), r[1]) for r in rows]


def set_split_rates(
    session: Session, factory_id: int, rates: dict[int, Decimal]
) -> None:
    """Upsert a factory's per-wood split rates. A wood set to 0 (or below) is
    removed — 0 means 'no split, whole rate on the weekly side'. Does NOT
    commit; the caller owns the transaction."""
    existing = {
        r.wood_type_id: r
        for r in session.scalars(
            select(FactorySplitRate).where(
                FactorySplitRate.factory_id == factory_id
            )
        )
    }
    for wood_id, rate in rates.items():
        val = money(rate or 0)
        row = existing.get(wood_id)
        if val > 0:
            if row is None:
                session.add(FactorySplitRate(
                    factory_id=factory_id, wood_type_id=wood_id, split_rate=val,
                ))
            else:
                row.split_rate = val
        elif row is not None:
            session.delete(row)


@dataclass
class SplitEntry:
    txn_date: date
    kind: str                 # "load" | "payment"
    vehicle: str = ""
    wood: str = ""
    weight: Decimal = ZERO    # decimal maunds
    kg: Decimal = ZERO        # weight × 40
    # left (weekly) side
    left_rate: Decimal = ZERO
    left_total: Decimal = ZERO
    freight: Decimal = ZERO   # signed deduction (negative when factory paid)
    left_net: Decimal = ZERO
    left_payment: Decimal = ZERO
    left_balance: Decimal = ZERO
    # right (irregular) side
    right_rate: Decimal = ZERO
    right_amount: Decimal = ZERO
    right_payment: Decimal = ZERO
    right_balance: Decimal = ZERO
    detail: str = ""          # payment route (which bank → which bank / Cash)
    ref: str = ""             # payment reference no / notes
    booked_date: date | None = None  # payment ENTRY date, if it differs from
    #                                  the received date (txn_date) shown


@dataclass
class SplitStatement:
    factory_name: str
    split_rate: Decimal
    opening_left: Decimal
    opening_right: Decimal
    entries: list[SplitEntry] = field(default_factory=list)
    closing_left: Decimal = ZERO
    closing_right: Decimal = ZERO
    total_left: Decimal = ZERO     # sum of left_net (loads)
    total_right: Decimal = ZERO    # sum of right_amount (loads)
    paid_left: Decimal = ZERO
    paid_right: Decimal = ZERO

    @property
    def closing_total(self) -> Decimal:
        return money(self.closing_left + self.closing_right)


def factory_split_statement(
    session: Session,
    factory_id: int,
    start: date | None = None,
    end: date | None = None,
) -> SplitStatement:
    party = session.get(Party, factory_id)
    if party is None or party.party_type != PARTY_FACTORY:
        raise ValueError("Factory not found.")
    from timber.core.labels import payment_route

    split = money(party.split_rate or 0)  # enrolment flag / display only
    rates = split_rate_map(session, factory_id)  # per-wood split amounts

    loads = list(session.scalars(
        select(FactoryTxn).where(
            FactoryTxn.party_id == factory_id, FactoryTxn.is_void.is_(False)
        )
    ))
    payments = list(session.scalars(
        select(Payment).where(
            Payment.party_id == factory_id, Payment.is_void.is_(False),
            Payment.cheque_status.is_distinct_from("bounced"),
        )
    ))

    events: list[tuple] = []
    for t in loads:
        events.append((t.txn_date, t.created_at or datetime.min, t.id, "load", t))
    for p in payments:
        events.append((p.txn_date, p.created_at or datetime.min, p.id, "payment", p))
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    # The opening balance (pre-app carryover) lives on the weekly side.
    bal_left = money(party.opening_balance)
    bal_right = ZERO
    st = SplitStatement(
        factory_name=party.name, split_rate=split,
        opening_left=bal_left, opening_right=bal_right,
    )

    for entry_date, _order, _id, kind, obj in events:
        if kind == "load":
            bill = money(obj.bill)
            rate = money(obj.rate)
            # Split amount for THIS load's wood type. A configured wood uses its
            # own rate (0 / unconfigured → whole rate stays weekly). A legacy
            # load with NO wood type falls back to the factory's flat rate so
            # historical balances never change.
            if obj.wood_type_id is not None:
                wsplit = rates.get(obj.wood_type_id, ZERO)
            else:
                wsplit = split
            s = min(wsplit, rate) if wsplit > 0 else ZERO
            right_amt = money(obj.weight * s)
            if right_amt > bill:
                right_amt = bill
            left_total = money(bill - right_amt)
            freight = money(obj.freight)
            left_net = money(left_total + freight)
            bal_left = money(bal_left + left_net)
            bal_right = money(bal_right + right_amt)
            entry = SplitEntry(
                txn_date=entry_date, kind="load",
                vehicle=obj.vehicle_no or "",
                wood=obj.wood_type.name if obj.wood_type else "",
                weight=money(obj.weight), kg=money(obj.weight * 40),
                left_rate=money(rate - s), left_total=left_total,
                freight=freight, left_net=left_net,
                right_rate=s, right_amount=right_amt,
                left_balance=bal_left, right_balance=bal_right,
                # Trade entry date = the day it was booked (auto). Shown beneath
                # the actual trade date when they differ (e.g. a late-entered load).
                booked_date=obj.created_at.date() if obj.created_at else None,
            )
        else:
            # A refund to the factory (direction "out") is money going back, so
            # it RAISES what they owe. Carried as a negative payment so the
            # side balances and the period totals stay consistent.
            amt = money(obj.amount)
            if not settles_debt(party.party_type, obj.direction):
                amt = -amt
            side_right = (obj.split_side or "left") == "right"
            if side_right:
                bal_right = money(bal_right - amt)
            else:
                bal_left = money(bal_left - amt)
            entry = SplitEntry(
                txn_date=entry_date, kind="payment",
                left_payment=ZERO if side_right else amt,
                right_payment=amt if side_right else ZERO,
                left_balance=bal_left, right_balance=bal_right,
                detail=payment_route(obj, party.name),
                ref=" ".join(x for x in (obj.reference_no, obj.notes) if x),
                booked_date=obj.entry_date,
            )

        in_range = (start is None or entry_date >= start) and (
            end is None or entry_date <= end
        )
        if start is not None and entry_date < start:
            st.opening_left, st.opening_right = bal_left, bal_right
            continue
        if not in_range:
            continue
        st.entries.append(entry)
        # Totals cover only the rows shown (the selected period).
        if kind == "load":
            st.total_left = money(st.total_left + entry.left_net)
            st.total_right = money(st.total_right + entry.right_amount)
        else:
            st.paid_left = money(st.paid_left + entry.left_payment)
            st.paid_right = money(st.paid_right + entry.right_payment)

    st.closing_left, st.closing_right = bal_left, bal_right
    return st
