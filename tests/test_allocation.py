"""Tests for FIFO payment allocation and advances."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import build_party_ledger
from timber.core.payment_service import (
    create_payment,
    party_outstanding_loads,
    void_payment,
)
from timber.core.transaction_service import create_bapari_txn
from timber.db.models.party import PARTY_BAPARI


@pytest.fixture
def bapari(session):
    return admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)


def _load(session, bapari, day, amount_rate):
    # weight 1 @ rate -> bill = rate
    return create_bapari_txn(
        session, txn_date=day, party_id=bapari.id, weight=1, rate=amount_rate
    )


def test_fifo_allocates_oldest_first(session, bapari):
    _load(session, bapari, date(2026, 1, 1), 1000)   # oldest
    _load(session, bapari, date(2026, 1, 5), 2000)
    # pay 1500 -> fully covers load1 (1000), partially load2 (500)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id, amount=1500)
    loads = party_outstanding_loads(session, bapari.id)
    assert loads[0].outstanding == Decimal("0.00")     # 1000 paid
    assert loads[1].paid == Decimal("500.00")
    assert loads[1].outstanding == Decimal("1500.00")


def test_advance_when_overpaid(session, bapari):
    _load(session, bapari, date(2026, 1, 1), 1000)
    # pay 1500 against a 1000 load -> 500 advance, balance negative
    create_payment(session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=1500)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("-500.00")
    loads = party_outstanding_loads(session, bapari.id)
    assert loads[0].outstanding == Decimal("0.00")


def test_advance_applies_to_later_load(session, bapari):
    # Pay 1000 advance BEFORE any load exists...
    create_payment(session, txn_date=date(2026, 1, 1), party_id=bapari.id, amount=1000)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("-1000.00")
    # ...then a 1000 load arrives -> the advance settles it automatically.
    _load(session, bapari, date(2026, 1, 5), 1000)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("0.00")
    assert party_outstanding_loads(session, bapari.id)[0].outstanding == Decimal("0.00")


def test_cash_payment_hits_cash_account(session):
    from datetime import date as _date

    from timber.core import bank_service
    from timber.db.models.party import PARTY_FACTORY
    from timber.db.models.payment import METHOD_CASH

    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    create_payment(
        session, txn_date=_date(2026, 1, 1), party_id=factory.id, amount=5000,
        method=METHOD_CASH,
    )
    cash = bank_service.cash_account(session)
    assert bank_service.account_balance(session, cash.id) == Decimal("5000.00")


def test_per_truck_percentage_fills_in_order(session, bapari):
    # Three truckloads of 250 each, then a single 600 payment.
    # FIFO fills truck 1 (100%), truck 2 (100%), truck 3 partly (40%).
    _load(session, bapari, date(2026, 1, 1), 250)
    _load(session, bapari, date(2026, 1, 2), 250)
    _load(session, bapari, date(2026, 1, 3), 250)
    create_payment(session, txn_date=date(2026, 1, 4), party_id=bapari.id, amount=600)
    loads = party_outstanding_loads(session, bapari.id)
    pct = [float(o.paid / o.amount * 100) for o in loads]
    assert pct == [100.0, 100.0, 40.0]
    assert loads[2].outstanding == Decimal("150.00")


def test_void_payment_frees_allocations(session, bapari):
    _load(session, bapari, date(2026, 1, 1), 1000)
    p = create_payment(session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=1000)
    assert party_outstanding_loads(session, bapari.id)[0].outstanding == Decimal("0.00")
    void_payment(session, p.id)
    # load is outstanding again, balance back to 1000
    assert party_outstanding_loads(session, bapari.id)[0].outstanding == Decimal("1000.00")
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("1000.00")
