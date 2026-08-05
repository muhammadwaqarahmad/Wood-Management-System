"""Full business simulation — a week of real activity across EVERY module,
verifying the math end-to-end and the cross-module invariants:

* trades (incl. split-ledger factory + freight payers)
* payments (cash / online / cheque pending->cleared)
* expenses (business + house), transfers, loans (taken + given) + repayment
* bank balances incl. rolling "today's opening"
* party ledgers, split sub-ledger, dashboard, cash flow, financial position
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service, expense_service, loan_service
from timber.core.dashboard_service import dashboard_summary
from timber.core.ledger import detailed_party_statement, party_balance
from timber.core.payment_service import (
    clear_cheque,
    create_payment,
    cheque_balance,
)
from timber.core.position import financial_position
from timber.core.split_ledger import factory_split_statement
from timber.core.stats_service import cashflow_report
from timber.core.transaction_service import create_trade
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import METHOD_CHEQUE, METHOD_ONLINE

D = Decimal
D1 = date(2026, 7, 1)
D2 = date(2026, 7, 2)
D3 = date(2026, 7, 3)


@pytest.fixture
def world(session):
    hbl = bank_service.create_account(session, name="HBL", opening_balance=1_000_000)
    meezan = bank_service.create_account(session, name="Meezan", opening_balance=500_000)
    cash = bank_service.cash_account(session)
    cash.opening_balance = D("200000")

    s1 = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    s2 = admin_service.create_party(
        session, name="Waqar", party_type=PARTY_BAPARI,
        opening_balance=D("50000"),   # we already owe Waqar 50,000
    )
    f1 = admin_service.create_party(session, name="MORO", party_type=PARTY_FACTORY)
    f2 = admin_service.create_party(session, name="Faisal", party_type=PARTY_FACTORY)
    f2.split_rate = D("100")          # Faisal uses the split sub-ledger
    session.flush()
    return dict(hbl=hbl, meezan=meezan, cash=cash, s1=s1, s2=s2, f1=f1, f2=f2)


def _trading_week(session, w):
    """Three days of activity; every number below is hand-computed."""
    # D1 T1: Karim -> MORO. 200 md @400/450. Freight 20,000 paid by factory.
    # The supplier ALWAYS bears freight: Karim's bill = 80,000 - 20,000 =
    # 60,000; MORO fronted the driver so owes 90,000 - 20,000 = 70,000.
    create_trade(
        session, txn_date=D1, muds=200, kg=0,
        bapari_id=w["s1"].id, bapari_rate=400,
        factory_id=w["f1"].id, factory_rate=450,
        vehicle_no="T1", freight_amount=20000, freight_payer="factory",
    )

    # D1 T2: Waqar -> Faisal. 100 md @300/400 (split 100 -> right 10,000).
    create_trade(
        session, txn_date=D1, muds=100, kg=0,
        bapari_id=w["s2"].id, bapari_rate=300,
        factory_id=w["f2"].id, factory_rate=400, vehicle_no="T2",
    )
    # Waqar +30,000 (total we owe 80,000); Faisal owes 40,000.

    # D2: pay Karim 50,000 online from HBL.
    create_payment(
        session, txn_date=D2, party_id=w["s1"].id, amount=50000,
        method=METHOD_ONLINE, bank_account_id=w["hbl"].id,
    )
    # D2: MORO pays 70,000 by CHEQUE into Meezan (pending).
    chq = create_payment(
        session, txn_date=D2, party_id=w["f1"].id, amount=70000,
        method=METHOD_CHEQUE, bank_account_id=w["meezan"].id, reference_no="CH-1",
    )
    # D2: business expense 5,000 (fuel) from cash; house expense 3,000 from cash.
    expense_service.create_expense(
        session, txn_date=D2, category="fuel", amount=5000,
        bank_account_id=w["cash"].id,
    )
    expense_service.create_expense(
        session, txn_date=D2, category="rent", amount=3000, kind="house",
        bank_account_id=w["cash"].id,
    )
    # D2: transfer 100,000 HBL -> Meezan.
    bank_service.create_transfer(
        session, txn_date=D2, from_account_id=w["hbl"].id,
        to_account_id=w["meezan"].id, amount=100000,
    )
    # D3: loan taken 200,000 (Uncle -> HBL); loan given 80,000 (Bilal <- Meezan).
    loan_service.create_loan(
        session, txn_date=D3, lender_name="Uncle", amount=200000,
        bank_account_id=w["hbl"].id,
    )
    given = loan_service.create_loan(
        session, txn_date=D3, lender_name="Bilal", amount=80000,
        direction="given", bank_account_id=w["meezan"].id,
    )
    # D3: Bilal returns 30,000 into Meezan.
    loan_service.repay_loan(
        session, loan_id=given.id, txn_date=D3, amount=30000,
        bank_account_id=w["meezan"].id,
    )
    # D3: Faisal pays its weekly (left) side 20,000 online into Meezan.
    create_payment(
        session, txn_date=D3, party_id=w["f2"].id, amount=20000,
        method=METHOD_ONLINE, bank_account_id=w["meezan"].id, split_side="left",
    )
    return chq


def test_bank_balances_and_rolling_opening(session, world):
    chq = _trading_week(session, world)
    hbl, meezan, cash = world["hbl"], world["meezan"], world["cash"]

    # HBL: 1,000,000 - 50,000 (Karim) - 100,000 (transfer) + 200,000 (loan) = 1,050,000
    assert bank_service.account_balance(session, hbl.id) == D("1050000.00")
    # Meezan: 500,000 + 100,000 (transfer) - 80,000 (lent) + 30,000 (returned)
    #         + 20,000 (Faisal) = 570,000. Cheque is PENDING -> not counted.
    assert bank_service.account_balance(session, meezan.id) == D("570000.00")
    # Cash: 200,000 - 5,000 - 3,000 = 192,000
    assert bank_service.account_balance(session, cash.id) == D("192000.00")

    # Pending cheque: settles MORO but doesn't move the bank until cleared.
    assert cheque_balance(session) == D("70000.00")
    clear_cheque(session, chq.id, cleared_date=D3)
    assert bank_service.account_balance(session, meezan.id) == D("640000.00")

    # Rolling opening: D2's opening = D1's closing; changes day by day.
    assert bank_service.account_balance(session, hbl.id, before=D1) == D("1000000.00")
    assert bank_service.account_balance(session, hbl.id, before=D2) == D("1000000.00")
    assert bank_service.account_balance(session, hbl.id, before=D3) == D("850000.00")
    assert bank_service.account_balance(
        session, hbl.id, before=D3 + timedelta(days=1)
    ) == D("1050000.00")


def test_party_ledgers_and_split(session, world):
    _trading_week(session, world)

    # Karim (supplier): bill 60,000 (freight deducted), paid 50,000 ->
    # we still owe 10,000 (display negative).
    st = detailed_party_statement(session, world["s1"].id)
    assert st.closing == D("-10000.00")
    # Waqar: opening 50,000 + load 30,000 -> -80,000.
    assert detailed_party_statement(session, world["s2"].id).closing == D("-80000.00")
    # MORO: owes 70,000, paid 70,000 by (pending) cheque -> settled.
    assert detailed_party_statement(session, world["f1"].id).closing == D("0.00")
    # Faisal: owes 40,000 - 20,000 paid = 20,000.
    assert detailed_party_statement(session, world["f2"].id).closing == D("20000.00")

    # Split sub-ledger: right = 100 md x 100 = 10,000; left = 30,000 - 20,000 paid.
    split = factory_split_statement(session, world["f2"].id)
    assert split.closing_right == D("10000.00")
    assert split.closing_left == D("10000.00")
    assert split.closing_total == detailed_party_statement(
        session, world["f2"].id
    ).closing


def test_dashboard_cashflow_position_agree(session, world):
    chq = _trading_week(session, world)
    clear_cheque(session, chq.id, cleared_date=D3)

    d = dashboard_summary(session)
    c = d["cards"]
    # Flows: purchases 80,000+30,000; sales 90,000-20,000(freight)+40,000...
    # profit is gross margin: T1 (450-400)*200 - 0 fright ours = 10,000 ... freight
    # paid by factory reduces THEIR bill, not our profit; T2 (400-300)*100 = 10,000.
    assert c["purchases"] == 110000.0
    assert c["profit"] == 20000.0
    assert c["trades"] == 2
    assert c["expBusiness"] == 5000.0
    assert c["expHouse"] == 3000.0
    assert c["netProfit"] == 15000.0          # profit - business expenses

    # Position: banks 1,050,000+640,000, cash 192,000.
    assert c["bankTotal"] == 1690000.0
    assert c["cash"] == 192000.0
    assert c["available"] == 1882000.0
    # Receivable: Faisal 20,000. Payable: Karim 10,000 + Waqar 80,000.
    assert c["receivable"] == 20000.0
    assert c["payable"] == -90000.0
    assert c["loans"] == -200000.0
    assert c["loansGiven"] == 50000.0
    # Net worth = 1,882,000 + 20,000 + 50,000 - 90,000 - 200,000 = 1,662,000
    assert c["netWorth"] == 1662000.0

    # The cash-flow report's "total business worth" must agree exactly.
    assert cashflow_report(session)["worth"] == 1662000.0

    # Financial position page agrees too.
    pos = financial_position(session)
    assert float(pos.grand_total) == 1882000.0
    # receivables: Faisal 20,000 + Bilal's loan 50,000
    assert float(pos.total_receivable) == 70000.0
    # payables: Karim -10,000, Waqar -80,000, Uncle -200,000
    assert float(pos.total_payable) == -290000.0


def test_expense_stats_and_overdraft_guard(session, world):
    _trading_week(session, world)
    stats = expense_service.expense_stats(session)
    assert stats.total == D("8000.00")
    assert stats.business == D("5000.00")
    assert stats.house == D("3000.00")
    assert stats.count == 2

    # The strict rule: an account can never go negative.
    expense_service.create_expense(
        session, txn_date=D3, category="other", amount=10_000_000,
        bank_account_id=world["cash"].id,
    )
    with pytest.raises(ValueError):
        bank_service.ensure_not_overdrawn(session, world["cash"].id)
