"""Business bank accounts — CRUD and live balance.

Closing balance = opening + payments IN − payments OUT − expenses,
counting only non-void rows tied to that account.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from timber.core.audit import log_action
from timber.core.calculations import money
from timber.db.models import AccountTransfer, BankAccount, Expense, Payment
from timber.db.models.payment import PAYMENT_IN

ZERO = Decimal("0.00")


def _unknown_signed_amount():
    """SQL: an unknown receipt adds to its account, an unknown debit subtracts."""
    from timber.db.models import UnknownPayment

    return case(
        (UnknownPayment.direction == PAYMENT_IN, UnknownPayment.amount),
        else_=-UnknownPayment.amount,
    )
CASH_ACCOUNT_NAME = "Cash"        # stable key — matched on the physical column
CASH_ACCOUNT_NAME_UR = "نقد"


def cash_account(session: Session) -> BankAccount:
    """Get (or create) the special 'Cash' account for cash-in-hand."""
    # Look up by the physical name column (language-independent) so we never
    # create a duplicate Cash account when the app is in Urdu.
    acct = session.scalar(
        select(BankAccount).where(BankAccount._name == CASH_ACCOUNT_NAME)
    )
    if acct is None:
        acct = BankAccount()
        acct.set_names(en=CASH_ACCOUNT_NAME, ur=CASH_ACCOUNT_NAME_UR)
        acct._name = CASH_ACCOUNT_NAME  # keep the stable key regardless of UI lang
        session.add(acct)
        session.flush()
    return acct


def _account_name_taken(session: Session, *names: str) -> bool:
    wanted = {n for n in names if n}
    for existing in session.scalars(select(BankAccount)):
        if wanted & {existing._name, existing.name_en, existing.name_ur}:
            return True
    return False


def create_account(
    session: Session,
    *,
    name: str | None = None,
    name_en: str | None = None,
    name_ur: str | None = None,
    bank_name: str | None = None,
    account_number: str | None = None,
    iban: str | None = None,
    branch: str | None = None,
    opening_balance: Any = 0,
    created_by=None,
) -> BankAccount:
    from timber.core.admin_service import resolve_names

    en, ur = resolve_names(name, name_en, name_ur)
    if _account_name_taken(session, en, ur):
        raise ValueError("That account name already exists.")
    if Decimal(str(opening_balance or 0)) < 0:
        raise ValueError("Opening balance cannot be negative.")
    acct = BankAccount(
        bank_name=(bank_name or None),
        account_number=(account_number or None),
        iban=(iban or None),
        branch=(branch or None),
        opening_balance=Decimal(str(opening_balance or 0)),
    )
    acct.set_names(en=en, ur=ur)
    session.add(acct)
    session.flush()
    log_action(session, created_by, "create", "bank_accounts", acct.id, acct.name)
    return acct


def update_account(
    session: Session,
    account_id: int,
    *,
    name: str | None = None,
    name_en: str | None = None,
    name_ur: str | None = None,
    bank_name: str | None = None,
    account_number: str | None = None,
    iban: str | None = None,
    branch: str | None = None,
    opening_balance: Any = None,
    created_by=None,
) -> BankAccount:
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise ValueError("Account not found.")
    if name_en is not None or name_ur is not None:
        en = name_en.strip() if name_en is not None else (acct.name_en or "")
        ur = name_ur.strip() if name_ur is not None else (acct.name_ur or "")
        if not (en or ur):
            raise ValueError("Name is required.")
        acct.set_names(en=(en or ur), ur=(ur or en))
    elif name is not None:
        if not name.strip():
            raise ValueError("Name is required.")
        acct.name = name.strip()
    if bank_name is not None:
        acct.bank_name = bank_name or None
    if account_number is not None:
        acct.account_number = account_number or None
    if iban is not None:
        acct.iban = iban or None
    if branch is not None:
        acct.branch = branch or None
    if opening_balance is not None:
        if Decimal(str(opening_balance)) < 0:
            raise ValueError("Opening balance cannot be negative.")
        acct.opening_balance = Decimal(str(opening_balance))
    session.flush()
    log_action(session, created_by, "update", "bank_accounts", account_id, acct.name)
    return acct


def set_account_active(session: Session, account_id: int, active: bool, created_by=None):
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise ValueError("Account not found.")
    acct.is_active = active
    session.flush()
    log_action(
        session, created_by, "activate" if active else "deactivate",
        "bank_accounts", account_id,
    )
    return acct


def ensure_not_overdrawn(session: Session, account_id: int | None) -> None:
    """Strict rule: a bank account can never go below zero. Call this AFTER
    flushing a money-OUT (payment out / expense / transfer-from) so the new
    row is counted; raises ValueError if the account would be overdrawn."""
    if account_id is None:
        return
    bal = account_balance(session, account_id)
    if bal < 0:
        acct = session.get(BankAccount, account_id)
        name = acct.name if acct else "account"
        raise ValueError(
            f"{name} does not have enough balance for this — it would go "
            f"negative ({bal:,.2f}). Add an opening balance or money in first."
        )


def account_balance(
    session: Session, account_id: int, before: "date | None" = None
) -> Decimal:
    """The account's balance. With ``before``, only entries dated BEFORE
    that day count — i.e. the account's OPENING for that day (yesterday's
    closing), which rolls forward with every payment/expense/transfer.

    Uses SUM aggregates (not row hydration) so a busy account — Cash, the main
    bank — stays fast even after years of entries and on a networked DB."""
    acct = session.get(BankAccount, account_id)
    if acct is None:
        raise ValueError("Account not found.")
    from timber.db.models import Loan, LoanRepayment, UnknownPayment
    from timber.db.models.loan import LOAN_GIVEN
    from timber.db.models.payment import CHEQUE_CLEARED, METHOD_CHEQUE

    def _before(query, col):
        return query.where(col < before) if before is not None else query

    def _sum(query) -> Decimal:
        return session.scalar(query) or Decimal("0")

    balance = acct.opening_balance

    # Payments: +IN / −OUT, but a cheque only counts once CLEARED.
    cheque_ok = or_(
        Payment.method != METHOD_CHEQUE, Payment.cheque_status == CHEQUE_CLEARED
    )
    signed_pay = case(
        (Payment.direction == PAYMENT_IN, Payment.amount), else_=-Payment.amount
    )
    balance += _sum(_before(
        select(func.sum(signed_pay)).where(
            Payment.bank_account_id == account_id,
            Payment.is_void.is_(False), cheque_ok,
        ),
        Payment.txn_date,
    ))
    balance -= _sum(_before(
        select(func.sum(Expense.amount)).where(
            Expense.bank_account_id == account_id, Expense.is_void.is_(False)
        ),
        Expense.txn_date,
    ))
    balance += _sum(_before(
        select(func.sum(AccountTransfer.amount)).where(
            AccountTransfer.to_account_id == account_id
        ),
        AccountTransfer.txn_date,
    ))
    balance -= _sum(_before(
        select(func.sum(AccountTransfer.amount)).where(
            AccountTransfer.from_account_id == account_id
        ),
        AccountTransfer.txn_date,
    ))
    # Loans. TAKEN: borrowing puts money IN (+principal), GIVEN: lending takes
    # it OUT (−principal).
    signed_loan = case(
        (Loan.direction == LOAN_GIVEN, -Loan.principal), else_=Loan.principal
    )
    balance += _sum(_before(
        select(func.sum(signed_loan)).where(
            Loan.bank_account_id == account_id, Loan.is_void.is_(False)
        ),
        Loan.txn_date,
    ))
    # Repayments: on a GIVEN loan money comes back IN (+); otherwise OUT (−).
    signed_rep = case(
        (Loan.direction == LOAN_GIVEN, LoanRepayment.amount),
        else_=-LoanRepayment.amount,
    )
    balance += _sum(_before(
        select(func.sum(signed_rep))
        .select_from(LoanRepayment)
        .join(Loan, LoanRepayment.loan_id == Loan.id)
        .where(LoanRepayment.bank_account_id == account_id),
        LoanRepayment.txn_date,
    ))
    # Unknown receipts: real cash in the account until attributed. An unknown
    # DEBIT is the mirror case — money already gone, so it subtracts.
    balance += _sum(_before(
        select(func.sum(_unknown_signed_amount())).where(
            UnknownPayment.bank_account_id == account_id,
            UnknownPayment.is_void.is_(False),
        ),
        UnknownPayment.txn_date,
    ))
    return money(balance)


@dataclass
class TransferRow:
    id: int
    txn_date: "date"
    from_name: str
    to_name: str
    amount: Decimal
    note: str


def create_transfer(
    session: Session,
    *,
    txn_date,
    from_account_id: int,
    to_account_id: int,
    amount: Any,
    note: str | None = None,
    created_by=None,
) -> AccountTransfer:
    if not from_account_id or not to_account_id:
        raise ValueError("Choose both accounts.")
    if from_account_id == to_account_id:
        raise ValueError("Source and destination must be different.")
    if session.get(BankAccount, from_account_id) is None or session.get(BankAccount, to_account_id) is None:
        raise ValueError("Account not found.")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    transfer = AccountTransfer(
        txn_date=txn_date,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amt,
        note=(note or None),
        created_by=created_by,
    )
    session.add(transfer)
    session.flush()
    log_action(session, created_by, "create", "account_transfers", transfer.id, str(amt))
    return transfer


def update_transfer(
    session: Session,
    transfer_id: int,
    *,
    txn_date,
    from_account_id: int,
    to_account_id: int,
    amount: Any,
    note: str | None = None,
    created_by=None,
) -> AccountTransfer:
    transfer = session.get(AccountTransfer, transfer_id)
    if transfer is None:
        raise ValueError("Transfer not found.")
    if not from_account_id or not to_account_id:
        raise ValueError("Choose both accounts.")
    if from_account_id == to_account_id:
        raise ValueError("Source and destination must be different.")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    transfer.txn_date = txn_date
    transfer.from_account_id = from_account_id
    transfer.to_account_id = to_account_id
    transfer.amount = amt
    transfer.note = (note or None)
    session.flush()
    log_action(session, created_by, "update", "account_transfers", transfer_id, str(amt))
    return transfer


def delete_transfer(session: Session, transfer_id: int, created_by=None) -> None:
    transfer = session.get(AccountTransfer, transfer_id)
    if transfer is None:
        raise ValueError("Transfer not found.")
    session.delete(transfer)
    session.flush()
    log_action(session, created_by, "delete", "account_transfers", transfer_id)


def list_transfers(
    session: Session, limit: int = 500,
    start: "date | None" = None, end: "date | None" = None,
) -> list[TransferRow]:
    """Transfers, optionally limited to a date range."""
    rows: list[TransferRow] = []
    q = (
        select(AccountTransfer)
        # Both account names are read for every row; without these they were
        # lazy-loaded one query at a time.
        .options(
            joinedload(AccountTransfer.from_account),
            joinedload(AccountTransfer.to_account),
        )
        .order_by(AccountTransfer.txn_date, AccountTransfer.id)
    )
    if start is not None:
        q = q.where(AccountTransfer.txn_date >= start)
    if end is not None:
        q = q.where(AccountTransfer.txn_date <= end)
    for t in session.scalars(q.limit(limit)):
        rows.append(
            TransferRow(
                t.id, t.txn_date, t.from_account.name, t.to_account.name,
                t.amount, t.note or "",
            )
        )
    return rows


@dataclass
class AccountBalance:
    id: int
    name: str
    bank_name: str | None
    account_number: str | None
    iban: str | None
    branch: str | None
    opening: Decimal
    closing: Decimal
    # Language-independent flag: ``name`` is localized, so never compare it to
    # "Cash" — check this instead.
    is_cash: bool = False
    is_active: bool = True


def all_account_balances(
    session: Session, before: "date | None" = None
) -> dict[int, Decimal]:
    """Closing balance of EVERY account in a handful of aggregate queries
    (not one-per-account). Same math as :func:`account_balance`, but grouped
    server-side — so opening a balances page is ~7 round-trips instead of a
    few hundred (which is what made it crawl on a networked PostgreSQL)."""
    from timber.db.models import Loan, LoanRepayment, UnknownPayment
    from timber.db.models.loan import LOAN_GIVEN
    from timber.db.models.payment import CHEQUE_CLEARED, METHOD_CHEQUE

    ZERO = Decimal("0.00")
    bal: dict[int, Decimal] = {}

    def _add(rows) -> None:
        for acc_id, total in rows:
            if acc_id is None or total is None:
                continue
            bal[acc_id] = bal.get(acc_id, ZERO) + total

    # Opening balances seed every account.
    for aid, opening in session.execute(
        select(BankAccount.id, BankAccount.opening_balance)
    ):
        bal[aid] = opening or ZERO

    def _before(query, col):
        return query.where(col < before) if before is not None else query

    # Payments: +IN / −OUT, but a cheque only counts once CLEARED.
    cheque_ok = or_(
        Payment.method != METHOD_CHEQUE, Payment.cheque_status == CHEQUE_CLEARED
    )
    signed_pay = case(
        (Payment.direction == PAYMENT_IN, Payment.amount), else_=-Payment.amount
    )
    _add(session.execute(
        _before(
            select(Payment.bank_account_id, func.sum(signed_pay))
            .where(Payment.is_void.is_(False), cheque_ok),
            Payment.txn_date,
        ).group_by(Payment.bank_account_id)
    ))

    # Expenses: −amount.
    _add((aid, -total) for aid, total in session.execute(
        _before(
            select(Expense.bank_account_id, func.sum(Expense.amount))
            .where(Expense.is_void.is_(False)),
            Expense.txn_date,
        ).group_by(Expense.bank_account_id)
    ))

    # Transfers: +into / −out of.
    _add(session.execute(
        _before(
            select(AccountTransfer.to_account_id, func.sum(AccountTransfer.amount)),
            AccountTransfer.txn_date,
        ).group_by(AccountTransfer.to_account_id)
    ))
    _add((aid, -total) for aid, total in session.execute(
        _before(
            select(AccountTransfer.from_account_id, func.sum(AccountTransfer.amount)),
            AccountTransfer.txn_date,
        ).group_by(AccountTransfer.from_account_id)
    ))

    # Loans: TAKEN puts money in (+principal); GIVEN takes it out (−principal).
    signed_loan = case(
        (Loan.direction == LOAN_GIVEN, -Loan.principal), else_=Loan.principal
    )
    _add(session.execute(
        _before(
            select(Loan.bank_account_id, func.sum(signed_loan))
            .where(Loan.is_void.is_(False)),
            Loan.txn_date,
        ).group_by(Loan.bank_account_id)
    ))
    # Repayments: on a GIVEN loan they come back IN (+); otherwise OUT (−).
    signed_rep = case(
        (Loan.direction == LOAN_GIVEN, LoanRepayment.amount),
        else_=-LoanRepayment.amount,
    )
    _add(session.execute(
        _before(
            select(LoanRepayment.bank_account_id, func.sum(signed_rep))
            .join(Loan, LoanRepayment.loan_id == Loan.id),
            LoanRepayment.txn_date,
        ).group_by(LoanRepayment.bank_account_id)
    ))

    # Unknown receipts: real cash in the account until attributed. An unknown
    # DEBIT is the mirror case — money already gone, so it subtracts.
    _add(session.execute(
        _before(
            select(UnknownPayment.bank_account_id,
                   func.sum(_unknown_signed_amount()))
            .where(UnknownPayment.is_void.is_(False)),
            UnknownPayment.txn_date,
        ).group_by(UnknownPayment.bank_account_id)
    ))

    return {aid: money(v) for aid, v in bal.items()}


def all_balances(session: Session, active_only: bool = True) -> list[AccountBalance]:
    balmap = all_account_balances(session)
    query = select(BankAccount).order_by(BankAccount.name)
    if active_only:
        query = query.where(BankAccount.is_active.is_(True))
    return [
        AccountBalance(
            a.id, a.name, a.bank_name, a.account_number, a.iban, a.branch,
            money(a.opening_balance), balmap.get(a.id, money(a.opening_balance)),
            is_cash=(a._name == CASH_ACCOUNT_NAME),
            is_active=bool(a.is_active),
        )
        for a in session.scalars(query)
    ]


def total_cash_position(
    session: Session, balances: "list[AccountBalance] | None" = None
) -> Decimal:
    """Total closing balance across ACTIVE accounts.

    Pass ``balances`` (e.g. an ``all_balances(active_only=False)`` result the
    caller already has) to reuse it — recomputing meant running the whole
    balance aggregate set a second time on every Bank Accounts refresh.
    Inactive accounts are excluded either way.
    """
    rows = balances if balances is not None else all_balances(session)
    return money(sum((b.closing for b in rows if b.is_active), ZERO))
