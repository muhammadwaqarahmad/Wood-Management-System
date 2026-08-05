"""Reverse-direction payments: receiving from a supplier, paying a factory.

Normally money flows one way per party type — out to a bapari, in from a
factory. But refunds happen: a supplier returns money for rejected wood, or we
refund a factory. Those rows must move the party's balance the OPPOSITE way
from a normal payment, and every consumer of the payments table has to agree
about that.

The rule under test: a payment in the party's natural direction settles what is
owed; a payment against it adds to what is owed.
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import all_party_balances, build_party_ledger, party_balance
from timber.core.payment_service import (
    create_payment,
    party_outstanding_loads,
    void_payment,
)
from timber.core.transaction_service import create_bapari_txn, create_factory_txn
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT


@pytest.fixture
def bapari(session):
    return admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)


@pytest.fixture
def factory(session):
    return admin_service.create_party(session, name="Ravi Mills",
                                      party_type=PARTY_FACTORY)


def _bapari_load(session, party, day, amount):
    return create_bapari_txn(session, txn_date=day, party_id=party.id,
                             weight=1, rate=amount)


def _factory_load(session, party, day, amount):
    return create_factory_txn(session, txn_date=day, party_id=party.id,
                              weight=1, rate=amount)


# --------------------------------------------------------------- supplier side
def test_receiving_from_supplier_raises_what_we_owe(session, bapari):
    """The case that started this: a supplier returns money.

    We owe 100,000 and have paid 30,000, so 70,000 is left. When the supplier
    hands 20,000 back, we have net paid only 10,000 — so 90,000 is owed again,
    NOT 50,000 (which is what treating it as another payment would give).
    """
    _bapari_load(session, bapari, date(2026, 1, 5), 100000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=30000, direction=PAYMENT_OUT)
    assert party_balance(session, bapari.id) == Decimal("70000.00")

    create_payment(session, txn_date=date(2026, 1, 7), party_id=bapari.id,
                   amount=20000, direction=PAYMENT_IN)
    assert party_balance(session, bapari.id) == Decimal("90000.00")


def test_supplier_refund_agrees_across_all_three_balance_paths(session, bapari):
    """party_balance, build_party_ledger and all_party_balances are three
    separate implementations of the same sum. They must not diverge."""
    _bapari_load(session, bapari, date(2026, 1, 5), 100000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=30000, direction=PAYMENT_OUT)
    create_payment(session, txn_date=date(2026, 1, 7), party_id=bapari.id,
                   amount=20000, direction=PAYMENT_IN)

    quick = party_balance(session, bapari.id)
    walked = build_party_ledger(session, bapari.id).closing_balance
    bulk = all_party_balances(session)[bapari.id]
    assert quick == walked == bulk == Decimal("90000.00")


def test_supplier_refund_unsettles_the_load(session, bapari):
    """FIFO must not keep a bill marked settled with money that came back."""
    _bapari_load(session, bapari, date(2026, 1, 5), 100000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=100000, direction=PAYMENT_OUT)
    assert party_outstanding_loads(session, bapari.id)[0].outstanding == Decimal("0.00")

    create_payment(session, txn_date=date(2026, 1, 7), party_id=bapari.id,
                   amount=25000, direction=PAYMENT_IN)
    load = party_outstanding_loads(session, bapari.id)[0]
    assert load.paid == Decimal("75000.00")
    assert load.outstanding == Decimal("25000.00")


def test_refund_larger_than_paid_never_over_allocates(session, bapari):
    """A refund bigger than everything paid must not produce negative
    allocations — the load simply goes back to fully outstanding."""
    _bapari_load(session, bapari, date(2026, 1, 5), 50000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=10000, direction=PAYMENT_OUT)
    create_payment(session, txn_date=date(2026, 1, 7), party_id=bapari.id,
                   amount=40000, direction=PAYMENT_IN)

    load = party_outstanding_loads(session, bapari.id)[0]
    assert load.paid == Decimal("0.00")
    assert load.outstanding == Decimal("50000.00")
    assert party_balance(session, bapari.id) == Decimal("80000.00")


# ---------------------------------------------------------------- factory side
def test_paying_a_factory_raises_what_they_owe(session, factory):
    """Mirror image: refunding a factory increases their outstanding."""
    _factory_load(session, factory, date(2026, 1, 5), 80000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=factory.id,
                   amount=50000, direction=PAYMENT_IN)
    assert party_balance(session, factory.id) == Decimal("30000.00")

    create_payment(session, txn_date=date(2026, 1, 7), party_id=factory.id,
                   amount=10000, direction=PAYMENT_OUT)
    assert party_balance(session, factory.id) == Decimal("40000.00")


def test_factory_refund_agrees_across_balance_paths(session, factory):
    _factory_load(session, factory, date(2026, 1, 5), 80000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=factory.id,
                   amount=50000, direction=PAYMENT_IN)
    create_payment(session, txn_date=date(2026, 1, 7), party_id=factory.id,
                   amount=10000, direction=PAYMENT_OUT)

    assert (party_balance(session, factory.id)
            == build_party_ledger(session, factory.id).closing_balance
            == all_party_balances(session)[factory.id]
            == Decimal("40000.00"))


# ------------------------------------------------------------------ regression
def test_normal_direction_behaviour_is_unchanged(session, bapari, factory):
    """The default path must behave exactly as before the change."""
    _bapari_load(session, bapari, date(2026, 1, 1), 1000)
    _bapari_load(session, bapari, date(2026, 1, 5), 2000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=1500)
    loads = party_outstanding_loads(session, bapari.id)
    assert loads[0].outstanding == Decimal("0.00")
    assert loads[1].paid == Decimal("500.00")
    assert party_balance(session, bapari.id) == Decimal("1500.00")

    _factory_load(session, factory, date(2026, 1, 1), 5000)
    create_payment(session, txn_date=date(2026, 1, 2), party_id=factory.id,
                   amount=2000)
    assert party_balance(session, factory.id) == Decimal("3000.00")


def test_direction_defaults_are_still_inferred(session, bapari, factory):
    """Callers that pass no direction keep the old behaviour."""
    p1 = create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                        amount=100)
    p2 = create_payment(session, txn_date=date(2026, 1, 6), party_id=factory.id,
                        amount=100)
    assert p1.direction == PAYMENT_OUT
    assert p2.direction == PAYMENT_IN


def test_voiding_a_refund_restores_the_balance(session, bapari):
    _bapari_load(session, bapari, date(2026, 1, 5), 100000)
    create_payment(session, txn_date=date(2026, 1, 6), party_id=bapari.id,
                   amount=30000, direction=PAYMENT_OUT)
    refund = create_payment(session, txn_date=date(2026, 1, 7), party_id=bapari.id,
                            amount=20000, direction=PAYMENT_IN)
    assert party_balance(session, bapari.id) == Decimal("90000.00")

    void_payment(session, refund.id)
    assert party_balance(session, bapari.id) == Decimal("70000.00")
