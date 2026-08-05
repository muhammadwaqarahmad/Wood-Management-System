"""Advanced statistics for the Reports page: overall cash flow, and
per-factory / per-supplier performance with overdue buckets.

Everything is period-aware (start/end) where it's a flow; balance-sheet
positions (banks, cash, balances, cheques) are as-of-now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.core import bank_service, expense_service, loan_service
from timber.core.calculations import money
from timber.core.ledger import receivable_and_payable
from timber.core.payment_service import list_cheques, party_outstanding_loads
from timber.core.reports import list_trades
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

ZERO = Decimal("0.00")


# ------------------------------------------------------------------ #
# Overall cash flow                                                    #
# ------------------------------------------------------------------ #
def cashflow_report(
    session: Session, start: date | None = None, end: date | None = None
) -> dict:
    """Rows for the cash-flow statement. Each row: key (i18n), amount,
    sign (+1 adds to the position, -1 reduces, 0 = result row), section."""
    balances = bank_service.all_balances(session)
    cash = money(sum((b.closing for b in balances if b.is_cash), ZERO))
    banks = money(sum((b.closing for b in balances if not b.is_cash), ZERO))
    available = money(banks + cash)

    # Cheques received from receivables that are still in cheque form —
    # not yet money in a bank or in cash.
    pending = list_cheques(session, status="pending")
    chq_in = money(sum((c.amount for c in pending if c.direction == "in"), ZERO))

    # Money already in the bank but not yet attributed to any party. It is a
    # subset of "available" above (not added again), surfaced so it's visible.
    from timber.core.unknown_payment_service import total_unknown

    unclaimed = total_unknown(session)

    receivable, payable = receivable_and_payable(session)  # one balance pass
    from timber.db.models.loan import LOAN_GIVEN

    loans = loan_service.total_loans_outstanding(session)              # we owe
    loans_given = loan_service.total_loans_outstanding(session, LOAN_GIVEN)

    trades = list_trades(session, start, end)
    profit = money(sum((t.profit for t in trades), ZERO))
    exp_biz = expense_service.total_expenses(
        session, operating_only=True, kind="business", start=start, end=end
    )
    exp_house = expense_service.total_expenses(
        session, operating_only=True, kind="house", start=start, end=end
    )
    profit_after = money(profit - exp_biz - exp_house)
    net = money(available + receivable + loans_given - payable - loans)

    def row(key: str, amount: Decimal, sign: int, section: str) -> dict:
        return {"key": key, "amount": float(amount), "sign": sign, "section": section}

    # Total business worth = everything we hold + everything we will
    # receive - everything we must give (payable + loans).
    return {
        "worth": float(net),
        "rows": [
            # -- the headline ------------------------------------------
            row("worth", net, 0, "worth"),
            # -- 1. what we hold ---------------------------------------
            row("banks", banks, 1, "position"),
            row("cash", cash, 1, "position"),
            row("available", available, 0, "position"),
            # -- 2. what we will receive / must give -------------------
            row("receivable", receivable, 1, "balances"),
            row("loans_given", loans_given, 1, "balances"),
            row("payable", payable, -1, "balances"),
            row("loans", loans, -1, "balances"),
            # -- 3. received in cheque form (not yet in bank/cash) ------
            row("cheques_in", chq_in, 1, "cheques"),
            # -- unattributed money sitting in the bank (memo; = result) --
            row("unclaimed", unclaimed, 0, "unclaimed"),
            # -- 4. the period's flows ---------------------------------
            row("profit", profit, 1, "flows"),
            row("exp_business", exp_biz, -1, "flows"),
            row("exp_house", exp_house, -1, "flows"),
            row("profit_after", profit_after, 0, "flows"),
        ],
        "trades": len(trades),
    }


# ------------------------------------------------------------------ #
# Per-party performance (factories / suppliers)                        #
# ------------------------------------------------------------------ #
@dataclass
class PartyStat:
    name: str
    trades: int
    volume: Decimal      # sales to a factory / purchases from a supplier
    profit: Decimal
    balance: Decimal     # display-signed: + we receive, - we give
    over30: Decimal      # outstanding on loads older than 30 days
    over60: Decimal      # ... older than 60 days


def party_stats(
    session: Session,
    party_type: str,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Overall + per-party stats. ``party_type`` is PARTY_FACTORY or
    PARTY_BAPARI. Volume/profit/trades honour the period; balance and the
    overdue buckets are as-of-now."""
    assert party_type in (PARTY_FACTORY, PARTY_BAPARI)
    is_factory = party_type == PARTY_FACTORY

    trades = list_trades(session, start, end)
    per: dict[str, dict] = {}
    for t in trades:
        name = t.factory_name if is_factory else t.bapari_name
        agg = per.setdefault(name, {"trades": 0, "volume": ZERO, "profit": ZERO})
        agg["trades"] += 1
        agg["volume"] = money(
            agg["volume"] + (t.sale_bill if is_factory else t.purchase_bill)
        )
        agg["profit"] = money(agg["profit"] + t.profit)

    from timber.core.ledger import all_party_balances
    from timber.core.payment_service import all_parties_outstanding_loads

    party_bal = all_party_balances(session)  # every party in a few queries
    # Every party's loads in TWO queries. Doing this per party was an N+1 that
    # cost ~2 queries per party (~200 with the client's party list) — decisive
    # over a cloud database where each query is a network round-trip.
    loads_by_party = all_parties_outstanding_loads(session, party_type)
    disp_sign = 1 if is_factory else -1
    rows: list[PartyStat] = []
    for p in session.scalars(
        select(Party).where(
            Party.party_type == party_type, Party.is_active.is_(True)
        ).order_by(Party.name)
    ):
        agg = per.get(p.name, {"trades": 0, "volume": ZERO, "profit": ZERO})
        balance = money(disp_sign * party_bal.get(p.id, ZERO))
        over30 = over60 = ZERO
        # Overdue buckets only exist when the party actually has an outstanding
        # net (FIFO fully allocates a settled party, so balance==0 => nothing
        # outstanding => nothing overdue). Guarding on the already-computed
        # balance skips a per-party query for every settled/inactive party --
        # decisive over a cloud DB where each of ~100 parties was a round-trip.
        if party_bal.get(p.id, ZERO):
            for o in loads_by_party.get(p.id, ()):
                if o.outstanding <= 0:
                    continue
                if o.days > 30:
                    over30 += o.outstanding
                if o.days > 60:
                    over60 += o.outstanding
        if not agg["trades"] and balance == 0 and over30 == 0:
            continue  # nothing to report for this party
        rows.append(PartyStat(
            p.name, agg["trades"], agg["volume"], agg["profit"],
            balance, money(over30), money(over60),
        ))
    rows.sort(key=lambda r: r.volume, reverse=True)

    return {
        "overall": {
            "trades": sum(r.trades for r in rows),
            "volume": float(money(sum((r.volume for r in rows), ZERO))),
            "profit": float(money(sum((r.profit for r in rows), ZERO))),
            "receivable": float(money(sum((r.balance for r in rows if r.balance > 0), ZERO))),
            "payable": float(money(sum((-r.balance for r in rows if r.balance < 0), ZERO))),
            "over30": float(money(sum((r.over30 for r in rows), ZERO))),
            "over60": float(money(sum((r.over60 for r in rows), ZERO))),
        },
        "rows": [
            {
                "name": r.name, "trades": r.trades, "volume": float(r.volume),
                "profit": float(r.profit), "balance": float(r.balance),
                "over30": float(r.over30), "over60": float(r.over60),
            }
            for r in rows
        ],
    }
