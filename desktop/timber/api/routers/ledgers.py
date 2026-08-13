"""Ledgers — Financial Position, Factory Sub-ledger (split), Trade Ledger,
Profit Ledger. Supplier/Factory party ledgers live under /parties.

Same data the desktop Ledgers section shows, from the same services."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.position import financial_position
from timber.core.reports import profit_ledger, profit_totals, trade_ledger
from timber.core.split_ledger import factory_split_statement

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


@router.get("/position")
def position(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Firm-wide financial position: bank/cash, receivables, payables."""
    p = financial_position(session)
    return {
        "bank_total": float(p.bank_total),
        "cash_balance": float(p.cash_balance),
        "cheque_total": float(p.cheque_total),
        "unclaimed_total": float(p.unclaimed_total),
        "grand_total": float(p.grand_total),
        "total_receivable": float(p.total_receivable),
        "total_payable": float(p.total_payable),
        "accounts": [
            {"id": a.id, "name": a.name, "closing": float(a.closing),
             "is_cash": a.is_cash}
            for a in p.accounts
        ],
        "receivables": [
            {"name": r.name, "contact": r.contact, "kind": r.kind,
             "amount": float(r.amount)}
            for r in p.receivables
        ],
        "payables": [
            {"name": r.name, "contact": r.contact, "kind": r.kind,
             "amount": float(r.amount)}
            for r in p.payables
        ],
    }


@router.get("/factory-split/{factory_id}")
def factory_split(
    factory_id: int,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The two-sided (weekly / irregular) sub-ledger for one factory."""
    try:
        st = factory_split_statement(session, factory_id, start, end)
    except ValueError:
        raise HTTPException(404, "Factory not found")
    return {
        "factory_name": st.factory_name,
        "split_rate": float(st.split_rate),
        "opening_left": float(st.opening_left),
        "opening_right": float(st.opening_right),
        "closing_left": float(st.closing_left),
        "closing_right": float(st.closing_right),
        "closing_total": float(st.closing_total),
        "total_left": float(st.total_left),
        "total_right": float(st.total_right),
        "paid_left": float(st.paid_left),
        "paid_right": float(st.paid_right),
        "entries": [jsonable(e) for e in st.entries],
    }


@router.get("/trades")
def trade_ledger_ep(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Every wood line as a full trade row (supplier side + factory side)."""
    rows, purchase, sale, profit = trade_ledger(session, start, end)
    return {
        "totals": {"purchase": float(purchase), "sale": float(sale),
                   "profit": float(profit)},
        "rows": [jsonable(r) for r in rows],
    }


@router.get("/profit")
def profit_ep(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Every combined load with its margin, plus headline totals."""
    rows, total = profit_ledger(session)
    t = profit_totals(rows, total)
    return {
        "totals": {
            "profit": float(t.profit),
            "sale": float(t.sale),
            "purchase": float(t.purchase),
            "trades": t.trades,
            "margin_pct": float(t.margin_pct),
        },
        "rows": [jsonable(r) for r in rows],
    }
