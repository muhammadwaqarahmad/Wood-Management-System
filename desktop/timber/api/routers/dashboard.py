"""Dashboard — the same period summary the desktop shows, in one call."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.dashboard_service import dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Cards, plus/minus table, chart series and bank balances for a period.
    Omitting start/end gives all-time; pass both for a custom range."""
    return jsonable(dashboard_summary(session, start, end))
