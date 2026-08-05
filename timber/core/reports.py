"""Aggregations for the ledger/report screens.

All functions are read-only, take a Session, and return lightweight
dataclasses resolved while the session is open (no detached-instance
errors). The per-party running statement lives in ``ledger.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from timber.core.calculations import balance_amount, money
from timber.core.ledger import (
    all_party_balances,
    build_party_ledger,
    total_payable,
    total_receivable,
)
from timber.db.models import (
    BapariTxn,
    CombinedTxn,
    FactoryTxn,
    Location,
    Party,
    Payment,
    WoodType,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

ZERO = Decimal("0.00")
NONE_LABEL = "—"


# --- party summaries (payables / receivables) ------------------------
@dataclass
class PartySummary:
    party_id: int
    name: str
    balance: Decimal


def overdue_factory_ids(session: Session) -> set[int]:
    """Factory ids whose oldest unpaid sale is older than their credit
    period (they're holding our money too long).
    """
    from datetime import date

    today = date.today()
    overdue: set[int] = set()
    factories = session.scalars(
        select(Party).where(
            Party.party_type == PARTY_FACTORY,
            Party.is_active.is_(True),
            Party.credit_days.is_not(None),
        )
    )
    balances = all_party_balances(session)
    # Oldest sale date for EVERY factory in one grouped query. Asking per
    # factory was an N+1 that ran on every Master Data / Overdue / Aging open.
    oldest_by_party = dict(
        session.execute(
            select(FactoryTxn.party_id, func.min(FactoryTxn.txn_date))
            .where(FactoryTxn.is_void.is_(False))
            .group_by(FactoryTxn.party_id)
        ).all()
    )
    for f in factories:
        if balances.get(f.id, ZERO) <= ZERO:
            continue
        oldest = oldest_by_party.get(f.id)
        if oldest and (today - oldest).days > (f.credit_days or 0):
            overdue.add(f.id)
    return overdue


@dataclass
class OverdueFactory:
    party_id: int
    name: str
    outstanding: Decimal
    oldest_date: date
    days_outstanding: int
    credit_days: int
    days_overdue: int


def overdue_report(session: Session) -> list[OverdueFactory]:
    """Factories whose oldest unpaid sale is past their credit period."""
    from datetime import date as _date

    from timber.core.payment_service import party_outstanding_loads

    today = _date.today()
    rows: list[OverdueFactory] = []
    factories = session.scalars(
        select(Party).where(
            Party.party_type == PARTY_FACTORY,
            Party.is_active.is_(True),
            Party.credit_days.is_not(None),
        )
    )
    for f in factories:
        unpaid = [o for o in party_outstanding_loads(session, f.id) if o.outstanding > 0]
        if not unpaid:
            continue
        oldest = min(o.txn_date for o in unpaid)
        days_out = (today - oldest).days
        if days_out > (f.credit_days or 0):
            rows.append(
                OverdueFactory(
                    f.id, f.name,
                    money(sum(o.outstanding for o in unpaid)),
                    oldest, days_out, f.credit_days, days_out - f.credit_days,
                )
            )
    rows.sort(key=lambda r: r.days_overdue, reverse=True)
    return rows


@dataclass
class AgingRow:
    name: str
    b0_30: Decimal
    b31_60: Decimal
    b61_90: Decimal
    b90p: Decimal
    total: Decimal


def aging_report(session: Session) -> list[AgingRow]:
    """Factory receivables split into age buckets (by load date)."""
    from timber.core.payment_service import all_parties_outstanding_loads

    # Every factory's loads in two queries. Asking per factory was an N+1 —
    # the same one the Reports page already had a batched helper for.
    loads_by_party = all_parties_outstanding_loads(session, PARTY_FACTORY)

    rows: list[AgingRow] = []
    for f in session.scalars(
        select(Party).where(
            Party.party_type == PARTY_FACTORY, Party.is_active.is_(True)
        )
    ):
        b = [ZERO, ZERO, ZERO, ZERO]
        for o in loads_by_party.get(f.id, ()):
            if o.outstanding <= 0:
                continue
            if o.days <= 30:
                b[0] += o.outstanding
            elif o.days <= 60:
                b[1] += o.outstanding
            elif o.days <= 90:
                b[2] += o.outstanding
            else:
                b[3] += o.outstanding
        total = money(b[0] + b[1] + b[2] + b[3])
        if total > 0:
            rows.append(
                AgingRow(f.name, money(b[0]), money(b[1]), money(b[2]), money(b[3]), total)
            )
    rows.sort(key=lambda r: r.total, reverse=True)
    return rows


@dataclass
class AdvanceRow:
    name: str
    advance: Decimal


def advance_register(session: Session) -> list[AdvanceRow]:
    """Baparis we've advanced money to (negative balance = advance)."""
    rows: list[AdvanceRow] = []
    balances = all_party_balances(session)
    for b in session.scalars(
        select(Party).where(
            Party.party_type == PARTY_BAPARI, Party.is_active.is_(True)
        )
    ):
        bal = balances.get(b.id, ZERO)
        if bal < 0:
            rows.append(AdvanceRow(b.name, money(-bal)))
    rows.sort(key=lambda r: r.advance, reverse=True)
    return rows


@dataclass
class CashFlowForecast:
    current_cash: Decimal
    total_receivable: Decimal
    total_payable: Decimal
    projected: Decimal
    overdue_in: Decimal
    due_7: Decimal
    due_30: Decimal
    later: Decimal


def cash_flow_forecast(session: Session) -> CashFlowForecast:
    """Cash now + receivables grouped by when they're due vs payables."""
    from datetime import date as _date  # noqa: F401  (kept for clarity)

    from timber.core.bank_service import total_cash_position
    from timber.core.payment_service import party_outstanding_loads

    overdue_in = due_7 = due_30 = later = ZERO
    for f in session.scalars(
        select(Party).where(
            Party.party_type == PARTY_FACTORY, Party.is_active.is_(True)
        )
    ):
        credit = f.credit_days or 0
        for o in party_outstanding_loads(session, f.id):
            if o.outstanding <= 0:
                continue
            days_to_due = credit - o.days  # negative = already overdue
            if days_to_due < 0:
                overdue_in += o.outstanding
            elif days_to_due <= 7:
                due_7 += o.outstanding
            elif days_to_due <= 30:
                due_30 += o.outstanding
            else:
                later += o.outstanding

    cash = total_cash_position(session)
    recv = total_receivable(session)
    pay = total_payable(session)
    return CashFlowForecast(
        current_cash=cash,
        total_receivable=recv,
        total_payable=pay,
        projected=money(cash + recv - pay),
        overdue_in=money(overdue_in),
        due_7=money(due_7),
        due_30=money(due_30),
        later=money(later),
    )


def party_summaries(session: Session, party_type: str) -> list[PartySummary]:
    """Closing balance for every active party of a side."""
    parties = session.scalars(
        select(Party)
        .where(Party.party_type == party_type, Party.is_active.is_(True))
        .order_by(Party.name)
    ).all()
    balances = all_party_balances(session)
    return [
        PartySummary(p.id, p.name, balances.get(p.id, ZERO))
        for p in parties
    ]


# --- location ledger -------------------------------------------------
@dataclass
class LocationSummary:
    name: str
    purchases: Decimal
    sales: Decimal

    @property
    def difference(self) -> Decimal:
        return money(self.sales - self.purchases)


def location_summary(session: Session) -> list[LocationSummary]:
    names = {loc.id: loc.name for loc in session.scalars(select(Location)).all()}
    totals: dict[int | None, list[Decimal]] = {}

    for t in session.scalars(select(BapariTxn).where(BapariTxn.is_void.is_(False))):
        totals.setdefault(t.location_id, [ZERO, ZERO])[0] += balance_amount(
            t.bill, t.freight
        )
    for t in session.scalars(select(FactoryTxn).where(FactoryTxn.is_void.is_(False))):
        totals.setdefault(t.location_id, [ZERO, ZERO])[1] += balance_amount(
            t.bill, t.freight
        )

    rows = [
        LocationSummary(names.get(loc_id, NONE_LABEL), money(pur), money(sal))
        for loc_id, (pur, sal) in totals.items()
    ]
    rows.sort(key=lambda r: r.name)
    return rows


# --- trades (all buy & sell records) --------------------------------
@dataclass
class TradeRow:
    id: int                # the trade group id (use for edit/void)
    txn_date: date
    vehicle: str
    wood: str
    location: str
    bapari_name: str
    bapari_rate: Decimal
    factory_name: str
    factory_rate: Decimal
    muds: Decimal
    kg: Decimal
    purchase_bill: Decimal
    sale_bill: Decimal
    profit: Decimal
    lines: int = 1         # number of wood lines (>1 = mixed load)
    # Truck expenses with who paid each (optional split to a 2nd payer).
    loading: Decimal = ZERO
    loading_payer: str = ""
    loading_payer2: str | None = None
    loading_split: Decimal = Decimal("0")
    freight: Decimal = ZERO
    freight_payer: str = ""
    freight_payer2: str | None = None
    freight_split: Decimal = Decimal("0")
    unloading: Decimal = ZERO
    unloading_payer: str = ""
    unloading_payer2: str | None = None
    unloading_split: Decimal = Decimal("0")

    @property
    def is_mixed(self) -> bool:
        return self.lines > 1

    @property
    def weight_text(self) -> str:
        # Weight shown in decimal maunds (e.g. 429 mud 25 kg -> 429.62).
        return f"{(self.muds + self.kg / 40):,.2f}"


def count_trades(
    session: Session,
    start: date | None = None,
    end: date | None = None,
) -> int:
    """How many trade ROWS (mixed loads counted once) match the range.

    Lets a screen say "showing the latest 500 of 4,312" without paying to
    load the other 3,812.
    """
    key = func.coalesce(CombinedTxn.group_id, CombinedTxn.id)
    q = select(func.count(func.distinct(key)))
    if start is not None:
        q = q.where(CombinedTxn.txn_date >= start)
    if end is not None:
        q = q.where(CombinedTxn.txn_date <= end)
    return int(session.scalar(q) or 0)


def trades_totals(
    session: Session,
    start: date | None = None,
    end: date | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """(profit, sale_bill, muds) summed over EVERY trade in the range.

    Computed in SQL so the figures are the true period totals no matter how
    many rows the screen chooses to display, and so summing 10,000 trades
    costs one query instead of loading them all.
    """
    from timber.db.models import BapariTxn, FactoryTxn

    q = (
        select(
            func.coalesce(func.sum(CombinedTxn.profit), 0),
            func.coalesce(func.sum(FactoryTxn.bill), 0),
            func.coalesce(func.sum(BapariTxn.muds), 0),
        )
        .join(FactoryTxn, CombinedTxn.factory_txn_id == FactoryTxn.id)
        .join(BapariTxn, CombinedTxn.bapari_txn_id == BapariTxn.id)
    )
    if start is not None:
        q = q.where(CombinedTxn.txn_date >= start)
    if end is not None:
        q = q.where(CombinedTxn.txn_date <= end)
    profit, sale, muds = session.execute(q).one()
    return money(profit), money(sale), money(muds)


def list_trades(
    session: Session,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[TradeRow]:
    """All trades oldest first (newest at the bottom), optional date range. A
    mixed-load truck (several wood lines sharing a group) is one aggregated row.

    ``limit`` keeps only the most recent N trades. It selects the newest N
    GROUP KEYS first and then fetches those groups whole — limiting the rows
    directly would slice a mixed load in half and report a partial trade.
    """
    from sqlalchemy.orm import joinedload

    from timber.db.models import BapariTxn, FactoryTxn

    query = (
        select(CombinedTxn)
        .options(
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.party),
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.wood_type),
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.location),
            joinedload(CombinedTxn.factory_txn).joinedload(FactoryTxn.party),
        )
        .order_by(CombinedTxn.id)
    )
    if start is not None:
        query = query.where(CombinedTxn.txn_date >= start)
    if end is not None:
        query = query.where(CombinedTxn.txn_date <= end)

    if limit is not None and limit > 0:
        key = func.coalesce(CombinedTxn.group_id, CombinedTxn.id)
        keys_q = select(key.label("k"))
        if start is not None:
            keys_q = keys_q.where(CombinedTxn.txn_date >= start)
        if end is not None:
            keys_q = keys_q.where(CombinedTxn.txn_date <= end)
        # Newest by DATE, with id only as the tie-break. Ordering by id alone
        # picks the most recently ENTERED trades, which is not the same set as
        # the most recent trades whenever anything is back-dated — and the
        # table itself is sorted by date, so the two must agree.
        keys_q = (keys_q.group_by(key)
                  .order_by(func.max(CombinedTxn.txn_date).desc(),
                            func.max(CombinedTxn.id).desc())
                  .limit(limit))
        wanted = [r for (r,) in session.execute(keys_q).all()]
        if not wanted:
            return []
        query = query.where(key.in_(wanted))

    groups: dict[int, list[CombinedTxn]] = {}
    for c in session.scalars(query):
        key = c.group_id or c.id
        groups.setdefault(key, []).append(c)

    rows: list[TradeRow] = []
    for key, members in groups.items():
        first = members[0]
        b0, f0 = first.bapari_txn, first.factory_txn
        woods: list[str] = []
        for c in members:
            nm = c.bapari_txn.wood_type.name if c.bapari_txn.wood_type else NONE_LABEL
            if nm not in woods:
                woods.append(nm)
        rows.append(
            TradeRow(
                id=key,
                txn_date=first.txn_date,
                vehicle=b0.vehicle_no or "",
                wood=", ".join(woods),
                location=b0.location.name if b0.location else "",
                bapari_name=b0.party.name,
                bapari_rate=b0.rate if len(members) == 1 else ZERO,
                factory_name=f0.party.name,
                factory_rate=f0.rate if len(members) == 1 else ZERO,
                muds=money(sum((c.bapari_txn.muds for c in members), ZERO)),
                kg=money(sum((c.bapari_txn.kg for c in members), ZERO)),
                purchase_bill=money(sum((c.bapari_txn.bill for c in members), ZERO)),
                sale_bill=money(sum((c.factory_txn.bill for c in members), ZERO)),
                profit=money(sum((c.profit for c in members), ZERO)),
                lines=len(members),
                loading=money(sum((c.loading_amount for c in members), ZERO)),
                loading_payer=first.loading_payer,
                loading_payer2=first.loading_payer2,
                loading_split=first.loading_split,
                freight=money(sum((c.freight_amount for c in members), ZERO)),
                freight_payer=first.freight_payer,
                freight_payer2=first.freight_payer2,
                freight_split=first.freight_split,
                unloading=money(sum((c.unloading_amount for c in members), ZERO)),
                unloading_payer=first.unloading_payer,
                unloading_payer2=first.unloading_payer2,
                unloading_split=first.unloading_split,
            )
        )
    rows.sort(key=lambda r: (r.txn_date, r.id))  # oldest first, newest last
    return rows


# --- complete trade ledger (supplier + factory, both sides) ---------
@dataclass
class TradeLedgerRow:
    txn_date: date
    vehicle: str
    wood: str
    weight_text: str
    supplier_name: str
    buy_rate: Decimal
    purchase_bill: Decimal
    supplier_status: str       # paid / partial / unpaid (have we paid them)
    factory_name: str
    sell_rate: Decimal
    sale_bill: Decimal
    factory_status: str        # paid / partial / unpaid (has factory paid us)
    profit: Decimal
    loading: Decimal = ZERO
    loading_payer: str = ""
    loading_payer2: str | None = None
    loading_split: Decimal = Decimal("0")
    freight: Decimal = ZERO
    freight_payer: str = ""
    freight_payer2: str | None = None
    freight_split: Decimal = Decimal("0")
    unloading: Decimal = ZERO
    unloading_payer: str = ""
    unloading_payer2: str | None = None
    unloading_split: Decimal = Decimal("0")


def _pay_status(paid: Decimal, gross: Decimal) -> str:
    if gross <= 0 or paid >= gross:
        return "paid"
    return "partial" if paid > 0 else "unpaid"


def trade_ledger(
    session: Session, start: date | None = None, end: date | None = None
) -> tuple[list[TradeLedgerRow], Decimal, Decimal, Decimal]:
    """Every wood line as a full trade row: where it came from (supplier,
    buy rate, purchase, paid?) and where it went (factory, sell rate, sale,
    paid?), with weight, vehicle and profit. Returns (rows, purchase, sale,
    profit) totals."""
    from sqlalchemy.orm import joinedload

    from timber.core.payment_service import allocated_by_load
    from timber.db.models import BapariTxn, FactoryTxn

    query = (
        select(CombinedTxn)
        .options(
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.party),
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.wood_type),
            joinedload(CombinedTxn.factory_txn).joinedload(FactoryTxn.party),
        )
        .order_by(CombinedTxn.txn_date, CombinedTxn.id)
    )
    if start is not None:
        query = query.where(CombinedTxn.txn_date >= start)
    if end is not None:
        query = query.where(CombinedTxn.txn_date <= end)

    combos = list(session.scalars(query))
    # Paid-per-load in two grouped queries instead of two per row.
    b_paid_map = allocated_by_load(session, "bapari", [c.bapari_txn_id for c in combos])
    f_paid_map = allocated_by_load(session, "factory", [c.factory_txn_id for c in combos])

    rows: list[TradeLedgerRow] = []
    tot_purchase = tot_sale = tot_profit = ZERO
    for c in combos:
        b, f = c.bapari_txn, c.factory_txn
        b_gross = balance_amount(b.bill, b.freight)
        f_gross = balance_amount(f.bill, f.freight)
        b_paid = b_paid_map.get(b.id, ZERO)
        f_paid = f_paid_map.get(f.id, ZERO)
        rows.append(TradeLedgerRow(
            txn_date=c.txn_date,
            vehicle=b.vehicle_no or "",
            wood=b.wood_type.name if b.wood_type else NONE_LABEL,
            weight_text=f"{b.weight:,.2f}",
            supplier_name=b.party.name,
            buy_rate=b.rate,
            purchase_bill=b.bill,
            supplier_status=_pay_status(b_paid, b_gross),
            factory_name=f.party.name,
            sell_rate=f.rate,
            sale_bill=f.bill,
            factory_status=_pay_status(f_paid, f_gross),
            profit=c.profit,
            loading=money(c.loading_amount), loading_payer=c.loading_payer,
            loading_payer2=c.loading_payer2, loading_split=c.loading_split,
            freight=money(c.freight_amount), freight_payer=c.freight_payer,
            freight_payer2=c.freight_payer2, freight_split=c.freight_split,
            unloading=money(c.unloading_amount), unloading_payer=c.unloading_payer,
            unloading_payer2=c.unloading_payer2, unloading_split=c.unloading_split,
        ))
        tot_purchase += b.bill
        tot_sale += f.bill
        tot_profit += c.profit
    return rows, money(tot_purchase), money(tot_sale), money(tot_profit)


# --- combined / profit ledger ---------------------------------------
@dataclass
class ProfitRow:
    id: int
    txn_date: date
    bapari_name: str
    factory_name: str
    weight: Decimal
    bapari_rate: Decimal
    factory_rate: Decimal
    profit: Decimal
    purchase: Decimal = ZERO
    sale: Decimal = ZERO

    @property
    def margin_pct(self) -> Decimal:
        """Profit as a % of the sale value."""
        if self.sale and self.sale != 0:
            return money(self.profit / self.sale * 100)
        return ZERO


def profit_ledger(session: Session) -> tuple[list[ProfitRow], Decimal]:
    from sqlalchemy.orm import joinedload

    from timber.db.models import BapariTxn, FactoryTxn

    rows: list[ProfitRow] = []
    total = ZERO
    query = (
        select(CombinedTxn)
        .options(
            joinedload(CombinedTxn.bapari_txn).joinedload(BapariTxn.party),
            joinedload(CombinedTxn.factory_txn).joinedload(FactoryTxn.party),
        )
        .order_by(CombinedTxn.id)
    )
    for c in session.scalars(query):
        b, f = c.bapari_txn, c.factory_txn
        rows.append(
            ProfitRow(
                c.id, c.txn_date, b.party.name, f.party.name,
                b.weight, b.rate, f.rate, c.profit,
                purchase=money(b.bill), sale=money(f.bill),
            )
        )
        total += c.profit
    return rows, money(total)


@dataclass
class ProfitTotals:
    profit: Decimal
    sale: Decimal
    purchase: Decimal
    trades: int

    @property
    def margin_pct(self) -> Decimal:
        if self.sale and self.sale != 0:
            return money(self.profit / self.sale * 100)
        return ZERO


def profit_totals(rows: list[ProfitRow], total_profit: Decimal) -> ProfitTotals:
    """Roll a list of profit rows up into headline totals."""
    sale = money(sum((r.sale for r in rows), start=ZERO))
    purchase = money(sum((r.purchase for r in rows), start=ZERO))
    return ProfitTotals(money(total_profit), sale, purchase, len(rows))


# --- factory receivables (accounts-receivable dashboard) -------------
STATUS_SETTLED = "settled"
STATUS_OK = "ok"
STATUS_DUE_SOON = "due_soon"
STATUS_OVERDUE = "overdue"


@dataclass
class FactoryReceivable:
    party_id: int
    name: str
    billed: Decimal        # total value of their loads
    received: Decimal      # total payments in
    balance: Decimal       # what they still owe
    oldest_days: int       # age of their oldest unpaid load (0 if none)
    credit_days: int | None
    status: str


def factory_receivables(session: Session) -> list[FactoryReceivable]:
    """Per-factory accounts-receivable line: billed, received, balance,
    age of the oldest unpaid load and an overdue/due-soon status."""
    from timber.core.payment_service import party_outstanding_loads

    rows: list[FactoryReceivable] = []
    balances = all_party_balances(session)
    for f in session.scalars(
        select(Party)
        .where(Party.party_type == PARTY_FACTORY, Party.is_active.is_(True))
        .order_by(Party.name)
    ):
        loads = party_outstanding_loads(session, f.id)
        billed = money(sum((o.amount for o in loads), start=ZERO))
        received = money(sum((o.paid for o in loads), start=ZERO))
        balance = balances.get(f.id, ZERO)
        unpaid = [o for o in loads if o.outstanding > 0]
        oldest_days = max((o.days for o in unpaid), default=0)
        credit = f.credit_days

        if balance <= ZERO:
            status = STATUS_SETTLED
        elif credit is None:
            status = STATUS_OK
        elif oldest_days > credit:
            status = STATUS_OVERDUE
        elif oldest_days >= credit - 7:
            status = STATUS_DUE_SOON
        else:
            status = STATUS_OK

        rows.append(
            FactoryReceivable(
                f.id, f.name, billed, received, money(balance),
                oldest_days, credit, status,
            )
        )
    rows.sort(key=lambda r: r.balance, reverse=True)
    return rows


# --- vehicle history -------------------------------------------------
@dataclass
class VehicleRow:
    side: str
    txn_date: date
    party_name: str
    weight: Decimal
    rate: Decimal
    bill: Decimal


def vehicle_history(session: Session, vehicle_no: str) -> list[VehicleRow]:
    rows: list[VehicleRow] = []
    for model, side in ((BapariTxn, "Bapari"), (FactoryTxn, "Factory")):
        for t in session.scalars(
            select(model).where(
                model.vehicle_no == vehicle_no, model.is_void.is_(False)
            )
        ):
            rows.append(
                VehicleRow(side, t.txn_date, t.party.name, t.weight, t.rate, t.bill)
            )
    rows.sort(key=lambda r: r.txn_date)
    return rows


def known_vehicles(session: Session) -> list[str]:
    seen: list[str] = []
    for model in (BapariTxn, FactoryTxn):
        for v in session.scalars(
            select(model.vehicle_no).where(model.vehicle_no.is_not(None)).distinct()
        ):
            if v and v not in seen:
                seen.append(v)
    return sorted(seen)


# --- wood-type ledger ------------------------------------------------
@dataclass
class WoodSummary:
    name: str
    bought_weight: Decimal
    sold_weight: Decimal


def wood_type_summary(session: Session) -> list[WoodSummary]:
    names = {w.id: w.name for w in session.scalars(select(WoodType)).all()}
    totals: dict[int | None, list[Decimal]] = {}
    for t in session.scalars(select(BapariTxn).where(BapariTxn.is_void.is_(False))):
        totals.setdefault(t.wood_type_id, [ZERO, ZERO])[0] += t.weight
    for t in session.scalars(select(FactoryTxn).where(FactoryTxn.is_void.is_(False))):
        totals.setdefault(t.wood_type_id, [ZERO, ZERO])[1] += t.weight
    rows = [
        WoodSummary(names.get(wid, NONE_LABEL), bought, sold)
        for wid, (bought, sold) in totals.items()
    ]
    rows.sort(key=lambda r: r.name)
    return rows


# --- daily book (روزنامچہ) ------------------------------------------
@dataclass
class DayEntry:
    kind: str
    party_name: str
    detail: str
    amount: Decimal


def daily_book(session: Session, day: date) -> list[DayEntry]:
    entries: list[DayEntry] = []

    for t in session.scalars(
        select(BapariTxn).where(BapariTxn.txn_date == day, BapariTxn.is_void.is_(False))
    ):
        entries.append(
            DayEntry("Purchase", t.party.name, f"{t.weight:g} @ {t.rate:g}", t.net_amount)
        )
    for t in session.scalars(
        select(FactoryTxn).where(FactoryTxn.txn_date == day, FactoryTxn.is_void.is_(False))
    ):
        entries.append(
            DayEntry("Sale", t.party.name, f"{t.weight:g} @ {t.rate:g}", t.net_amount)
        )
    for p in session.scalars(
        select(Payment).where(Payment.txn_date == day, Payment.is_void.is_(False))
    ):
        entries.append(
            DayEntry(f"Payment {p.direction}", p.party.name, p.method, p.amount)
        )
    return entries
