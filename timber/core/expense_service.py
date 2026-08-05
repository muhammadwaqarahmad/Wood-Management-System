"""Operational expenses — rent, electricity, etc., paid from an account.

Every expense belongs to a high-level *kind*: **business** or **house**
(personal/household spending), so the two can be tracked and reported
separately."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from timber.core.audit import log_action
from timber.core.calculations import money
from timber.db.models import BankAccount, Expense
from timber.db.models.expense import KIND_BUSINESS, KIND_HOUSE

# Suggested categories (free text is also allowed).
EXPENSE_CATEGORIES = [
    "rent",
    "electricity",
    "salary",
    "fuel",
    "maintenance",
    "other",
]

EXPENSE_KINDS = [KIND_BUSINESS, KIND_HOUSE]

ZERO = Decimal("0.00")


def _valid_kind(kind: str | None) -> str:
    kind = (kind or KIND_BUSINESS).strip().lower()
    if kind not in EXPENSE_KINDS:
        raise ValueError(f"Unknown expense kind: {kind!r}")
    return kind


def create_expense(
    session: Session,
    *,
    txn_date: date,
    category: str,
    amount: Any,
    kind: str = KIND_BUSINESS,
    bank_account_id: int | None = None,
    note: str | None = None,
    created_by=None,
) -> Expense:
    category = (category or "").strip()
    if not category:
        raise ValueError("Category is required.")
    kind = _valid_kind(kind)
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    if bank_account_id and session.get(BankAccount, bank_account_id) is None:
        raise ValueError("Bank account not found.")
    expense = Expense(
        txn_date=txn_date,
        kind=kind,
        category=category,
        amount=amt,
        bank_account_id=bank_account_id,
        note=(note or None),
        created_by=created_by,
    )
    session.add(expense)
    session.flush()
    log_action(
        session, created_by, "create", "expenses", expense.id,
        f"{kind}/{category} {amt}",
    )
    return expense


def update_expense(
    session: Session,
    expense_id: int,
    *,
    txn_date: date,
    category: str,
    amount: Any,
    kind: str | None = None,
    bank_account_id: int | None = None,
    note: str | None = None,
    created_by=None,
) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise ValueError("Expense not found.")
    category = (category or "").strip()
    if not category:
        raise ValueError("Category is required.")
    amt = money(amount)
    if amt <= 0:
        raise ValueError("Amount must be greater than 0.")
    if bank_account_id and session.get(BankAccount, bank_account_id) is None:
        raise ValueError("Bank account not found.")
    expense.txn_date = txn_date
    if kind is not None:
        expense.kind = _valid_kind(kind)
    expense.category = category
    expense.amount = amt
    expense.bank_account_id = bank_account_id
    expense.note = (note or None)
    session.flush()
    log_action(session, created_by, "update", "expenses", expense_id, f"{category} {amt}")
    return expense


def void_expense(session: Session, expense_id: int, created_by=None) -> None:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise ValueError("Expense not found.")
    expense.is_void = True
    session.flush()
    log_action(session, created_by, "void", "expenses", expense_id)


@dataclass
class ExpenseRow:
    id: int
    txn_date: date
    kind: str
    category: str
    amount: Decimal
    account_name: str
    note: str


def list_expenses(
    session: Session,
    limit: int = 500,
    *,
    kind: str | None = None,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
) -> list[ExpenseRow]:
    """Manual/operating expenses, oldest first, with optional filters:
    ``kind`` (business/house), ``category``, a date range and a free-text
    search over category + note."""
    query = (
        select(Expense)
        .options(joinedload(Expense.bank_account))
        .where(Expense.is_void.is_(False), Expense.combined_id.is_(None))
    )
    if kind:
        query = query.where(Expense.kind == _valid_kind(kind))
    if category:
        query = query.where(Expense.category == category)
    if start is not None:
        query = query.where(Expense.txn_date >= start)
    if end is not None:
        query = query.where(Expense.txn_date <= end)
    rows: list[ExpenseRow] = []
    needle = (search or "").strip().lower()
    for e in session.scalars(query.order_by(Expense.txn_date, Expense.id).limit(limit)):
        if needle and needle not in f"{e.category} {e.note or ''}".lower():
            continue
        rows.append(
            ExpenseRow(
                e.id, e.txn_date, e.kind, e.category, e.amount,
                e.bank_account.name if e.bank_account else "—",
                e.note or "",
            )
        )
    return rows


def total_expenses(
    session: Session,
    operating_only: bool = False,
    *,
    kind: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Decimal:
    """Total non-void expenses. ``operating_only`` excludes expenses that
    were auto-created from trades (used on the Expenses page); the dashboard
    uses the full total (since per-trade profit is now gross). ``kind`` and
    the date range narrow the total."""
    query = select(Expense).where(Expense.is_void.is_(False))
    if operating_only:
        query = query.where(Expense.combined_id.is_(None))
    if kind:
        query = query.where(Expense.kind == _valid_kind(kind))
    if start is not None:
        query = query.where(Expense.txn_date >= start)
    if end is not None:
        query = query.where(Expense.txn_date <= end)
    return money(sum((e.amount for e in session.scalars(query)), ZERO))


@dataclass
class ExpenseStats:
    total: Decimal
    business: Decimal
    house: Decimal
    count: int
    by_category: list[tuple[str, Decimal]]  # sorted, biggest first


def expense_stats(
    session: Session,
    *,
    kind: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> ExpenseStats:
    """Aggregate statistics for the Expenses page (manual expenses only)."""
    query = select(Expense).where(
        Expense.is_void.is_(False), Expense.combined_id.is_(None)
    )
    if kind:
        query = query.where(Expense.kind == _valid_kind(kind))
    if start is not None:
        query = query.where(Expense.txn_date >= start)
    if end is not None:
        query = query.where(Expense.txn_date <= end)
    total = business = house = ZERO
    count = 0
    by_cat: dict[str, Decimal] = {}
    for e in session.scalars(query):
        amt = money(e.amount)
        total += amt
        count += 1
        if e.kind == KIND_HOUSE:
            house += amt
        else:
            business += amt
        by_cat[e.category] = by_cat.get(e.category, ZERO) + amt
    cats = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)
    return ExpenseStats(money(total), money(business), money(house), count, cats)
