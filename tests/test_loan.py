"""Loans: borrowing adds cash to an account, repaying takes it out;
outstanding = principal - repayments."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import bank_service, loan_service

D = Decimal


@pytest.fixture
def hbl(session):
    return bank_service.create_account(session, name="HBL", opening_balance=100000)


def test_borrow_adds_cash(session, hbl):
    loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Uncle",
        amount=50000, bank_account_id=hbl.id,
    )
    # 100,000 opening + 50,000 borrowed = 150,000
    assert bank_service.account_balance(session, hbl.id) == D("150000.00")
    assert loan_service.total_loans_outstanding(session) == D("50000.00")


def test_repay_takes_cash_out(session, hbl):
    loan = loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Uncle",
        amount=50000, bank_account_id=hbl.id,
    )
    loan_service.repay_loan(
        session, loan_id=loan.id, txn_date=date(2026, 2, 1),
        amount=20000, bank_account_id=hbl.id,
    )
    # 150,000 - 20,000 repaid = 130,000
    assert bank_service.account_balance(session, hbl.id) == D("130000.00")
    assert loan_service.loan_outstanding(session, loan.id) == D("30000.00")
    assert loan_service.total_loans_outstanding(session) == D("30000.00")


def test_cannot_overpay_loan(session, hbl):
    loan = loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Uncle",
        amount=50000, bank_account_id=hbl.id,
    )
    with pytest.raises(ValueError):
        loan_service.repay_loan(
            session, loan_id=loan.id, txn_date=date(2026, 2, 1),
            amount=60000, bank_account_id=hbl.id,
        )


def test_list_and_delete_loan(session, hbl):
    loan = loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Friend",
        amount=30000, bank_account_id=hbl.id,
    )
    assert len(loan_service.list_loans(session)) == 1
    loan_service.delete_loan(session, loan.id)
    assert loan_service.list_loans(session) == []
    # cash back to opening
    assert bank_service.account_balance(session, hbl.id) == D("100000.00")


# ---------------------------------------------------------------- #
# Loans GIVEN: we lend money out — cash leaves the account, their   #
# repayments bring it back; outstanding = what they still owe us.   #
# ---------------------------------------------------------------- #
def test_given_loan_takes_cash_out(session, hbl):
    loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Bilal",
        amount=40000, direction="given", bank_account_id=hbl.id,
    )
    # 100,000 opening - 40,000 lent out = 60,000
    assert bank_service.account_balance(session, hbl.id) == D("60000.00")
    # Taken total unchanged; given outstanding tracked separately.
    assert loan_service.total_loans_outstanding(session) == D("0.00")
    assert loan_service.total_loans_outstanding(session, "given") == D("40000.00")


def test_given_loan_repayment_brings_cash_back(session, hbl):
    loan = loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Bilal",
        amount=40000, direction="given", bank_account_id=hbl.id,
    )
    loan_service.repay_loan(
        session, loan_id=loan.id, txn_date=date(2026, 2, 1),
        amount=15000, bank_account_id=hbl.id,
    )
    # 60,000 + 15,000 returned = 75,000
    assert bank_service.account_balance(session, hbl.id) == D("75000.00")
    assert loan_service.loan_outstanding(session, loan.id) == D("25000.00")
    assert loan_service.total_loans_outstanding(session, "given") == D("25000.00")


def test_loans_in_net_worth_and_cashflow(session, hbl):
    """Given loans count as receivable, taken loans as giveable, in the
    dashboard net worth and the cash-flow statement."""
    from timber.core.dashboard_service import dashboard_summary
    from timber.core.stats_service import cashflow_report

    loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Uncle",
        amount=50000, bank_account_id=hbl.id,          # taken
    )
    loan_service.create_loan(
        session, txn_date=date(2026, 1, 2), lender_name="Bilal",
        amount=20000, direction="given", bank_account_id=hbl.id,
    )
    d = dashboard_summary(session)
    assert d["cards"]["loans"] == -50000.0        # we must repay
    assert d["cards"]["loansGiven"] == 20000.0    # they owe us
    # bank: 100,000 + 50,000 - 20,000 = 130,000; net worth:
    # 130,000 (available) + 20,000 (given) - 50,000 (taken) = 100,000
    assert d["cards"]["available"] == 130000.0
    assert d["cards"]["netWorth"] == 100000.0

    cf = cashflow_report(session)
    rows = {r["key"]: r for r in cf["rows"]}
    assert rows["loans"]["amount"] == 50000.0 and rows["loans"]["sign"] == -1
    assert rows["loans_given"]["amount"] == 20000.0 and rows["loans_given"]["sign"] == 1
    assert rows["worth"]["amount"] == 100000.0


def test_given_loan_in_financial_position(session, hbl):
    from timber.core.position import financial_position

    loan_service.create_loan(
        session, txn_date=date(2026, 1, 1), lender_name="Bilal",
        amount=20000, direction="given", bank_account_id=hbl.id,
    )
    pos = financial_position(session)
    loan_recv = [r for r in pos.receivables if r.kind == "loan"]
    assert len(loan_recv) == 1
    assert loan_recv[0].name == "Bilal"
    assert loan_recv[0].amount == D("20000.00")
