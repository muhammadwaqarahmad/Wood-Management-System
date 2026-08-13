"""Global search across parties, loads and payments (read-only)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.search import global_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("", description="search text"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Match parties, purchases, sales and payments by name/phone/reference."""
    results = global_search(session, q, limit=limit, start=start, end=end)
    return {"results": jsonable(results)}
