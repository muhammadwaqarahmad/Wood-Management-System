"""Edge cases and defensive behaviour."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import build_party_ledger, total_receivable
from timber.core.payment_service import create_payment, void_payment
from timber.core.permissions import Permission, Role, has_permission
from timber.core.reports import party_summaries
from timber.core.transaction_service import create_bapari_txn, create_combined_txn
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def test_voided_payment_excluded_from_balance(session):
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000
    )
    pay = create_payment(session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=4000)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("6000.00")
    void_payment(session, pay.id)
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("10000.00")


def test_inactive_party_excluded_from_summaries(session):
    f = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    admin_service.set_party_active(session, f.id, False)
    assert party_summaries(session, PARTY_FACTORY) == []
    assert total_receivable(session) == Decimal("0.00")


def test_bad_payment_method_rejected(session):
    p = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    with pytest.raises(ValueError, match="method"):
        create_payment(
            session, txn_date=date(2026, 1, 1), party_id=p.id, amount=100,
            method="bitcoin",
        )


def test_explicit_bad_direction_rejected(session):
    p = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    with pytest.raises(ValueError, match="direction"):
        create_payment(
            session, txn_date=date(2026, 1, 1), party_id=p.id, amount=100,
            direction="sideways",
        )


def test_combined_requires_both_loads(session):
    with pytest.raises(ValueError):
        create_combined_txn(session, bapari_txn_id=999, factory_txn_id=998)


def test_update_user_rejects_bad_role(session):
    u = admin_service.create_user_account(
        session, username="ali", password="x", role=Role.VIEWER
    )
    with pytest.raises(ValueError):
        admin_service.update_user(session, u.id, role="SuperKing")


def test_every_role_resolves_in_matrix():
    # Each declared role must have a permission set (no KeyError).
    for role in Role:
        assert isinstance(has_permission(role, Permission.VIEW_LEDGERS), bool)
