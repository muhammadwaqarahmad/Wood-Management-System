"""API: trade (Buy & Sell) write endpoints — create / void + permission gate.

Route-function level (in-memory ``session`` fixture + a CurrentUser), reusing the
desktop's ``transaction_service``. No HTTP-client dependency.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.api.deps import require_permission
from timber.api.routers.trades import TradeIn, WoodLineIn, create, void

ADMIN = CurrentUser(id=1, username="admin", role="Admin")
VIEWER = CurrentUser(id=2, username="viewer", role="Viewer")


def _seed(session):
    bapari = Party(name="Bapari X", party_type=PARTY_BAPARI, is_active=True)
    factory = Party(name="Factory Y", party_type=PARTY_FACTORY, is_active=True)
    session.add_all([bapari, factory])
    session.commit()
    return bapari.id, factory.id


def test_admin_can_create_and_void_trade(session):
    bid, fid = _seed(session)
    body = TradeIn(
        txn_date=date.today(), bapari_id=bid, factory_id=fid,
        lines=[WoodLineIn(muds=10, bapari_rate=1000, factory_rate=1200,
                          factory_muds=10)],
    )
    res = create(body, session=session, user=ADMIN)
    assert res["count"] >= 1 and res["ids"]

    v = void(res["ids"][0], session=session, user=ADMIN)
    assert v["ok"] is True


def test_viewer_cannot_create_trade():
    dep = require_permission(Permission.CREATE_TXN)
    with pytest.raises(HTTPException) as ei:
        dep(user=VIEWER)
    assert ei.value.status_code == 403
    assert dep(user=ADMIN) is ADMIN
