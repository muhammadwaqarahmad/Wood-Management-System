"""Suppliers / factories — their balances and running statements."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.ledger import build_party_ledger
from timber.core.reports import party_summaries
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

router = APIRouter(prefix="/parties", tags=["parties"])

_KIND = {"supplier": PARTY_BAPARI, "factory": PARTY_FACTORY}


@router.get("")
def list_parties(
    kind: str = Query(..., description="'supplier' or 'factory'"),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    ptype = _KIND.get(kind)
    if ptype is None:
        raise HTTPException(422, "kind must be 'supplier' or 'factory'")
    return [
        {"id": s.party_id, "name": s.name, "balance": float(s.balance)}
        for s in party_summaries(session, ptype)
    ]


@router.get("/{party_id}/ledger")
def party_ledger(
    party_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Full running statement for one party (every load and payment)."""
    try:
        pl = build_party_ledger(session, party_id)
    except ValueError:
        raise HTTPException(404, "Party not found")
    return {
        "party": {"id": pl.party.id, "name": pl.party.name,
                  "type": pl.party.party_type},
        "opening": float(pl.opening_balance),
        "closing": float(pl.closing_balance),
        "entries": [
            {
                "date": e.entry_date.isoformat(),
                "kind": e.kind,
                "ref_id": e.ref_id,
                "description": e.description,
                "debit": float(e.debit),
                "credit": float(e.credit),
                "balance": float(e.balance),
            }
            for e in pl.entries
        ],
    }
