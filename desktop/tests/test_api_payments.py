"""API: payment write endpoints (create + void) + the permission gate.

Tested at the route-function level — the endpoint functions are called directly
with an in-memory session (the shared ``session`` fixture) and a ``CurrentUser``
— so no HTTP-client dependency is needed. This proves the endpoints reuse the
desktop's tested ``payment_service`` and that writes require MANAGE_PAYMENTS. The
same pattern will cover every future write endpoint.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from timber.core import bank_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.db.models import Party
from timber.db.models.party import PARTY_FACTORY
from timber.api.deps import require_permission
from timber.api.routers.payments import PaymentIn, create, void

ADMIN = CurrentUser(id=1, username="admin", role="Admin")
VIEWER = CurrentUser(id=2, username="viewer", role="Viewer")


def _seed(session):
    fac = Party(name="Factory A", party_type=PARTY_FACTORY, is_active=True)
    session.add(fac)
    session.flush()
    acct = bank_service.create_account(
        session, name_en="Cash", name_ur="", bank_name="", account_number="",
        iban="", branch="", opening_balance=100000, created_by=ADMIN.id,
    )
    session.commit()
    return fac.id, acct.id


def test_admin_can_create_and_void_payment(session):
    fac_id, acct_id = _seed(session)
    body = PaymentIn(txn_date=date.today(), party_id=fac_id, amount=5000,
                     method="cash", bank_account_id=acct_id)

    res = create(body, session=session, user=ADMIN)
    assert res["id"] > 0

    v = void(res["id"], session=session, user=ADMIN)
    assert v["ok"] is True


def test_permission_gate_blocks_viewer():
    dep = require_permission(Permission.MANAGE_PAYMENTS)
    with pytest.raises(HTTPException) as ei:
        dep(user=VIEWER)
    assert ei.value.status_code == 403
    # An allowed role passes straight through.
    assert dep(user=ADMIN) is ADMIN
