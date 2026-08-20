"""Bank book — daily continuity and per-transaction statement."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import bank_service
from timber.core.bank_ledger import bank_daily_book, bank_statement
from timber.db.models import BankAccount, Expense, Party, Payment
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import (
    CHEQUE_CLEARED,
    CHEQUE_PENDING,
    METHOD_CHEQUE,
    PAYMENT_IN,
    PAYMENT_OUT,
)


@pytest.fixture
def account_with_activity(session):
    acct = BankAccount(name="HBL", opening_balance=Decimal("1000.00"))
    factory = Party(name="ABC", party_type=PARTY_FACTORY)
    bapari = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add_all([acct, factory, bapari])
    session.flush()

    # Day 1: receive 500 from a factory.
    session.add(Payment(
        txn_date=date(2026, 1, 1), party_id=factory.id, direction=PAYMENT_IN,
        amount=Decimal("500.00"), method="online", bank_account_id=acct.id,
    ))
    # Day 2: pay 300 to a bapari + a 200 expense.
    session.add(Payment(
        txn_date=date(2026, 1, 2), party_id=bapari.id, direction=PAYMENT_OUT,
        amount=Decimal("300.00"), method="online", bank_account_id=acct.id,
    ))
    session.add(Expense(
        txn_date=date(2026, 1, 2), category="rent", amount=Decimal("200.00"),
        bank_account_id=acct.id,
    ))
    session.flush()
    return acct


def test_daily_book_continuity(session, account_with_activity):
    book = bank_daily_book(session, account_with_activity.id)
    assert len(book.rows) == 2
    d1, d2 = book.rows  # oldest day first
    # Day 1: 1000 + 500 = 1500
    assert d1.opening == Decimal("1000.00")
    assert d1.money_in == Decimal("500.00")
    assert d1.closing == Decimal("1500.00")
    # Day 2 opening MUST equal day 1 closing (the client's requirement)
    assert d2.opening == d1.closing == Decimal("1500.00")
    # Day 2: 1500 - 300 - 200 = 1000
    assert d2.money_out == Decimal("500.00")
    assert d2.closing == Decimal("1000.00")


def test_statement_running_balance(session, account_with_activity):
    st = bank_statement(session, account_with_activity.id)
    assert st.opening == Decimal("1000.00")
    # Oldest first: balances run from earliest to latest.
    assert [e.balance for e in st.entries] == [
        Decimal("1500.00"), Decimal("1200.00"), Decimal("1000.00"),
    ]
    assert st.total_in == Decimal("500.00")
    assert st.total_out == Decimal("500.00")
    assert st.closing == Decimal("1000.00")
    # From / To (where money came from and went to) — oldest first.
    e_in, e_pay, e_exp = st.entries
    assert (e_in.source, e_in.destination) == ("ABC", "HBL")        # factory -> us
    assert (e_pay.source, e_pay.destination) == ("HBL", "Karim")    # us -> supplier
    assert e_exp.source == "HBL" and e_exp.destination.endswith("rent")


def test_statement_date_filter_folds_opening(session, account_with_activity):
    # Filtering to day 2 only: day-1 activity folds into the opening.
    st = bank_statement(
        session, account_with_activity.id,
        start=date(2026, 1, 2), end=date(2026, 1, 2),
    )
    assert st.opening == Decimal("1500.00")  # 1000 + 500 from day 1
    assert st.closing == Decimal("1000.00")
    assert len(st.entries) == 2


def test_uncleared_cheque_hidden_until_cleared(session):
    """An uncleared cheque must NOT hit the bank book — the same rule the
    Dashboard / Bank Accounts balance uses (all_account_balances) — so the two
    never drift. Regression for the client's Habib Metro Kashif case, where the
    bank book (which used to count the uncleared cheque) read lower than the
    dashboard by exactly that cheque's amount."""
    acct = BankAccount(name="Habib Metro Kashif", opening_balance=Decimal("7182.00"))
    bapari = Party(name="New Ameer Khan Chang", party_type=PARTY_BAPARI)
    session.add_all([acct, bapari])
    session.flush()
    session.add(Payment(   # cash in
        txn_date=date(2026, 8, 14), party_id=bapari.id, direction=PAYMENT_IN,
        amount=Decimal("400000.00"), method="online", bank_account_id=acct.id,
    ))
    session.add(Payment(   # cheque paid OUT, not yet cleared
        txn_date=date(2026, 8, 16), party_id=bapari.id, direction=PAYMENT_OUT,
        amount=Decimal("122900.00"), method=METHOD_CHEQUE,
        cheque_status=CHEQUE_PENDING, bank_account_id=acct.id,
    ))
    session.flush()

    # While uncleared: excluded from the balance AND the book, so they agree and
    # the cheque row is hidden.
    dashboard = bank_service.all_account_balances(session)[acct.id]
    st = bank_statement(session, acct.id)
    assert st.closing == dashboard == Decimal("407182.00")
    assert len(st.entries) == 1
    assert bank_daily_book(session, acct.id).rows[-1].closing == Decimal("407182.00")

    # Once it clears: it counts in BOTH, still in agreement, and now shows.
    session.query(Payment).filter_by(
        cheque_status=CHEQUE_PENDING).one().cheque_status = CHEQUE_CLEARED
    session.flush()
    dashboard2 = bank_service.all_account_balances(session)[acct.id]
    st2 = bank_statement(session, acct.id)
    assert st2.closing == dashboard2 == Decimal("284282.00")
    assert len(st2.entries) == 2
    assert bank_daily_book(session, acct.id).rows[-1].closing == Decimal("284282.00")
