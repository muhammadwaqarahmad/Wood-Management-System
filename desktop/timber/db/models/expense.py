"""Operational expenses (the `expenses` table): rent, electricity, etc.

Each expense is paid from a bank account and reduces its balance.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base

# High-level buckets: business vs house (personal/household) spending.
KIND_BUSINESS = "business"
KIND_HOUSE = "house"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(default=KIND_BUSINESS, server_default=KIND_BUSINESS)
    category: Mapped[str]  # rent, electricity, salary, fuel, other ...
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id")
    )

    # Set when this expense was auto-created from a trade (freight/loading/
    # unloading paid by us). Lets edit/void of the trade manage it, and lets
    # the dashboard avoid double-counting it against trade profit.
    combined_id: Mapped[int | None] = mapped_column(
        ForeignKey("combined_txns.id")
    )

    note: Mapped[str | None]
    is_void: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    bank_account: Mapped["BankAccount | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Expense id={self.id} {self.category!r} {self.amount}>"
