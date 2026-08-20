"""API: money write endpoints — expenses, transfers, loans, cheques.

Route-function level (in-memory ``session`` fixture + a CurrentUser), reusing the
desktop services. Overdraw guards mirror the desktop.
"""
from __future__ import annotations

from datetime import date

from timber.core import bank_service
from timber.core.current_user import CurrentUser
from timber.db.models import Party
from timber.db.models.party import PARTY_FACTORY
from timber.api.routers import money as M

ADMIN = CurrentUser(id=1, username="admin", role="Admin")


def _accounts(session):
    a1 = bank_service.create_account(
        session, name_en="Cash", name_ur="", opening_balance=100000,
        created_by=ADMIN.id)
    a2 = bank_service.create_account(
        session, name_en="Bank", name_ur="", opening_balance=0,
        created_by=ADMIN.id)
    session.commit()
    return a1.id, a2.id


def test_expense_create_and_void(session):
    a1, _ = _accounts(session)
    r = M.create_expense_ep(
        M.ExpenseIn(txn_date=date.today(), category="Fuel", amount=500,
                    bank_account_id=a1),
        session=session, user=ADMIN)
    assert r["id"] > 0
    assert M.void_expense_ep(r["id"], session=session, user=ADMIN)["ok"] is True


def test_transfer_create_and_delete(session):
    a1, a2 = _accounts(session)
    r = M.create_transfer_ep(
        M.TransferIn(txn_date=date.today(), from_account_id=a1,
                     to_account_id=a2, amount=1000),
        session=session, user=ADMIN)
    assert r["id"] > 0
    assert M.delete_transfer_ep(r["id"], session=session, user=ADMIN)["ok"] is True


def test_loan_create_and_repay(session):
    a1, _ = _accounts(session)
    r = M.create_loan_ep(
        M.LoanIn(txn_date=date.today(), lender_name="Uncle", amount=5000,
                 direction="taken", bank_account_id=a1),
        session=session, user=ADMIN)
    assert r["id"] > 0
    ok = M.repay_loan_ep(
        r["id"],
        M.RepayIn(txn_date=date.today(), amount=2000, bank_account_id=a1),
        session=session, user=ADMIN)
    assert ok["ok"] is True


def test_cheque_clear(session):
    from timber.core.payment_service import create_payment
    from timber.db.models.payment import METHOD_CHEQUE

    a1, _ = _accounts(session)
    fac = Party(name="Fac", party_type=PARTY_FACTORY, is_active=True)
    session.add(fac)
    session.commit()
    pay = create_payment(
        session, txn_date=date.today(), party_id=fac.id, amount=3000,
        method=METHOD_CHEQUE, bank_account_id=a1, created_by=ADMIN.id)
    session.commit()
    assert M.clear_cheque_ep(pay.id, session=session, user=ADMIN)["ok"] is True
