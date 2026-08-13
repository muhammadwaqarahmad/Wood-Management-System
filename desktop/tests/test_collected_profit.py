"""Collected (realised) profit: only counts as the factory pays."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.dashboard import collected_profit, dashboard_cards
from timber.core.payment_service import create_payment
from timber.core.transaction_service import (
    create_bapari_txn,
    create_combined_txn,
    create_factory_txn,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def trade(session):
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    b = create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000,
    )
    f = create_factory_txn(
        session, txn_date=date(2026, 1, 2), party_id=factory.id, weight=10, rate=1200,
    )
    create_combined_txn(session, bapari_txn_id=b.id, factory_txn_id=f.id)
    return {"factory": factory, "sale": Decimal("12000.00"), "profit": Decimal("2000.00")}


def test_no_profit_collected_before_payment(session, trade):
    # Expected profit is on the books, but nothing collected yet.
    assert dashboard_cards(session).total_profit == trade["profit"]
    assert collected_profit(session) == Decimal("0.00")


def test_half_payment_collects_half_profit(session, trade):
    create_payment(
        session, txn_date=date(2026, 1, 10), party_id=trade["factory"].id,
        amount=6000,  # half of the 12000 sale
    )
    assert collected_profit(session) == Decimal("1000.00")  # half of 2000


def test_full_payment_collects_all_profit(session, trade):
    create_payment(
        session, txn_date=date(2026, 1, 10), party_id=trade["factory"].id,
        amount=12000,
    )
    assert collected_profit(session) == trade["profit"]
