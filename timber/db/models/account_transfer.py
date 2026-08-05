"""Money moved between two business accounts (the `account_transfers`
table), e.g. cash deposited into a bank, or bank-to-bank.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base


class AccountTransfer(Base):
    __tablename__ = "account_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    to_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    note: Mapped[str | None]

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    from_account: Mapped["BankAccount"] = relationship(foreign_keys=[from_account_id])
    to_account: Mapped["BankAccount"] = relationship(foreign_keys=[to_account_id])

    def __repr__(self) -> str:
        return f"<AccountTransfer {self.from_account_id}->{self.to_account_id} {self.amount}>"
