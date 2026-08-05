"""Freight model per the client meeting:

- Profit = sale - purchase (freight NEVER affects profit).
- Supplier ALWAYS bears the freight the factory/us fronted (deducted).
- Factory fronts -> factory owes us less AND supplier owed less.
- We front -> supplier owed less. Freight is NEVER a cash transaction
  (no bank/Cash movement); it is purely a ledger deduction.
- Supplier fronts directly -> not recorded (no deduction).
- Separate supplier / factory weights.
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service, expense_service
from timber.core.ledger import build_party_ledger
from timber.core.transaction_service import create_trade
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

D = Decimal


@pytest.fixture
def parties(session):
    return {
        "bapari": admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI),
        "factory": admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY),
    }


def _trade(session, parties, **kw):
    return create_trade(
        session, txn_date=date(2026, 1, 1), muds=10, kg=0,
        bapari_id=parties["bapari"].id, bapari_rate=1000,
        factory_id=parties["factory"].id, factory_rate=1300, **kw,
    )


def test_factory_fronts_freight(session, parties):
    _trade(session, parties, freight_amount=500, freight_payer=PAYER_FACTORY)
    # supplier owed = 10,000 - 500; factory owed = 13,000 - 500; profit = 3,000
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == D("9500.00")
    assert build_party_ledger(session, parties["factory"].id).closing_balance == D("12500.00")


def test_we_front_freight(session, parties):
    cash = bank_service.cash_account(session)
    _, _, c = _trade(session, parties, freight_amount=500, freight_payer=PAYER_US)
    # supplier owed less; factory owed full; profit gross 3,000.
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == D("9500.00")
    assert build_party_ledger(session, parties["factory"].id).closing_balance == D("13000.00")
    # Freight is NOT a cash transaction — Cash stays put.
    assert bank_service.account_balance(session, cash.id) == D("0.00")
    assert c.profit == D("3000.00")
    # freight is not an expense at all
    assert expense_service.total_expenses(session, operating_only=True) == D("0.00")
    assert expense_service.total_expenses(session) == D("0.00")


def test_supplier_fronts_freight_not_recorded(session, parties):
    _trade(session, parties, freight_amount=500, freight_payer=PAYER_BAPARI)
    # supplier paid the driver directly -> no deduction, owed full 10,000
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == D("10000.00")
    assert build_party_ledger(session, parties["factory"].id).closing_balance == D("13000.00")


def test_split_factory_and_us(session, parties):
    # freight 1000: factory fronts 600, we front 400
    cash = bank_service.cash_account(session)
    _trade(session, parties, freight_amount=1000, freight_payer=PAYER_FACTORY,
           freight_payer2=PAYER_US, freight_split=600)
    # supplier owed = 10,000 - 1,000 (both fronted parts); factory = 13,000 - 600
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == D("9000.00")
    assert build_party_ledger(session, parties["factory"].id).closing_balance == D("12400.00")
    # Freight never moves Cash.
    assert bank_service.account_balance(session, cash.id) == D("0.00")


def test_separate_supplier_factory_weight(session, parties):
    # supplier 10 maund, factory re-weighed at 12 maund
    _, f, c = _trade(session, parties, factory_muds=12, factory_kg=0)
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == D("10000.00")  # 10*1000
    assert build_party_ledger(session, parties["factory"].id).closing_balance == D("15600.00")  # 12*1300
    assert c.profit == D("5600.00")  # 15600 - 10000
