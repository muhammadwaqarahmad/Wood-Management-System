"""Tests for bank accounts, expenses, and payment->bank linkage."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service, expense_service
from timber.core.payment_service import create_payment
from timber.core.reports import overdue_factory_ids
from timber.core.transaction_service import create_factory_txn
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def account(session):
    return bank_service.create_account(
        session, name="HBL Main", opening_balance=10000
    )


def test_account_opening_balance(session, account):
    assert bank_service.account_balance(session, account.id) == Decimal("10000.00")


def test_payment_in_and_out_move_balance(session, account):
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    # factory pays us 5000 into the account (IN)
    create_payment(
        session, txn_date=date(2026, 1, 1), party_id=factory.id, amount=5000,
        bank_account_id=account.id,
    )
    # we pay bapari 3000 from the account (OUT)
    create_payment(
        session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=3000,
        bank_account_id=account.id,
    )
    # 10000 + 5000 - 3000
    assert bank_service.account_balance(session, account.id) == Decimal("12000.00")


def test_expense_reduces_balance(session, account):
    expense_service.create_expense(
        session, txn_date=date(2026, 1, 1), category="rent", amount=2000,
        bank_account_id=account.id,
    )
    assert bank_service.account_balance(session, account.id) == Decimal("8000.00")
    assert expense_service.total_expenses(session) == Decimal("2000.00")


def test_voided_payment_does_not_move_balance(session, account):
    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    from timber.core.payment_service import void_payment

    p = create_payment(
        session, txn_date=date(2026, 1, 1), party_id=factory.id, amount=5000,
        bank_account_id=account.id,
    )
    void_payment(session, p.id)
    assert bank_service.account_balance(session, account.id) == Decimal("10000.00")


def test_ensure_not_overdrawn_detects_negative(session, account):
    # account opens at 10,000; after a 20,000 OUT payment it's negative, so
    # the overdraft guard (used by the UI before commit) must raise.
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_payment(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id,
        amount=20000, bank_account_id=account.id,
    )
    with pytest.raises(ValueError, match="negative|enough balance"):
        bank_service.ensure_not_overdrawn(session, account.id)


def test_ensure_not_overdrawn_ok_when_funded(session, account):
    # 10,000 in, a 3,000 payment leaves 7,000 — the guard must NOT raise.
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_payment(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id,
        amount=3000, bank_account_id=account.id,
    )
    bank_service.ensure_not_overdrawn(session, account.id)  # no exception
    assert bank_service.account_balance(session, account.id) == Decimal("7000.00")


def test_account_opening_cannot_be_negative(session):
    with pytest.raises(ValueError, match="negative"):
        bank_service.create_account(session, name="BadOpen", opening_balance=-500)


def test_account_update_opening_cannot_be_negative(session, account):
    with pytest.raises(ValueError, match="negative"):
        bank_service.update_account(session, account.id, opening_balance=-1)


def test_duplicate_account_name_rejected(session, account):
    with pytest.raises(ValueError, match="already exists"):
        bank_service.create_account(session, name="HBL Main")


def test_transfer_moves_balance_between_accounts(session, account):
    other = bank_service.create_account(session, name="UBL", opening_balance=0)
    bank_service.create_transfer(
        session, txn_date=date(2026, 1, 1),
        from_account_id=account.id, to_account_id=other.id, amount=3000,
    )
    assert bank_service.account_balance(session, account.id) == Decimal("7000.00")
    assert bank_service.account_balance(session, other.id) == Decimal("3000.00")


def test_transfer_same_account_rejected(session, account):
    with pytest.raises(ValueError, match="different"):
        bank_service.create_transfer(
            session, txn_date=date(2026, 1, 1),
            from_account_id=account.id, to_account_id=account.id, amount=100,
        )


def test_overdue_factory_detection(session):
    factory = admin_service.create_party(
        session, name="Slow Factory", party_type=PARTY_FACTORY, credit_days=10
    )
    # a sale 40 days ago, unpaid -> overdue (credit is 10 days)
    create_factory_txn(
        session, txn_date=date.today() - timedelta(days=40),
        party_id=factory.id, weight=10, rate=1000,
    )
    overdue = overdue_factory_ids(session)
    assert factory.id in overdue


def test_overdue_report(session):
    from timber.core.reports import overdue_report

    factory = admin_service.create_party(
        session, name="Slow Factory", party_type=PARTY_FACTORY, credit_days=30
    )
    create_factory_txn(
        session, txn_date=date.today() - timedelta(days=50),
        party_id=factory.id, weight=10, rate=1000,
    )
    rows = overdue_report(session)
    assert len(rows) == 1
    r = rows[0]
    assert r.name == "Slow Factory"
    assert r.days_outstanding == 50
    assert r.days_overdue == 20          # 50 - 30
    assert r.outstanding == Decimal("10000.00")


def test_factory_without_credit_days_not_overdue(session):
    factory = admin_service.create_party(
        session, name="OK Factory", party_type=PARTY_FACTORY
    )
    create_factory_txn(
        session, txn_date=date(2026, 1, 1), party_id=factory.id, weight=10, rate=1000
    )
    assert factory.id not in overdue_factory_ids(session)
