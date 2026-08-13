"""Trades — buy & sell records, newest first, with running totals."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.reports import count_trades, list_trades, trades_totals

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("")
def trades(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Most recent ``limit`` trades in the range, plus the totals for the WHOLE
    range (not just the page) so the phone can show an accurate summary."""
    rows = list_trades(session, start, end, limit=limit)
    rows.reverse()  # newest first for the phone
    return {
        "total_count": count_trades(session, start, end),
        "totals": jsonable(trades_totals(session, start, end)),
        "trades": jsonable(rows),
    }
