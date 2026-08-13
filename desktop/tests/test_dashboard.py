"""Tests for the dashboard aggregations."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core.dashboard import (
    dashboard_cards,
    monthly_cash_flow,
    monthly_profit,
    outstanding_alerts,
    profit_by_location,
    top_parties,
)
from timber.core.payment_service import create_payment
from timber.core.transaction_service import (
    create_bapari_txn,
    create_combined_txn,
    create_factory_txn,
)
from timber.db.models import Location, Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def data(session):
    lahore = Location(name="Lahore")
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    factory = Party(name="ABC", party_type=PARTY_FACTORY)
    session.add_all([lahore, bapari, factory])
    session.flush()
    b = create_bapari_txn(
        session, txn_date=date.today(), party_id=bapari.id,
        weight=10, rate=1000, location_id=lahore.id,
    )
    f = create_factory_txn(
        session, txn_date=date.today(), party_id=factory.id,
        weight=10, rate=1200, location_id=lahore.id,
    )
    create_combined_txn(session, bapari_txn_id=b.id, factory_txn_id=f.id)
    create_payment(session, txn_date=date.today(), party_id=factory.id, amount=5000)
    create_payment(session, txn_date=date.today(), party_id=bapari.id, amount=3000)
    return {"lahore": lahore, "bapari": bapari, "factory": factory}


def test_cards(session, data):
    cards = dashboard_cards(session)
    assert cards.payable == Decimal("7000.00")     # 10000 - 3000
    assert cards.receivable == Decimal("7000.00")  # 12000 - 5000
    assert cards.net == Decimal("0.00")
    assert cards.total_profit == Decimal("2000.00")
    assert cards.cash_in == Decimal("5000.00")
    assert cards.cash_out == Decimal("3000.00")


def test_monthly_profit_window(session, data):
    rows = monthly_profit(session, months=6)
    assert len(rows) == 6
    # The current month should carry the 2,000 profit.
    assert rows[-1][1] == Decimal("2000.00")


def test_profit_by_location(session, data):
    rows = profit_by_location(session)
    assert rows[0][0] == "Lahore"
    assert rows[0][1] == Decimal("2000.00")


def test_top_parties(session, data):
    tops = top_parties(session, PARTY_FACTORY, n=5)
    assert tops[0][0] == "ABC"


def test_outstanding_alerts(session, data):
    alerts = outstanding_alerts(session)
    names = {a.name for a in alerts}
    assert "Karim" in names and "ABC" in names


def test_monthly_cash_flow(session, data):
    rows = monthly_cash_flow(session, months=6)
    assert len(rows) == 6
    # current month carries the two payments (5000 in, 3000 out)
    label, money_in, money_out = rows[-1]
    assert money_in == Decimal("5000.00")
    assert money_out == Decimal("3000.00")
