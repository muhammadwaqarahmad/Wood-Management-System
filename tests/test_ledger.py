"""Tests for running balances and the firm-wide position."""

from datetime import date
from decimal import Decimal

from timber.core.calculations import apply_txn_totals
from timber.core.ledger import (
    build_party_ledger,
    net_position,
    total_payable,
    total_receivable,
)
from timber.db.models import BapariTxn, FactoryTxn, Party, Payment
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT


def _add_txn(session, model, party_id, day, weight, rate, freight=0):
    txn = model(
        txn_date=date(2026, 1, day),
        party_id=party_id,
        weight=Decimal(str(weight)),
        rate=Decimal(str(rate)),
        freight=Decimal(str(freight)),
    )
    apply_txn_totals(txn)  # fills bill + net_amount
    session.add(txn)
    session.flush()
    return txn


def _add_payment(session, party_id, day, amount, direction):
    pay = Payment(
        txn_date=date(2026, 1, day),
        party_id=party_id,
        direction=direction,
        amount=Decimal(str(amount)),
    )
    session.add(pay)
    session.flush()
    return pay


def test_bapari_running_balance(session):
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add(bapari)
    session.flush()

    _add_txn(session, BapariTxn, bapari.id, 1, weight=10, rate=1000, freight=500)
    _add_payment(session, bapari.id, 5, 4000, PAYMENT_OUT)
    _add_txn(session, BapariTxn, bapari.id, 10, weight=5, rate=1200)

    ledger = build_party_ledger(session, bapari.id)

    # 0 + 10500 = 10500 ; -4000 = 6500 ; +6000 = 12500
    balances = [e.balance for e in ledger.entries]
    assert balances == [
        Decimal("10500.00"),
        Decimal("6500.00"),
        Decimal("12500.00"),
    ]
    assert ledger.closing_balance == Decimal("12500.00")


def test_opening_balance_is_starting_point(session):
    bapari = Party(
        name="Saleem", party_type=PARTY_BAPARI, opening_balance=Decimal("2000.00")
    )
    session.add(bapari)
    session.flush()

    _add_txn(session, BapariTxn, bapari.id, 1, weight=1, rate=1000)  # +1000

    ledger = build_party_ledger(session, bapari.id)
    assert ledger.opening_balance == Decimal("2000.00")
    assert ledger.closing_balance == Decimal("3000.00")


def test_void_txn_excluded(session):
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add(bapari)
    session.flush()

    _add_txn(session, BapariTxn, bapari.id, 1, weight=10, rate=1000)
    voided = _add_txn(session, BapariTxn, bapari.id, 2, weight=10, rate=1000)
    voided.is_void = True
    session.flush()

    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("10000.00")


def test_firm_position(session):
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    factory = Party(name="ABC Factory", party_type=PARTY_FACTORY)
    session.add_all([bapari, factory])
    session.flush()

    # Owe bapari 12,500
    _add_txn(session, BapariTxn, bapari.id, 1, weight=10, rate=1000, freight=500)
    _add_txn(session, BapariTxn, bapari.id, 2, weight=5, rate=1200)
    _add_payment(session, bapari.id, 3, 4000, PAYMENT_OUT)  # 10500+6000-4000

    # Factory owes us 8,000
    _add_txn(session, FactoryTxn, factory.id, 1, weight=10, rate=1300)
    _add_payment(session, factory.id, 2, 5000, PAYMENT_IN)  # 13000-5000

    assert total_payable(session) == Decimal("12500.00")
    assert total_receivable(session) == Decimal("8000.00")
    assert net_position(session) == Decimal("-4500.00")
