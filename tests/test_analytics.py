"""Tests for aging, advance register, cash-flow forecast, and num→words."""

from datetime import date, timedelta
from decimal import Decimal

from timber.core import admin_service
from timber.core.num_to_words import to_words
from timber.core.payment_service import create_payment
from timber.core.reports import advance_register, aging_report, cash_flow_forecast
from timber.core.transaction_service import create_factory_txn
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def test_num_to_words_english():
    assert to_words(120000, "en") == "One lakh twenty thousand rupees"
    assert to_words(1500.50, "en") == "One thousand five hundred rupees and fifty paisa"


def test_num_to_words_urdu():
    assert to_words(120000, "ur").startswith("ایک لاکھ بیس ہزار")


def test_aging_buckets(session):
    f = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    create_factory_txn(session, txn_date=date.today() - timedelta(days=10),
                       party_id=f.id, weight=10, rate=1000)        # 0-30
    create_factory_txn(session, txn_date=date.today() - timedelta(days=75),
                       party_id=f.id, weight=10, rate=1000)        # 61-90
    rows = aging_report(session)
    assert len(rows) == 1
    r = rows[0]
    assert r.b0_30 == Decimal("10000.00")
    assert r.b61_90 == Decimal("10000.00")
    assert r.total == Decimal("20000.00")


def test_advance_register(session):
    b = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_payment(session, txn_date=date.today(), party_id=b.id, amount=30000)  # advance
    rows = advance_register(session)
    assert len(rows) == 1
    assert rows[0].name == "Karim"
    assert rows[0].advance == Decimal("30000.00")


def test_cash_flow_forecast(session):
    f = admin_service.create_party(
        session, name="ABC", party_type=PARTY_FACTORY, credit_days=30
    )
    # sale 40 days ago, 30-day credit -> overdue inflow
    create_factory_txn(session, txn_date=date.today() - timedelta(days=40),
                       party_id=f.id, weight=10, rate=1000)
    fc = cash_flow_forecast(session)
    assert fc.overdue_in == Decimal("10000.00")
    assert fc.total_receivable == Decimal("10000.00")
