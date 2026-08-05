"""Cheques: pending settles the party but not the bank; clear moves the
bank; bounce reverses."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service, payment_service
from timber.core.ledger import build_party_ledger
from timber.core.transaction_service import create_bapari_txn
from timber.db.models.party import PARTY_BAPARI
from timber.db.models.payment import METHOD_CHEQUE

D = Decimal


@pytest.fixture
def setup(session):
    hbl = bank_service.create_account(session, name="HBL", opening_balance=0)
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_bapari_txn(session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000)
    return {"hbl": hbl, "bapari": bapari}


def _pay_cheque(session, setup, amount=10000):
    return payment_service.create_payment(
        session, txn_date=date(2026, 1, 2), party_id=setup["bapari"].id,
        amount=amount, method=METHOD_CHEQUE, bank_account_id=setup["hbl"].id,
    )


def test_pending_cheque_settles_party_not_bank(session, setup):
    _pay_cheque(session, setup)
    # supplier settled (we handed them the cheque)
    assert build_party_ledger(session, setup["bapari"].id).closing_balance == D("0.00")
    # but the bank hasn't moved yet (cheque pending)
    assert bank_service.account_balance(session, setup["hbl"].id) == D("0.00")
    # cheque balance shows the pending issued cheque (negative = will leave)
    assert payment_service.cheque_balance(session) == D("-10000.00")


def test_clear_cheque_moves_bank(session, setup):
    p = _pay_cheque(session, setup)
    payment_service.clear_cheque(session, p.id)
    assert bank_service.account_balance(session, setup["hbl"].id) == D("-10000.00")
    assert payment_service.cheque_balance(session) == D("0.00")
    assert build_party_ledger(session, setup["bapari"].id).closing_balance == D("0.00")


def test_bounce_cheque_reverses_party(session, setup):
    p = _pay_cheque(session, setup)
    payment_service.bounce_cheque(session, p.id)
    # supplier owed again, bank still untouched, cheque balance cleared
    assert build_party_ledger(session, setup["bapari"].id).closing_balance == D("10000.00")
    assert bank_service.account_balance(session, setup["hbl"].id) == D("0.00")
    assert payment_service.cheque_balance(session) == D("0.00")


def test_list_cheques(session, setup):
    _pay_cheque(session, setup)
    rows = payment_service.list_cheques(session)
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].amount == D("10000.00")
