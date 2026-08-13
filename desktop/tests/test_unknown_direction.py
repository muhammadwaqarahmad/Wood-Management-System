"""Unknown receipts now carry a direction.

An unknown used to be receive-only, so its amount was always ADDED to the
account it landed in. The mirror case — an unexplained debit that left an
account before we know who it went to — has to subtract instead.

Also covers the claim path, which is how a reverse-direction payment could
already be created before this work: Unknown -> Claim onto a supplier.
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service
from timber.core import unknown_payment_service as ups
from timber.core.ledger import party_balance
from timber.core.transaction_service import create_bapari_txn
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT


@pytest.fixture
def account(session):
    return bank_service.create_account(session, name="Meezan", opening_balance=100000)


@pytest.fixture
def bapari(session):
    return admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)


@pytest.fixture
def factory(session):
    return admin_service.create_party(session, name="Ravi Mills",
                                      party_type=PARTY_FACTORY)


def test_unknown_receipt_still_adds_to_the_account(session, account):
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=5000,
                               bank_account_id=account.id)
    assert bank_service.account_balance(session, account.id) == Decimal("105000.00")
    assert ups.total_unknown(session) == Decimal("5000.00")


def test_unknown_debit_subtracts_from_the_account(session, account):
    """The new case: money left and we do not yet know who took it."""
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=5000,
                               bank_account_id=account.id, direction=PAYMENT_OUT)
    assert bank_service.account_balance(session, account.id) == Decimal("95000.00")
    assert ups.total_unknown(session) == Decimal("-5000.00")


def test_receipt_and_debit_net_out(session, account):
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=7000,
                               bank_account_id=account.id)
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 6), amount=2000,
                               bank_account_id=account.id, direction=PAYMENT_OUT)
    assert bank_service.account_balance(session, account.id) == Decimal("105000.00")
    assert ups.total_unknown(session) == Decimal("5000.00")


def test_direction_defaults_to_in(session, account):
    up = ups.create_unknown_payment(session, txn_date=date(2026, 1, 5),
                                    amount=1000, bank_account_id=account.id)
    assert up.direction == PAYMENT_IN


def test_bad_direction_rejected(session, account):
    with pytest.raises(ValueError):
        ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=1000,
                                   bank_account_id=account.id, direction="sideways")


# ----------------------------------------------------------------- claim path
def test_claiming_a_receipt_to_a_supplier_raises_what_we_owe(session, account, bapari):
    """This is the path that was already reachable in the shipped app.

    An unknown RECEIPT claimed by a supplier is money they sent back, so what
    we owe them goes UP. It used to go down by the same amount.
    """
    create_bapari_txn(session, txn_date=date(2026, 1, 1), party_id=bapari.id,
                      weight=1, rate=100000)
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=20000,
                               bank_account_id=account.id)
    up = ups.list_unknown_payments(session)[0]

    ups.claim_unknown_payment(session, up.id, bapari.id)
    assert party_balance(session, bapari.id) == Decimal("120000.00")


def test_claiming_a_receipt_to_a_factory_settles_as_before(session, account, factory):
    from timber.core.transaction_service import create_factory_txn

    create_factory_txn(session, txn_date=date(2026, 1, 1), party_id=factory.id,
                       weight=1, rate=80000)
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=20000,
                               bank_account_id=account.id)
    up = ups.list_unknown_payments(session)[0]

    ups.claim_unknown_payment(session, up.id, factory.id)
    assert party_balance(session, factory.id) == Decimal("60000.00")


def test_claiming_leaves_the_bank_total_unchanged(session, account, factory):
    """Claiming only re-labels money — the account must not move."""
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=20000,
                               bank_account_id=account.id)
    before = bank_service.account_balance(session, account.id)
    up = ups.list_unknown_payments(session)[0]

    ups.claim_unknown_payment(session, up.id, factory.id)
    assert bank_service.account_balance(session, account.id) == before


def test_claiming_a_debit_carries_the_direction_across(session, account, factory):
    """An unknown DEBIT claimed by a factory is us paying them, so their
    outstanding goes up — and the bank still must not move."""
    from timber.core.transaction_service import create_factory_txn

    create_factory_txn(session, txn_date=date(2026, 1, 1), party_id=factory.id,
                       weight=1, rate=80000)
    ups.create_unknown_payment(session, txn_date=date(2026, 1, 5), amount=15000,
                               bank_account_id=account.id, direction=PAYMENT_OUT)
    before = bank_service.account_balance(session, account.id)
    up = ups.list_unknown_payments(session)[0]
    assert up.direction == PAYMENT_OUT

    ups.claim_unknown_payment(session, up.id, factory.id)
    assert party_balance(session, factory.id) == Decimal("95000.00")
    assert bank_service.account_balance(session, account.id) == before
