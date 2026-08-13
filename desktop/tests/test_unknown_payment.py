"""Unknown (unattributed) receipts: land as cash immediately, sit in no
party's ledger, and on claim become a normal payment for that party with
the bank total unchanged."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service
from timber.core.ledger import detailed_party_statement, party_balance
from timber.core.transaction_service import create_trade
from timber.core.unknown_payment_service import (
    claim_unknown_payment,
    create_unknown_payment,
    list_unknown_payments,
    total_unknown,
    void_unknown_payment,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

D = Decimal


@pytest.fixture
def world(session):
    hbl = bank_service.create_account(session, name="HBL", opening_balance=100000)
    fac = admin_service.create_party(session, name="MORO", party_type=PARTY_FACTORY)
    sup = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    session.flush()
    return dict(hbl=hbl, fac=fac, sup=sup)


def test_unknown_receipt_is_cash_but_no_party(session, world):
    create_unknown_payment(
        session, txn_date=date(2026, 7, 1), amount=70000,
        bank_account_id=world["hbl"].id, reference_no="TRX-9",
    )
    # Money is in the bank right away...
    assert bank_service.account_balance(session, world["hbl"].id) == D("170000.00")
    assert total_unknown(session) == D("70000.00")
    # ...but attributed to nobody.
    assert party_balance(session, world["fac"].id) == D("0.00")
    assert len(list_unknown_payments(session)) == 1


def test_claim_credits_party_and_keeps_bank(session, world):
    # The factory owes us 90,000 from a sale.
    create_trade(
        session, txn_date=date(2026, 7, 1), muds=200, kg=0,
        bapari_id=world["sup"].id, bapari_rate=400,
        factory_id=world["fac"].id, factory_rate=450, vehicle_no="V1",
    )
    assert party_balance(session, world["fac"].id) == D("90000.00")

    up = create_unknown_payment(
        session, txn_date=date(2026, 7, 2), amount=90000,
        bank_account_id=world["hbl"].id,
    )
    bank_before = bank_service.account_balance(session, world["hbl"].id)

    # A factory claims it -> becomes their payment.
    claim_unknown_payment(session, up.id, world["fac"].id)

    # Bank total UNCHANGED by the claim (unknown removed, payment added).
    assert bank_service.account_balance(session, world["hbl"].id) == bank_before
    # The factory is now settled, and it shows on their ledger.
    assert party_balance(session, world["fac"].id) == D("0.00")
    st = detailed_party_statement(session, world["fac"].id)
    assert any(e.kind == "payment" and e.credit == D("90000.00") for e in st.entries)
    # No longer unknown.
    assert total_unknown(session) == D("0.00")
    assert list_unknown_payments(session) == []


def test_void_unknown_removes_it_from_bank(session, world):
    up = create_unknown_payment(
        session, txn_date=date(2026, 7, 1), amount=25000,
        bank_account_id=world["hbl"].id,
    )
    assert bank_service.account_balance(session, world["hbl"].id) == D("125000.00")
    void_unknown_payment(session, up.id)
    assert bank_service.account_balance(session, world["hbl"].id) == D("100000.00")
    assert total_unknown(session) == D("0.00")


def test_unknown_rolling_opening(session, world):
    create_unknown_payment(
        session, txn_date=date(2026, 7, 1), amount=40000,
        bank_account_id=world["hbl"].id,
    )
    # Counts before the next day's opening, not before its own day.
    assert bank_service.account_balance(
        session, world["hbl"].id, before=date(2026, 7, 1)
    ) == D("100000.00")
    assert bank_service.account_balance(
        session, world["hbl"].id, before=date(2026, 7, 2)
    ) == D("140000.00")


def test_unclaimed_shows_in_position_and_report(session, world):
    """The unclaimed total is surfaced on the Financial Position summary and
    inside the bank report, so it's visible on the dashboard/report pages."""
    from timber.core.position import financial_position
    from timber.core.report_data import position_report

    create_unknown_payment(
        session, txn_date=date(2026, 7, 1), amount=55000,
        bank_account_id=world["hbl"].id,
    )
    pos = financial_position(session)
    assert pos.unclaimed_total == D("55000.00")
    # Already folded into the grand total (money is really in the bank).
    assert pos.grand_total == D("155000.00")

    report = position_report(session, "bank")
    labels = {label: value for label, value in report.summary}
    from timber import i18n

    assert labels[i18n.tr("unclaimed_total")] == "55,000.00"
