"""Reports — cash-flow statement and per-party (factory/supplier) performance.

Same three data sets the desktop Reports page shows, from the same services."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.reports import (
    aging_report,
    daily_book,
    overdue_report,
    wood_type_summary,
)
from timber.core.stats_service import cashflow_report, party_stats
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/cashflow")
def cashflow(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Total business worth + the cash-flow statement rows for the period."""
    return jsonable(cashflow_report(session, start, end))


@router.get("/parties")
def party_performance(
    kind: str = Query(..., description="'factory' or 'supplier'"),
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Overall totals + a per-party table (trades, volume, profit, balance,
    overdue buckets for factories)."""
    ptype = {"factory": PARTY_FACTORY, "supplier": PARTY_BAPARI}.get(kind)
    if ptype is None:
        raise HTTPException(422, "kind must be 'factory' or 'supplier'")
    return jsonable(party_stats(session, ptype, start, end))


@router.get("/overdue")
def overdue(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Factories past their credit period, worst overdue first."""
    return {"factories": jsonable(overdue_report(session))}


@router.get("/aging")
def aging(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Factory receivables split into 0-30 / 31-60 / 61-90 / 90+ day buckets."""
    return {"rows": jsonable(aging_report(session))}


@router.get("/daily-book")
def daily_book_ep(
    day: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Every purchase, sale and payment on one day (defaults to today)."""
    d = day or date.today()
    return {"day": d.isoformat(), "entries": jsonable(daily_book(session, d))}


@router.get("/wood-summary")
def wood_summary_ep(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Total weight bought vs sold per wood type."""
    return {"rows": jsonable(wood_type_summary(session))}
