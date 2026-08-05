"""Detailed party statement + complete trade ledger."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import detailed_party_statement
from timber.core.payment_service import create_payment
from timber.core.reports import trade_ledger
from timber.core.transaction_service import (
    create_bapari_txn,
    create_trade,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def parties(session):
    return {
        "bapari": admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI),
        "factory": admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY),
    }


def test_detailed_statement_rich_rows(session, parties):
    bid = parties["bapari"].id
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bid, weight=10, rate=1000,
        vehicle_no="LEA-1",
    )
    create_payment(session, txn_date=date(2026, 1, 2), party_id=bid, amount=4000)

    st = detailed_party_statement(session, bid)
    assert st.total_loads == Decimal("10000.00")
    assert st.total_paid == Decimal("4000.00")
    # Client convention: a load pushes the balance down, a payment up.
    # After a 10,000 load and a 4,000 payment we still owe 6,000 → -6,000.
    assert st.closing == Decimal("-6000.00")

    # Oldest first: load (Jan 1) on top, payment (Jan 2) below.
    load = st.entries[0]
    assert load.kind == "load"
    assert load.vehicle == "LEA-1"
    assert load.rate == Decimal("1000.00")
    assert load.paid == Decimal("4000.00")
    assert load.outstanding == Decimal("6000.00")
    assert load.status == "partial"
    assert load.balance == Decimal("-10000.00")

    pay = st.entries[1]
    assert pay.kind == "payment"
    assert pay.credit == Decimal("4000.00")
    assert pay.balance == Decimal("-6000.00")


def test_detailed_statement_date_filter_opening(session, parties):
    bid = parties["bapari"].id
    create_bapari_txn(session, txn_date=date(2026, 1, 1), party_id=bid, weight=10, rate=1000)
    create_bapari_txn(session, txn_date=date(2026, 2, 1), party_id=bid, weight=5, rate=1000)
    st = detailed_party_statement(session, bid, start=date(2026, 2, 1))
    assert st.opening == Decimal("-10000.00")  # January load folded in (we owe)
    assert len(st.entries) == 1
    assert st.closing == Decimal("-15000.00")


def test_trade_ledger_complete_info(session, parties):
    b, f, c = create_trade(
        session, txn_date=date(2026, 1, 1),
        muds=10, kg=0, bapari_id=parties["bapari"].id, bapari_rate=1000,
        factory_id=parties["factory"].id, factory_rate=1200, vehicle_no="LEA-9",
    )
    # factory pays half; we haven't paid the supplier at all
    create_payment(session, txn_date=date(2026, 1, 5), party_id=parties["factory"].id, amount=6000)

    rows, purchase, sale, profit = trade_ledger(session)
    assert len(rows) == 1
    r = rows[0]
    assert r.vehicle == "LEA-9"
    assert r.supplier_name == "Karim"
    assert r.factory_name == "ABC"
    assert r.purchase_bill == Decimal("10000.00")
    assert r.sale_bill == Decimal("12000.00")
    assert r.profit == Decimal("2000.00")
    assert r.supplier_status == "unpaid"
    assert r.factory_status == "partial"
    assert purchase == Decimal("10000.00")
    assert sale == Decimal("12000.00")
    assert profit == Decimal("2000.00")
