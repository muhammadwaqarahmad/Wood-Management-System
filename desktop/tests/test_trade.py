"""Tests for the locked buy+sell trade flow (muds/kg + expense payers)."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.transaction_service import create_trade
from timber.db.models import BapariTxn, CombinedTxn, FactoryTxn
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def parties(session):
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    return bapari, factory


def test_trade_creates_all_three_records(session, parties):
    bapari, factory = parties
    b, f, c = create_trade(
        session,
        txn_date=date(2026, 1, 1),
        muds=10, kg=0,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1300,
        vehicle_no="LEA-1",
        freight_amount=500, freight_payer=PAYER_US,  # we front -> deducted from supplier
    )
    assert session.query(BapariTxn).count() == 1
    assert session.query(FactoryTxn).count() == 1
    assert session.query(CombinedTxn).count() == 1
    assert b.muds == f.muds == Decimal("10.00")
    assert b.weight == Decimal("10.000")              # buy: maunds only
    assert f.weight == Decimal("10.000")              # sale: 10 + 0/40
    # Supplier's freight share is DEDUCTED from what we owe them (matches
    # the manual ledger: bill = weight*rate - freight).
    assert b.freight == Decimal("-500.00")
    assert f.freight == Decimal("0.00")
    assert c.freight_amount == Decimal("500.00")       # recorded who paid
    # supplier owed = 10,000 - 500 freight = 9,500
    from timber.core.ledger import build_party_ledger
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("9500.00")
    # profit uses gross bills (freight is a pass-through): 13000 - 10000 = 3000
    assert c.profit == Decimal("3000.00")


def test_kg_counts_in_muds_terms(session, parties):
    bapari, factory = parties
    b, f, c = create_trade(
        session, txn_date=date(2026, 1, 1), muds=100, kg=20,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1000,
    )
    # kg counts on BOTH sides now (muds terms): 100 + 20/40 = 100.5
    assert b.weight == Decimal("100.500")
    assert f.weight == Decimal("100.500")
    # same rate, same weight -> no margin
    assert c.profit == Decimal("0.00")


def test_separate_weights_with_kg(session, parties):
    bapari, factory = parties
    # supplier 100 mud 20 kg (=100.5), factory re-weighed 100 mud 0 kg
    b, f, c = create_trade(
        session, txn_date=date(2026, 1, 1), muds=100, kg=20,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1000, factory_muds=100, factory_kg=0,
    )
    assert b.weight == Decimal("100.500")
    assert f.weight == Decimal("100.000")
    assert c.profit == Decimal("-500.00")  # 100000 - 100500


def test_expense_payers(session, parties):
    bapari, factory = parties
    _, _, c = create_trade(
        session, txn_date=date(2026, 1, 1), muds=10,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1300,
        loading_amount=200, loading_payer=PAYER_US,
        freight_amount=300, freight_payer=PAYER_BAPARI,
        unloading_amount=100, unloading_payer=PAYER_FACTORY,
    )
    # Per-trade profit is the gross margin (13000 - 10000 = 3000). Supplier's
    # 300 is deducted from their bill, factory's 100 added to theirs, and our
    # 200 becomes a real expense (reduces cash + Net Profit).
    assert c.own_expense == Decimal("200.00")
    assert c.profit == Decimal("3000.00")


def test_trade_is_atomic_on_bad_factory(session, parties):
    bapari, _ = parties
    with pytest.raises(ValueError):
        create_trade(
            session, txn_date=date(2026, 1, 1), muds=10,
            bapari_id=bapari.id, bapari_rate=1000,
            factory_id=bapari.id, factory_rate=1300,  # wrong type
        )
    session.rollback()
    assert session.query(BapariTxn).count() == 0
    assert session.query(FactoryTxn).count() == 0
    assert session.query(CombinedTxn).count() == 0


def test_trade_with_full_settlement(session, parties):
    from timber.core import bank_service
    from timber.core.ledger import build_party_ledger
    from timber.core.payment_service import create_payment
    from timber.db.models.payment import METHOD_ONLINE

    bapari, factory = parties
    acct = bank_service.create_account(session, name="HBL", opening_balance=0)
    create_trade(
        session, txn_date=date(2026, 1, 1), muds=10,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1300,
        freight_amount=500, freight_payer=PAYER_US,  # we front -> deducted from supplier
    )
    payable = Decimal("9500.00")     # 10*1000 - 500 freight (deducted from supplier)
    receivable = Decimal("13000.00")  # 10*1300

    create_payment(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, amount=payable,
        method=METHOD_ONLINE, bank_account_id=acct.id,
    )
    create_payment(
        session, txn_date=date(2026, 1, 1), party_id=factory.id, amount=receivable,
        method=METHOD_ONLINE, bank_account_id=acct.id,
    )

    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("0.00")
    assert build_party_ledger(session, factory.id).closing_balance == Decimal("0.00")
    # received 13,000 - paid 9,500 = 3,500
    assert bank_service.account_balance(session, acct.id) == Decimal("3500.00")


def test_void_trade_cascades_everywhere(session, parties):
    from timber.core.dashboard import dashboard_cards
    from timber.core.ledger import build_party_ledger
    from timber.core.reports import list_trades
    from timber.core.transaction_service import void_trade

    bapari, factory = parties
    _, _, combined = create_trade(
        session, txn_date=date(2026, 1, 1), muds=10,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1300,
    )
    # before: balances + trade exist
    assert build_party_ledger(session, factory.id).closing_balance == Decimal("13000.00")
    assert len(list_trades(session)) == 1

    void_trade(session, combined.id)

    # after: ledgers, trades and dashboard all reflect the removal
    assert build_party_ledger(session, factory.id).closing_balance == Decimal("0.00")
    assert build_party_ledger(session, bapari.id).closing_balance == Decimal("0.00")
    assert list_trades(session) == []
    cards = dashboard_cards(session)
    assert cards.receivable == Decimal("0.00")
    assert cards.total_profit == Decimal("0.00")


def test_update_trade_recomputes(session, parties):
    from timber.core.ledger import build_party_ledger
    from timber.core.transaction_service import update_trade

    bapari, factory = parties
    _, _, combined = create_trade(
        session, txn_date=date(2026, 1, 1), muds=10,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1200,
    )
    assert combined.profit == Decimal("2000.00")

    update_trade(
        session, combined.id, txn_date=date(2026, 1, 2), muds=10,
        bapari_id=bapari.id, bapari_rate=1000,
        factory_id=factory.id, factory_rate=1500,  # corrected sell rate
    )
    assert session.get(type(combined), combined.id).profit == Decimal("5000.00")
    assert build_party_ledger(session, factory.id).closing_balance == Decimal("15000.00")


def test_only_admin_manager_can_edit_trade():
    from timber.core.permissions import Permission, Role, has_permission

    assert has_permission(Role.ADMIN, Permission.EDIT_TRADE)
    assert has_permission(Role.MANAGER, Permission.EDIT_TRADE)
    assert not has_permission(Role.DATA_ENTRY, Permission.EDIT_TRADE)
    assert not has_permission(Role.ACCOUNTANT, Permission.EDIT_TRADE)


def test_trade_rejects_bad_weight(session, parties):
    bapari, factory = parties
    with pytest.raises(ValueError, match="Maunds"):
        create_trade(
            session, txn_date=date(2026, 1, 1), muds=0,
            bapari_id=bapari.id, bapari_rate=1000,
            factory_id=factory.id, factory_rate=1300,
        )
