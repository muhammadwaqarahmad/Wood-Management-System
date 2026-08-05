"""Full end-to-end reconciliation: bank accounts (with opening balances),
parties, single + mixed + split-expense trades, payments (incl. an
opening-balance factory), expenses and a transfer — then verify every
balance, the dashboard cards, the trade ledger and the FIFO paid status.
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service
from timber.core.dashboard import collected_profit, dashboard_cards
from timber.core.ledger import build_party_ledger, detailed_party_statement
from timber.core.payment_service import create_payment, party_outstanding_loads
from timber.core.reports import trade_ledger
from timber.core.transaction_service import (
    WoodLine,
    create_mixed_trade,
    create_trade,
)
from timber.db.models.combined_txn import PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

D = Decimal


@pytest.fixture
def world(session):
    hbl = bank_service.create_account(session, name="HBL", opening_balance=1_000_000)
    s1 = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    f1 = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY, credit_days=30)
    f2 = admin_service.create_party(
        session, name="XYZ", party_type=PARTY_FACTORY, opening_balance=200_000
    )
    session.flush()

    # T1 single, freight 500 paid by us
    create_trade(
        session, txn_date=date(2026, 1, 1), muds=10, kg=0,
        bapari_id=s1.id, bapari_rate=1000, factory_id=f1.id, factory_rate=1300,
        freight_amount=500, freight_payer=PAYER_US,
    )
    # T2 mixed (2 lines), freight 1000 split: us 400 / factory 600
    create_mixed_trade(
        session, txn_date=date(2026, 1, 2), bapari_id=s1.id, factory_id=f1.id,
        lines=[WoodLine(None, 5, 0, 1000, 1200), WoodLine(None, 3, 0, 900, 1100)],
        freight_amount=1000, freight_payer=PAYER_US,
        freight_payer2=PAYER_FACTORY, freight_split=400,
    )
    # T3 single to the opening-balance factory, no expenses
    create_trade(
        session, txn_date=date(2026, 1, 3), muds=4, kg=0,
        bapari_id=s1.id, bapari_rate=1000, factory_id=f2.id, factory_rate=1250,
    )

    # Payments
    create_payment(session, txn_date=date(2026, 1, 10), party_id=s1.id, amount=20_000,
                   bank_account_id=hbl.id, method="bank")
    create_payment(session, txn_date=date(2026, 1, 11), party_id=f1.id, amount=15_000,
                   bank_account_id=hbl.id, method="bank")
    create_payment(session, txn_date=date(2026, 1, 12), party_id=f2.id, amount=200_000,
                   bank_account_id=hbl.id, method="bank")

    # Expense + transfer
    from timber.core import expense_service
    expense_service.create_expense(session, txn_date=date(2026, 1, 13), category="rent",
                                   amount=3_000, bank_account_id=hbl.id)
    cash = bank_service.cash_account(session)
    bank_service.create_transfer(session, txn_date=date(2026, 1, 14),
                                 from_account_id=hbl.id, to_account_id=cash.id, amount=50_000)
    session.flush()
    return {"hbl": hbl, "cash": cash, "s1": s1, "f1": f1, "f2": f2}


def test_party_balances(world, session):
    # supplier owes = 21,700 purchases - 1,500 freight (T1 500 + T2 1000, borne
    # by supplier) - 20,000 paid = 200
    assert build_party_ledger(session, world["s1"].id).closing_balance == D("200.00")
    # F1 owes = 22,300 sales - 600 factory-fronted freight (T2) - 15,000 = 6,700
    assert build_party_ledger(session, world["f1"].id).closing_balance == D("6700.00")
    # F2 owes = opening 200,000 + sale 5,000 - received 200,000 = 5,000
    assert build_party_ledger(session, world["f2"].id).closing_balance == D("5000.00")


def test_bank_balances(world, session):
    # 1,000,000 -20,000 +15,000 +200,000 -3,000 -50,000 = 1,142,000
    assert bank_service.account_balance(session, world["hbl"].id) == D("1142000.00")
    # Cash: +50,000 transfer in only. Freight is NOT a cash transaction —
    # it's a supplier/factory ledger deduction, so it never touches Cash.
    assert bank_service.account_balance(session, world["cash"].id) == D("50000.00")
    assert bank_service.total_cash_position(session) == D("1192000.00")


def test_opening_balance_payment_does_not_mark_load_paid(world, session):
    # The 200,000 payment clears F2's opening debt FIRST, so the new 5,000
    # sale must still be UNPAID (this was the reported bug).
    loads = party_outstanding_loads(session, world["f2"].id)
    assert len(loads) == 1
    assert loads[0].paid == D("0.00")
    assert loads[0].outstanding == D("5000.00")


def test_dashboard_cards(world, session):
    c = dashboard_cards(session)
    assert c.receivable == D("11700.00")     # F1 6,700 + F2 5,000
    assert c.payable == D("200.00")          # supplier
    assert c.net == D("11500.00")
    # gross margins: T1 3000 + T2 (1000+600) + T3 1000 = 5600
    assert c.total_profit == D("5600.00")
    assert c.cash_in == D("215000.00")       # 15,000 + 200,000
    assert c.cash_out == D("20000.00")
    # collected: T1 full (3000) + T2 line1 (2000/5400 of 1000) + rest 0
    assert collected_profit(session) == D("3370.37")


def test_trade_ledger_totals(world, session):
    rows, purchase, sale, profit = trade_ledger(session)
    assert purchase == D("21700.00")
    assert sale == D("27300.00")
    assert profit == D("5600.00")  # gross margins
    assert len(rows) == 4  # 4 wood lines (T1, T2x2, T3)


def test_ledger_shows_who_paid_freight(world, session):
    # A party's ledger shows ONLY the freight that party paid. On T2 the
    # freight split is: we pay 400, the factory pays the 600 rest -> the
    # factory ledger shows its 600 share and NOT our 400.
    st = detailed_party_statement(session, world["f1"].id)
    freight_rows = [e for e in st.entries
                    if e.kind == "load" and "600.00" in e.expenses]
    assert freight_rows, "factory's freight share not shown in its ledger"
    assert "400.00" not in freight_rows[0].expenses  # our share stays out


def test_split_expense_recorded(world, session):
    # The freight split on T2 is stored and only our 400 share hit profit.
    rows, *_ = trade_ledger(session)
    t2 = [r for r in rows if r.freight == D("1000.00")]
    assert t2, "T2 freight row not found"
    r = t2[0]
    assert r.freight_payer == PAYER_US
    assert r.freight_payer2 == PAYER_FACTORY
    assert r.freight_split == D("400.00")
