"""Ledgers and balances.

Builds a party's running-balance statement and the firm-wide position:

    running balance = previous + (bill + freight) − payments
    total payable    = sum of all bapari balances   (we owe them)
    total receivable = sum of all factory balances   (they owe us)
    net position     = receivable − payable
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, select
from sqlalchemy.orm import Session, joinedload

from timber.core.calculations import balance_amount, money
from timber.db.models import BapariTxn, FactoryTxn, Party, Payment
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import (
    PAYMENT_IN,
    PAYMENT_OUT,
    natural_direction,
    settles_debt,
)

ZERO = Decimal("0.00")


def _settling_amount(party_type: str):
    """SQL: +amount when the payment settles the party, -amount when it
    refunds. Lets a balance be one SUM instead of two."""
    return case(
        (Payment.direction == natural_direction(party_type), Payment.amount),
        else_=-Payment.amount,
    )


def _settling_amount_joined():
    """Same expression across ALL parties at once — needs `parties` joined, as
    whether a row settles depends on the party's type as well as its
    direction."""
    return case(
        (and_(Party.party_type == PARTY_BAPARI,
              Payment.direction == PAYMENT_OUT), Payment.amount),
        (and_(Party.party_type != PARTY_BAPARI,
              Payment.direction == PAYMENT_IN), Payment.amount),
        else_=-Payment.amount,
    )


@dataclass
class LedgerEntry:
    """One line in a party statement."""

    entry_date: date
    kind: str          # "txn" | "payment"
    ref_id: int
    description: str
    debit: Decimal     # increases the balance (a load)
    credit: Decimal    # decreases the balance (a payment)
    balance: Decimal   # running balance after this line


@dataclass
class PartyLedger:
    party: Party
    entries: list[LedgerEntry]
    opening_balance: Decimal
    closing_balance: Decimal


def _active_txns(session: Session, party: Party):
    """Return this party's non-void transactions (bapari or factory)."""
    model = BapariTxn if party.party_type == PARTY_BAPARI else FactoryTxn
    return list(
        session.scalars(
            select(model).where(
                model.party_id == party.id, model.is_void.is_(False)
            )
        )
    )


def build_party_ledger(session: Session, party_id: int) -> PartyLedger:
    """Build a chronological running-balance statement for one party."""
    party = session.get(Party, party_id)
    if party is None:
        raise ValueError(f"No party with id={party_id}")

    txns = _active_txns(session, party)
    payments = list(
        session.scalars(
            select(Payment).where(
                Payment.party_id == party_id, Payment.is_void.is_(False),
                Payment.cheque_status.is_distinct_from("bounced"),  # exclude bounced (NULL-safe)
            )
        )
    )

    # Merge loads (debits) and payments (credits) into one timeline.
    # Sort by date, then put loads before payments on the same day,
    # then by id for a stable order.
    events: list[tuple[date, int, str, int, Decimal, Decimal]] = []
    for t in txns:
        events.append(
            (t.txn_date, 0, "txn", t.id, balance_amount(t.bill, t.freight), ZERO)
        )
    # A payment in the party's natural direction is a credit (it settles what
    # is owed). One against it — a supplier refunding us, us refunding a
    # factory — is a debit: it puts the money back on the balance.
    for p in payments:
        if settles_debt(party.party_type, p.direction):
            events.append((p.txn_date, 1, "payment", p.id, ZERO, money(p.amount)))
        else:
            events.append((p.txn_date, 1, "payment", p.id, money(p.amount), ZERO))
    events.sort(key=lambda e: (e[0], e[1], e[3]))

    opening = money(party.opening_balance)
    running = opening
    entries: list[LedgerEntry] = []
    for entry_date, _order, kind, ref_id, debit, credit in events:
        running = money(running + debit - credit)
        description = (
            f"Load #{ref_id}" if kind == "txn" else f"Payment #{ref_id}"
        )
        entries.append(
            LedgerEntry(entry_date, kind, ref_id, description, debit, credit, running)
        )

    return PartyLedger(party, entries, opening, running)


def party_balance(session: Session, party_id: int) -> Decimal:
    """Closing balance for a single party — two SUM queries, no row
    hydration (build_party_ledger walks every row and gets slow after a
    year of entries; use it only when the entry list itself is needed)."""
    from sqlalchemy import func

    party = session.get(Party, party_id)
    if party is None:
        raise ValueError(f"No party with id={party_id}")
    model = BapariTxn if party.party_type == PARTY_BAPARI else FactoryTxn
    loads = session.scalar(
        select(func.coalesce(func.sum(model.bill + model.freight), 0)).where(
            model.party_id == party_id, model.is_void.is_(False)
        )
    )
    # Net settling money: natural-direction payments count positive, reverse
    # ones (refunds) negative, so a refund raises the balance again.
    paid = session.scalar(
        select(func.coalesce(func.sum(_settling_amount(party.party_type)), 0)).where(
            Payment.party_id == party_id, Payment.is_void.is_(False),
            Payment.cheque_status.is_distinct_from("bounced"),
        )
    )
    return money(money(party.opening_balance) + money(loads or 0) - money(paid or 0))


def all_party_balances(session: Session) -> dict[int, Decimal]:
    """Closing balance of EVERY party in 4 aggregate queries instead of ~3
    per party. Same math as :func:`party_balance`, grouped server-side — this
    is what the Position / Dashboard / Reports pages use, so they load in a
    few round-trips rather than a few hundred on a networked PostgreSQL."""
    from sqlalchemy import func

    bal: dict[int, Decimal] = {}
    for pid, opening in session.execute(
        select(Party.id, Party.opening_balance)
    ):
        bal[pid] = money(opening or 0)

    # Loads: a bapari's are in BapariTxn, a factory's in FactoryTxn. Party ids
    # are unique, so a party only shows up under its own table.
    for model in (BapariTxn, FactoryTxn):
        for pid, total in session.execute(
            select(model.party_id, func.coalesce(func.sum(model.bill + model.freight), 0))
            .where(model.is_void.is_(False))
            .group_by(model.party_id)
        ):
            if pid in bal:
                bal[pid] += money(total or 0)

    # Joined to `parties` because a payment only counts as settling when its
    # direction matches that party type's natural one.
    for pid, total in session.execute(
        select(Payment.party_id,
               func.coalesce(func.sum(_settling_amount_joined()), 0))
        .join(Party, Payment.party_id == Party.id)
        .where(
            Payment.is_void.is_(False),
            Payment.cheque_status.is_distinct_from("bounced"),
        )
        .group_by(Payment.party_id)
    ):
        if pid in bal:
            bal[pid] -= money(total or 0)

    return {pid: money(v) for pid, v in bal.items()}


# --- detailed statement (rich rows for the ledger screens) -----------
@dataclass
class DetailedEntry:
    entry_date: date
    kind: str            # "load" | "payment"
    ref_id: int
    vehicle: str
    wood: str
    weight_text: str
    rate: Decimal
    amount: Decimal      # load gross (bill+freight) or payment amount
    paid: Decimal        # how much of a load is paid (loads only)
    outstanding: Decimal
    status: str          # paid / partial / unpaid  (loads); method (payments)
    debit: Decimal
    credit: Decimal
    balance: Decimal
    expenses: str = ""       # who paid loading/freight/unloading (loads only)
    counterparty: str = ""   # the other side (factory on a supplier ledger, etc.)
    total: Decimal = ZERO    # gross wood value (weight × rate, before freight)
    freight: Decimal = ZERO  # freight adjustment on the load
    payment_detail: str = "" # bank route for payments (from/to which account)


@dataclass
class DetailedStatement:
    party: Party
    party_type: str
    entries: list[DetailedEntry]
    opening: Decimal
    closing: Decimal
    total_loads: Decimal     # sum of debits in range
    total_paid: Decimal      # sum of credits in range


def detailed_party_statement(
    session: Session,
    party_id: int,
    start: date | None = None,
    end: date | None = None,
) -> DetailedStatement:
    """Per-party statement enriched with vehicle, wood, weight, rate, bill
    and per-load payment status, plus a running balance."""
    from timber import i18n
    from timber.core.labels import payment_route
    from timber.core.payment_service import allocated_by_load
    from timber.db.models import CombinedTxn
    from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY

    party = session.get(Party, party_id)
    if party is None:
        raise ValueError(f"No party with id={party_id}")
    kind = "bapari" if party.party_type == PARTY_BAPARI else "factory"
    model = BapariTxn if party.party_type == PARTY_BAPARI else FactoryTxn

    from sqlalchemy.orm import joinedload

    txns = list(
        session.scalars(
            select(model)
            .options(joinedload(model.wood_type))
            .where(model.party_id == party_id, model.is_void.is_(False))
        )
    )

    # Map each load to its truck so we can show who paid the expenses.
    # Eager-load both sides + their parties: the loop below reads them for
    # every row, and lazy loads would mean thousands of queries per view.
    load_ids = [t.id for t in txns]
    combined_map: dict[int, CombinedTxn] = {}
    if load_ids:
        fk = CombinedTxn.factory_txn_id if kind == "factory" else CombinedTxn.bapari_txn_id
        combined_q = (
            select(CombinedTxn)
            .options(
                joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.party),
                joinedload(CombinedTxn.factory_txn).joinedload(FactoryTxn.party),
            )
            .where(fk.in_(load_ids))
        )
        for c in session.scalars(combined_q):
            combined_map[c.factory_txn_id if kind == "factory" else c.bapari_txn_id] = c

    # In a party's own ledger the expense column shows ONLY the freight /
    # loading / unloading that THIS party actually paid — the amount the
    # supplier paid appears on the supplier ledger, the factory's on the
    # factory ledger, ours on neither. (Trade History still lists them all.)
    my_payer = PAYER_BAPARI if kind == "bapari" else PAYER_FACTORY

    def _payer_share(amt, p1, p2, sp) -> Decimal:
        amt = money(amt or 0)
        if amt <= 0:
            return ZERO
        split = money(sp or 0)
        if p2 and ZERO < split < amt:  # a split charge — each payer bears a part
            if p1 == my_payer:
                return split
            if p2 == my_payer:
                return money(amt - split)
            return ZERO
        return amt if p1 == my_payer else ZERO

    def _expenses_for(load_id: int) -> str:
        c = combined_map.get(load_id)
        if c is None:
            return ""
        parts = []
        for amt, p1, p2, sp, key in (
            (c.loading_amount, c.loading_payer, c.loading_payer2, c.loading_split, "loading"),
            (c.freight_amount, c.freight_payer, c.freight_payer2, c.freight_split, "freight"),
            (c.unloading_amount, c.unloading_payer, c.unloading_payer2, c.unloading_split, "unloading"),
        ):
            share = _payer_share(amt, p1, p2, sp)
            if share > 0:
                parts.append(f"{i18n.tr(key)}: {share:,.2f}")
        return "\n".join(parts)

    def _counterparty_for(load_id: int) -> str:
        c = combined_map.get(load_id)
        if c is None:
            return ""
        # On a supplier ledger show the factory; on a factory ledger the supplier.
        if kind == "factory":
            other = c.bapari_txn.party if c.bapari_txn and c.bapari_txn.party else None
        else:
            other = c.factory_txn.party if c.factory_txn and c.factory_txn.party else None
        return other.name if other else ""
    payments = list(
        session.scalars(
            select(Payment)
            # payment_route() reads both of these for every payment row; left
            # lazy they were one query each (28 extra round trips on a busy
            # factory ledger).
            .options(
                joinedload(Payment.bank_account),
                joinedload(Payment.party_bank),
            )
            .where(
                Payment.party_id == party_id, Payment.is_void.is_(False),
                Payment.cheque_status.is_distinct_from("bounced"),
            )
        )
    )

    # Order by the business date, then by the order things were actually
    # entered (created_at) — NOT loads-before-payments — so the running
    # balance follows the real sequence (e.g. a payment then a truck on the
    # same day reads in that order).
    from datetime import datetime as _dt

    events: list[tuple] = []
    for t in txns:
        events.append((t.txn_date, t.created_at or _dt.min, t.id, "load", t))
    for p in payments:
        events.append((p.txn_date, p.created_at or _dt.min, p.id, "payment", p))
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    # Paid-per-load for every load in ONE grouped query (per-load queries
    # make a year-long ledger take seconds).
    paid_map = allocated_by_load(session, kind, [t.id for t in txns])

    # THE universal display rule: money we must GIVE shows negative, money we
    # will RECEIVE shows positive. For a supplier that means -(internal): we
    # owe them -> negative. For a factory it means +(internal): they owe us ->
    # positive. We track the internal "what we owe" running balance and apply
    # this sign when displaying.
    disp_sign = -1 if kind == "bapari" else 1
    internal = money(party.opening_balance)
    running = money(disp_sign * internal)
    opening = running
    entries: list[DetailedEntry] = []
    total_loads = total_paid = ZERO
    for entry_date, _order, ref_id, ekind, obj in events:
        if ekind == "load":
            gross = balance_amount(obj.bill, obj.freight)
            debit, credit = gross, ZERO
        else:
            debit, credit = ZERO, money(obj.amount)
        internal = money(internal + debit - credit)
        running = money(disp_sign * internal)

        in_range = (start is None or entry_date >= start) and (
            end is None or entry_date <= end
        )
        if start is not None and entry_date < start:
            opening = running  # fold pre-range activity into the opening
            continue
        if not in_range:
            continue

        if ekind == "load":
            paid = paid_map.get(obj.id, ZERO)
            outstanding = money(gross - paid)
            if outstanding <= 0:
                status = "paid"
            elif paid > 0:
                status = "partial"
            else:
                status = "unpaid"
            entries.append(DetailedEntry(
                entry_date, "load", ref_id,
                obj.vehicle_no or "",
                obj.wood_type.name if obj.wood_type else "",
                f"{obj.weight:,.2f}",   # decimal maunds
                money(obj.rate), gross, paid, outstanding, status,
                debit, credit, running, _expenses_for(obj.id),
                _counterparty_for(obj.id), money(obj.bill), money(obj.freight),
            ))
            total_loads += debit
        else:
            entries.append(DetailedEntry(
                entry_date, "payment", ref_id,
                "", "", "", ZERO, money(obj.amount), ZERO, ZERO,
                obj.method, debit, credit, running,
                payment_detail=payment_route(obj, party.name),
            ))
            total_paid += credit

    # Chronological order: oldest first, newest at the bottom.
    return DetailedStatement(
        party, party.party_type, entries, money(opening), running,
        money(total_loads), money(total_paid),
    )


def _sum_balances(session: Session, party_type: str) -> Decimal:
    ids = session.scalars(
        select(Party.id).where(
            Party.party_type == party_type, Party.is_active.is_(True)
        )
    ).all()
    balances = all_party_balances(session)
    return money(sum((balances.get(pid, ZERO) for pid in ids), ZERO))


def total_payable(session: Session) -> Decimal:
    """Sum of all bapari balances — what we owe suppliers."""
    return _sum_balances(session, PARTY_BAPARI)


def total_receivable(session: Session) -> Decimal:
    """Sum of all factory balances — what buyers owe us."""
    return _sum_balances(session, PARTY_FACTORY)


def receivable_and_payable(session: Session) -> tuple[Decimal, Decimal]:
    """Total receivable (active factories) and payable (active baparis) from a
    SINGLE balance pass. ``total_receivable`` and ``total_payable`` each run
    ``all_party_balances`` (4 aggregate queries), so a caller that needs both
    (dashboard, cash-flow) would pay that pass twice. Computing them together
    halves those round-trips — decisive on a networked/cloud database."""
    balances = all_party_balances(session)
    receivable = payable = ZERO
    for pid, ptype in session.execute(
        select(Party.id, Party.party_type).where(Party.is_active.is_(True))
    ):
        if ptype == PARTY_FACTORY:
            receivable += balances.get(pid, ZERO)
        elif ptype == PARTY_BAPARI:
            payable += balances.get(pid, ZERO)
    return money(receivable), money(payable)


def net_position(session: Session) -> Decimal:
    """Receivable − payable."""
    receivable, payable = receivable_and_payable(session)
    return money(receivable - payable)
