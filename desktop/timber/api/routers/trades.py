"""Trades — buy & sell records.

Read: recent trades + range totals. Write (create / update / void): reuses the
desktop's tested ``transaction_service`` so a mixed-load truck books identically
everywhere. Create needs CREATE_TXN; edit/void need EDIT_TRADE (same as desktop).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.core.reports import count_trades, list_trades, trades_totals
from timber.core.transaction_service import (
    WoodLine,
    _group_members,
    create_mixed_trade,
    update_mixed_trade,
    void_trade,
)
from timber.db.models.combined_txn import PAYER_US, CombinedTxn

router = APIRouter(prefix="/trades", tags=["trades"])


class WoodLineIn(BaseModel):
    """One wood line of a (possibly mixed-load) truck. Supplier weight is
    muds/kg; factory weight defaults to the same but can differ."""

    wood_type_id: int | None = None
    muds: float = 0
    kg: float = 0
    bapari_rate: float = 0
    factory_rate: float = 0
    factory_muds: float | None = None
    factory_kg: float | None = None


class TradeIn(BaseModel):
    txn_date: date
    bapari_id: int
    factory_id: int
    lines: list[WoodLineIn]
    location_id: int | None = None
    vehicle_no: str | None = None
    loading_amount: float = 0
    loading_payer: str = PAYER_US
    loading_payer2: str | None = None
    loading_split: float = 0
    freight_amount: float = 0
    freight_payer: str = PAYER_US
    freight_payer2: str | None = None
    freight_split: float = 0
    unloading_amount: float = 0
    unloading_payer: str = PAYER_US
    unloading_payer2: str | None = None
    unloading_split: float = 0
    notes: str | None = None


def _trade_kwargs(body: TradeIn) -> dict:
    """Map the request onto ``transaction_service``'s create/update kwargs."""
    lines = [
        WoodLine(
            wood_type_id=ln.wood_type_id, muds=ln.muds, kg=ln.kg,
            bapari_rate=ln.bapari_rate, factory_rate=ln.factory_rate,
            factory_muds=ln.factory_muds, factory_kg=ln.factory_kg,
        )
        for ln in body.lines
    ]
    return dict(
        txn_date=body.txn_date, bapari_id=body.bapari_id, factory_id=body.factory_id,
        lines=lines, location_id=body.location_id, vehicle_no=body.vehicle_no,
        loading_amount=body.loading_amount, loading_payer=body.loading_payer,
        loading_payer2=body.loading_payer2, loading_split=body.loading_split,
        freight_amount=body.freight_amount, freight_payer=body.freight_payer,
        freight_payer2=body.freight_payer2, freight_split=body.freight_split,
        unloading_amount=body.unloading_amount, unloading_payer=body.unloading_payer,
        unloading_payer2=body.unloading_payer2, unloading_split=body.unloading_split,
        notes=body.notes,
    )


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


@router.post("")
def create(
    body: TradeIn,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_permission(Permission.CREATE_TXN)),
) -> dict:
    """Record a buy & sell (reuses ``create_mixed_trade``)."""
    try:
        created = create_mixed_trade(session, created_by=user.id, **_trade_kwargs(body))
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ids = [c.id for c in created]
    return {"ids": ids, "count": len(ids)}


@router.get("/{group_id}")
def trade_detail(
    group_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The full editable trade (date, vehicle, parties, wood lines, charges) —
    the same fields the desktop TradeEditDialog loads to pre-fill its form."""
    anchor = session.get(CombinedTxn, group_id)
    if anchor is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    members = sorted(_group_members(session, anchor), key=lambda c: c.id)
    first = members[0]
    b0, f0 = first.bapari_txn, first.factory_txn
    return {
        "id": group_id,
        "txn_date": b0.txn_date.isoformat(),
        "vehicle_no": b0.vehicle_no or "",
        "bapari_id": b0.party_id,
        "factory_id": f0.party_id,
        "lines": [
            {
                "wood_type_id": c.bapari_txn.wood_type_id,
                "muds": float(c.bapari_txn.muds), "kg": float(c.bapari_txn.kg),
                "bapari_rate": float(c.bapari_txn.rate),
                "factory_rate": float(c.factory_txn.rate),
                "factory_muds": float(c.factory_txn.muds), "factory_kg": float(c.factory_txn.kg),
            }
            for c in members
        ],
        "loading_amount": float(first.loading_amount), "loading_payer": first.loading_payer,
        "loading_payer2": first.loading_payer2, "loading_split": float(first.loading_split),
        "freight_amount": float(first.freight_amount), "freight_payer": first.freight_payer,
        "freight_payer2": first.freight_payer2, "freight_split": float(first.freight_split),
        "unloading_amount": float(first.unloading_amount), "unloading_payer": first.unloading_payer,
        "unloading_payer2": first.unloading_payer2, "unloading_split": float(first.unloading_split),
    }


@router.put("/{group_id}")
def update(
    group_id: int,
    body: TradeIn,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_permission(Permission.EDIT_TRADE)),
) -> dict:
    """Edit a saved trade (reuses ``update_mixed_trade``)."""
    try:
        update_mixed_trade(session, group_id, created_by=user.id, **_trade_kwargs(body))
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{combined_id}/void")
def void(
    combined_id: int,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require_permission(Permission.EDIT_TRADE)),
) -> dict:
    """Cancel a whole trade — voids both the purchase and the sale."""
    try:
        void_trade(session, combined_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
