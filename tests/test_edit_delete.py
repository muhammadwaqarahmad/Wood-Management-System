"""Edit/delete services: payment, expense, transfer, lookup, user."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service, expense_service
from timber.core.ledger import build_party_ledger
from timber.core.payment_service import create_payment, update_payment
from timber.db.models import Location, User
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import METHOD_CASH


@pytest.fixture
def bapari(session):
    return admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)


def test_update_payment_changes_balance(session, bapari):
    from timber.core.transaction_service import create_bapari_txn
    create_bapari_txn(session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000)
    p = create_payment(session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=3000)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("7000.00")
    update_payment(session, p.id, txn_date=date(2026, 1, 2), amount=5000, method=METHOD_CASH)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("5000.00")


def test_update_and_delete_expense(session):
    e = expense_service.create_expense(session, txn_date=date(2026, 1, 1), category="rent", amount=1000)
    expense_service.update_expense(session, e.id, txn_date=date(2026, 1, 1), category="fuel", amount=250)
    assert expense_service.total_expenses(session) == Decimal("250.00")
    row = expense_service.list_expenses(session)[0]
    assert row.category == "fuel"


def test_update_and_delete_transfer(session):
    a = bank_service.create_account(session, name="HBL", opening_balance=10000)
    b = bank_service.create_account(session, name="UBL", opening_balance=0)
    t = bank_service.create_transfer(session, txn_date=date(2026, 1, 1),
                                     from_account_id=a.id, to_account_id=b.id, amount=2000)
    assert bank_service.account_balance(session, b.id) == Decimal("2000.00")
    bank_service.update_transfer(session, t.id, txn_date=date(2026, 1, 1),
                                 from_account_id=a.id, to_account_id=b.id, amount=3500)
    assert bank_service.account_balance(session, b.id) == Decimal("3500.00")
    bank_service.delete_transfer(session, t.id)
    assert bank_service.account_balance(session, b.id) == Decimal("0.00")


def test_delete_lookup_blocked_when_used(session, bapari):
    from timber.core.transaction_service import create_bapari_txn
    loc = admin_service.create_lookup(session, Location, "Lahore")
    create_bapari_txn(session, txn_date=date(2026, 1, 1), party_id=bapari.id,
                      weight=1, rate=1, location_id=loc.id)
    with pytest.raises(ValueError, match="used in trades"):
        admin_service.delete_lookup(session, Location, loc.id)
    # an unused one deletes fine
    loc2 = admin_service.create_lookup(session, Location, "Multan")
    admin_service.delete_lookup(session, Location, loc2.id)
    assert session.get(Location, loc2.id) is None


def test_delete_user_guards(session):
    admin = admin_service.create_user_account(
        session, username="boss", password="x", role="Admin"
    )
    # cannot delete yourself
    with pytest.raises(ValueError, match="your own account"):
        admin_service.delete_user(session, admin.id, created_by=admin.id)
    # cannot delete the last admin
    with pytest.raises(ValueError, match="last admin"):
        admin_service.delete_user(session, admin.id, created_by=None)
    # a fresh viewer deletes fine
    u = admin_service.create_user_account(session, username="v1", password="x", role="Viewer")
    admin_service.delete_user(session, u.id, created_by=admin.id)
    assert session.get(User, u.id) is None
