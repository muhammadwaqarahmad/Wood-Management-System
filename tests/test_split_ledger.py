"""Factory split sub-ledger — reproduces the client's two-sided Excel:
each load's factory rate splits into a RIGHT side (split_rate × weight,
cleared irregularly) and a LEFT side (remaining rate × weight minus the
factory-paid freight, cleared weekly). The sides always sum to the main
factory ledger's gross.
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import detailed_party_statement
from timber.core.payment_service import create_payment
from timber.core.split_ledger import factory_split_statement
from timber.core.transaction_service import create_trade
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

D = Decimal


@pytest.fixture
def world(session):
    supplier = admin_service.create_party(
        session, name="Chaudhry Sattar", party_type=PARTY_BAPARI
    )
    factory = admin_service.create_party(
        session, name="MORO", party_type=PARTY_FACTORY
    )
    factory.split_rate = D("250")
    session.flush()
    return dict(supplier=supplier, factory=factory)


def test_split_matches_client_sheet(session, world):
    """Client's row: 459.75 maunds, factory rate 670 = 250 (right/Karachi)
    + 420 (left/factory), freight 56,675 paid by the factory."""
    create_trade(
        session, txn_date=date(2026, 6, 18),
        muds=D("459.75"), kg=0,
        bapari_id=world["supplier"].id, bapari_rate=400,
        factory_id=world["factory"].id, factory_rate=670,
        vehicle_no="735",
        freight_amount=56675, freight_payer="factory",
    )
    st = factory_split_statement(session, world["factory"].id)
    (load,) = st.entries

    # Right (irregular) side: 459.75 × 250 = 114,937.50
    assert load.right_rate == D("250.00")
    assert load.right_amount == D("114937.50")
    assert load.right_balance == D("114937.50")

    # Left (weekly) side: 459.75 × 420 = 193,095 − 56,675 = 136,420
    assert load.left_rate == D("420.00")
    assert load.left_total == D("193095.00")
    assert load.freight == D("-56675.00")     # deduction
    assert load.left_net == D("136420.00")
    assert load.left_balance == D("136420.00")

    # The two sides together = the main factory ledger's gross.
    main = detailed_party_statement(session, world["factory"].id)
    assert st.closing_total == main.closing


def test_payments_settle_their_side(session, world):
    create_trade(
        session, txn_date=date(2026, 6, 18),
        muds=100, kg=0,
        bapari_id=world["supplier"].id, bapari_rate=300,
        factory_id=world["factory"].id, factory_rate=400,
    )
    # weight 100 × rate 400: right = 25,000 (250), left = 15,000 (150).
    # The factory clears the weekly (left) side...
    create_payment(
        session, txn_date=date(2026, 6, 20),
        party_id=world["factory"].id, amount=15000, split_side="left",
    )
    # ...and later part of the irregular (right) side.
    create_payment(
        session, txn_date=date(2026, 7, 1),
        party_id=world["factory"].id, amount=10000, split_side="right",
    )
    st = factory_split_statement(session, world["factory"].id)
    assert st.closing_left == D("0.00")
    assert st.closing_right == D("15000.00")
    assert st.paid_left == D("15000.00")
    assert st.paid_right == D("10000.00")
    # Main ledger agrees with the combined sub-ledger.
    main = detailed_party_statement(session, world["factory"].id)
    assert st.closing_total == main.closing


def test_split_rate_capped_at_factory_rate(session, world):
    """A load cheaper than the split rate: the right side takes the whole
    rate, the left side gets zero (never negative)."""
    world["factory"].split_rate = D("500")
    session.flush()
    create_trade(
        session, txn_date=date(2026, 6, 18),
        muds=10, kg=0,
        bapari_id=world["supplier"].id, bapari_rate=300,
        factory_id=world["factory"].id, factory_rate=400,
    )
    st = factory_split_statement(session, world["factory"].id)
    (load,) = st.entries
    assert load.right_rate == D("400.00")   # capped at the factory rate
    assert load.right_amount == D("4000.00")
    assert load.left_total == D("0.00")
    assert load.left_net == D("0.00")


def test_no_split_rate_means_all_left(session, world):
    world["factory"].split_rate = None
    session.flush()
    create_trade(
        session, txn_date=date(2026, 6, 18),
        muds=50, kg=0,
        bapari_id=world["supplier"].id, bapari_rate=300,
        factory_id=world["factory"].id, factory_rate=400,
    )
    st = factory_split_statement(session, world["factory"].id)
    (load,) = st.entries
    assert load.right_amount == D("0.00")
    assert load.left_net == D("20000.00")
    assert st.closing_right == D("0.00")
