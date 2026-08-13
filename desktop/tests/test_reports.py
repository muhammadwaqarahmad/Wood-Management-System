"""Tests for the ledger/report aggregations."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core.reports import (
    STATUS_OVERDUE,
    STATUS_SETTLED,
    daily_book,
    factory_receivables,
    location_summary,
    party_summaries,
    profit_ledger,
    profit_totals,
    vehicle_history,
    wood_type_summary,
)
from timber.core.payment_service import create_payment
from timber.core.transaction_service import (
    create_bapari_txn,
    create_combined_txn,
    create_factory_txn,
)
from timber.db.models import Location, Party, WoodType
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def setup(session):
    lahore = Location(name="Lahore")
    kikar = WoodType(name="Kikar")
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    factory = Party(name="ABC", party_type=PARTY_FACTORY)
    session.add_all([lahore, kikar, bapari, factory])
    session.flush()
    return {
        "lahore": lahore,
        "kikar": kikar,
        "bapari": bapari,
        "factory": factory,
    }


def test_party_summaries(session, setup):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000, freight=500,
    )
    summaries = party_summaries(session, PARTY_BAPARI)
    assert len(summaries) == 1
    assert summaries[0].balance == Decimal("10500.00")


def test_location_summary(session, setup):
    loc = setup["lahore"].id
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000, location_id=loc,
    )
    create_factory_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["factory"].id,
        weight=10, rate=1300, location_id=loc,
    )
    rows = location_summary(session)
    lahore_row = next(r for r in rows if r.name == "Lahore")
    assert lahore_row.purchases == Decimal("10000.00")
    assert lahore_row.sales == Decimal("13000.00")
    assert lahore_row.difference == Decimal("3000.00")


def test_profit_ledger(session, setup):
    b = create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000,
    )
    f = create_factory_txn(
        session, txn_date=date(2026, 1, 2), party_id=setup["factory"].id,
        weight=10, rate=1200,
    )
    create_combined_txn(session, bapari_txn_id=b.id, factory_txn_id=f.id)
    rows, total = profit_ledger(session)
    assert total == Decimal("2000.00")
    assert rows[0].bapari_name == "Karim"
    assert rows[0].factory_name == "ABC"


def test_profit_totals_and_margin(session, setup):
    b = create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000,
    )
    f = create_factory_txn(
        session, txn_date=date(2026, 1, 2), party_id=setup["factory"].id,
        weight=10, rate=1250,
    )
    create_combined_txn(session, bapari_txn_id=b.id, factory_txn_id=f.id)
    rows, total = profit_ledger(session)
    totals = profit_totals(rows, total)
    assert totals.sale == Decimal("12500.00")
    assert totals.purchase == Decimal("10000.00")
    assert totals.profit == Decimal("2500.00")
    assert totals.trades == 1
    # margin = 2500 / 12500 = 20%
    assert totals.margin_pct == Decimal("20.00")
    assert rows[0].margin_pct == Decimal("20.00")


def test_factory_receivables_status(session, setup):
    from datetime import timedelta

    today = date.today()
    setup["factory"].credit_days = 30
    # A sale older than the credit period and unpaid -> overdue.
    create_factory_txn(
        session, txn_date=today - timedelta(days=45), party_id=setup["factory"].id,
        weight=10, rate=1000,
    )
    rows = factory_receivables(session)
    abc = next(r for r in rows if r.name == "ABC")
    assert abc.billed == Decimal("10000.00")
    assert abc.balance == Decimal("10000.00")
    assert abc.status == STATUS_OVERDUE
    assert abc.oldest_days >= 45

    # Paying it off flips the status to settled.
    create_payment(session, txn_date=today, party_id=setup["factory"].id, amount=10000)
    abc = next(r for r in factory_receivables(session) if r.name == "ABC")
    assert abc.balance == Decimal("0.00")
    assert abc.status == STATUS_SETTLED


def test_list_trades_and_date_filter(session, setup):
    from timber.core.reports import list_trades
    from timber.core.transaction_service import create_trade

    create_trade(
        session, txn_date=date(2026, 1, 10), muds=10,
        bapari_id=setup["bapari"].id, bapari_rate=1000,
        factory_id=setup["factory"].id, factory_rate=1300,
        vehicle_no="LEA-9", location_id=setup["lahore"].id,
    )
    create_trade(
        session, txn_date=date(2026, 2, 5), muds=5,
        bapari_id=setup["bapari"].id, bapari_rate=1000,
        factory_id=setup["factory"].id, factory_rate=1200,
    )
    # all
    assert len(list_trades(session)) == 2
    # January only
    jan = list_trades(session, date(2026, 1, 1), date(2026, 1, 31))
    assert len(jan) == 1
    assert jan[0].vehicle == "LEA-9"
    assert jan[0].profit == Decimal("3000.00")
    assert jan[0].factory_name == "ABC"


def test_vehicle_history(session, setup):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000, vehicle_no="LEA-1",
    )
    create_factory_txn(
        session, txn_date=date(2026, 1, 2), party_id=setup["factory"].id,
        weight=10, rate=1300, vehicle_no="LEA-1",
    )
    rows = vehicle_history(session, "LEA-1")
    assert len(rows) == 2
    assert {r.side for r in rows} == {"Bapari", "Factory"}


def test_wood_type_summary(session, setup):
    wid = setup["kikar"].id
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["bapari"].id,
        weight=10, rate=1000, wood_type_id=wid,
    )
    create_factory_txn(
        session, txn_date=date(2026, 1, 1), party_id=setup["factory"].id,
        weight=7, rate=1300, wood_type_id=wid,
    )
    rows = wood_type_summary(session)
    kikar = next(r for r in rows if r.name == "Kikar")
    assert kikar.bought_weight == Decimal("10.000")
    assert kikar.sold_weight == Decimal("7.000")


def test_daily_book(session, setup):
    day = date(2026, 1, 1)
    create_bapari_txn(
        session, txn_date=day, party_id=setup["bapari"].id, weight=10, rate=1000
    )
    create_payment(session, txn_date=day, party_id=setup["factory"].id, amount=5000)
    entries = daily_book(session, day)
    kinds = {e.kind for e in entries}
    assert "Purchase" in kinds
    assert any(k.startswith("Payment") for k in kinds)
