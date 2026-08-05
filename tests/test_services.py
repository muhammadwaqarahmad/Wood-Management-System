"""Tests for the Phase 3 service layer (create/void txns & payments)."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core.payment_service import create_payment
from timber.core.transaction_service import (
    create_bapari_txn,
    create_combined_txn,
    create_factory_txn,
    void_txn,
)
from timber.db.models import AuditLog, BapariTxn, Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT


@pytest.fixture
def bapari(session):
    p = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add(p)
    session.flush()
    return p


@pytest.fixture
def factory(session):
    p = Party(name="ABC Factory", party_type=PARTY_FACTORY)
    session.add(p)
    session.flush()
    return p


def test_create_bapari_txn_computes_totals(session, bapari):
    txn = create_bapari_txn(
        session,
        txn_date=date(2026, 1, 1),
        party_id=bapari.id,
        weight=10,
        rate=1000,
        freight=500,
        loading=200,
    )
    assert txn.bill == Decimal("10000.00")
    assert txn.net_amount == Decimal("10700.00")


def test_create_writes_audit_log(session, bapari):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=1
    )
    logs = session.query(AuditLog).all()
    assert len(logs) == 1
    assert logs[0].action == "create"
    assert logs[0].entity == "bapari_txns"


def test_weight_must_be_positive(session, bapari):
    with pytest.raises(ValueError, match="Weight"):
        create_bapari_txn(
            session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=0, rate=1000
        )


def test_negative_rate_rejected(session, bapari):
    with pytest.raises(ValueError, match="Rate"):
        create_bapari_txn(
            session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=-5
        )


def test_wrong_party_type_rejected(session, factory):
    # Passing a factory where a bapari is expected.
    with pytest.raises(ValueError, match="bapari"):
        create_bapari_txn(
            session, txn_date=date(2026, 1, 1), party_id=factory.id, weight=1, rate=1
        )


def test_void_txn(session, bapari):
    txn = create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=1
    )
    void_txn(session, BapariTxn, txn.id, created_by=None)
    assert session.get(BapariTxn, txn.id).is_void is True


def test_create_payment_infers_direction(session, bapari, factory):
    out = create_payment(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, amount=500
    )
    inn = create_payment(
        session, txn_date=date(2026, 1, 1), party_id=factory.id, amount=500
    )
    assert out.direction == PAYMENT_OUT
    assert inn.direction == PAYMENT_IN


def test_payment_amount_must_be_positive(session, bapari):
    with pytest.raises(ValueError, match="Amount"):
        create_payment(
            session, txn_date=date(2026, 1, 1), party_id=bapari.id, amount=0
        )


def test_list_payments_by_type(session, bapari, factory):
    from timber.core.payment_service import list_payments

    create_payment(session, txn_date=date(2026, 1, 1), party_id=factory.id, amount=5000)
    create_payment(session, txn_date=date(2026, 1, 2), party_id=bapari.id, amount=3000)
    factory_rows = list_payments(session, PARTY_FACTORY)
    bapari_rows = list_payments(session, PARTY_BAPARI)
    assert len(factory_rows) == 1 and factory_rows[0].party_name == "ABC Factory"
    assert len(bapari_rows) == 1 and bapari_rows[0].party_name == "Karim"


def test_create_combined_computes_profit(session, bapari, factory):
    b = create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000
    )
    f = create_factory_txn(
        session, txn_date=date(2026, 1, 2), party_id=factory.id, weight=10, rate=1200
    )
    combined = create_combined_txn(
        session, bapari_txn_id=b.id, factory_txn_id=f.id
    )
    # (1200 - 1000) * 10 = 2000
    assert combined.profit == Decimal("2000.00")
