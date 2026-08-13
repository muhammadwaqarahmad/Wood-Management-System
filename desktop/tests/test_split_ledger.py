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
from timber.core.split_ledger import (
    factory_split_statement,
    set_split_rates,
    split_rate_map,
    traded_wood_types,
)
from timber.core.transaction_service import create_trade
from timber.db.models import WoodType
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


# --------------------------------------------------------------------------
# Per-wood-type split rates (each wood on a factory can split differently).
# --------------------------------------------------------------------------
@pytest.fixture
def woods(session):
    kikar = WoodType(name="Kikar")
    sheesham = WoodType(name="Sheesham")
    session.add_all([kikar, sheesham])
    session.flush()
    return dict(kikar=kikar, sheesham=sheesham)


def _sell(session, world, wood, rate, muds=10):
    create_trade(
        session, txn_date=date(2026, 8, 3), muds=muds, kg=0,
        bapari_id=world["supplier"].id, bapari_rate=300,
        factory_id=world["factory"].id, factory_rate=rate,
        wood_type_id=wood.id,
    )


def test_per_wood_split_rates(session, world, woods):
    """Two wood types on ONE factory split at their own rates (rate 430)."""
    f = world["factory"]
    f.split_rate = D("0")  # enrolled; per-wood rates drive the split now
    set_split_rates(session, f.id, {
        woods["kikar"].id: D("100"), woods["sheesham"].id: D("150")})
    session.flush()
    _sell(session, world, woods["kikar"], 430)
    _sell(session, world, woods["sheesham"], 430)

    st = factory_split_statement(session, f.id)
    by = {e.wood: e for e in st.entries if e.kind == "load"}
    # Kikar: split 100 -> right 1,000 ; left (430-100)×10 = 3,300
    assert by["Kikar"].right_rate == D("100.00")
    assert by["Kikar"].right_amount == D("1000.00")
    assert by["Kikar"].left_net == D("3300.00")
    # Sheesham: split 150 -> right 1,500 ; left (430-150)×10 = 2,800
    assert by["Sheesham"].right_rate == D("150.00")
    assert by["Sheesham"].right_amount == D("1500.00")
    assert by["Sheesham"].left_net == D("2800.00")
    # Combined sub-ledger still equals the main factory ledger.
    main = detailed_party_statement(session, f.id)
    assert st.closing_total == main.closing


def test_unconfigured_wood_gets_no_split(session, world, woods):
    """A wood type with no configured rate stays 100% weekly."""
    f = world["factory"]
    f.split_rate = D("0")
    set_split_rates(session, f.id, {woods["kikar"].id: D("100")})
    session.flush()
    _sell(session, world, woods["sheesham"], 430)  # sheesham has no rate

    (load,) = factory_split_statement(session, f.id).entries
    assert load.right_amount == D("0.00")
    assert load.left_net == D("4300.00")           # whole rate weekly


def test_set_split_rates_zero_removes_row(session, world, woods):
    f = world["factory"]
    f.split_rate = D("0")
    set_split_rates(session, f.id, {woods["kikar"].id: D("100")})
    session.flush()
    assert split_rate_map(session, f.id) == {woods["kikar"].id: D("100.00")}
    # 0 means "no split" — the row is removed.
    set_split_rates(session, f.id, {woods["kikar"].id: D("0")})
    session.flush()
    assert split_rate_map(session, f.id) == {}


def test_traded_wood_types_lists_only_traded(session, world, woods):
    f = world["factory"]
    _sell(session, world, woods["kikar"], 400, muds=5)  # only Kikar traded
    assert traded_wood_types(session, f.id) == [(woods["kikar"].id, "Kikar")]
