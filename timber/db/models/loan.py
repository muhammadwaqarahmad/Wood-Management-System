"""Loans the business takes from family/friends to keep cash flowing,
and the repayments made later.

    loan outstanding = principal - sum(repayments)

Borrowing puts cash INTO a bank account; repaying takes it OUT. Both move
the account's running balance.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base

# Loan direction: money we borrowed (we owe it back) vs money we lent
# out to someone (they owe it back to us).
LOAN_TAKEN = "taken"
LOAN_GIVEN = "given"


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(default=LOAN_TAKEN, server_default=LOAN_TAKEN)
    lender_name: Mapped[str]  # the other person (lender OR borrower)
    principal: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Account the borrowed money was received into.
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    expected_return_date: Mapped[date | None] = mapped_column(Date, default=None)

    notes: Mapped[str | None]
    is_void: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    bank_account: Mapped["BankAccount | None"] = relationship()
    repayments: Mapped[list["LoanRepayment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Loan id={self.id} {self.lender_name!r} {self.principal}>"


class LoanRepayment(Base):
    __tablename__ = "loan_repayments"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    txn_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Account the repayment was paid from.
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    notes: Mapped[str | None]

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    loan: Mapped["Loan"] = relationship(back_populates="repayments")
    bank_account: Mapped["BankAccount | None"] = relationship()

    def __repr__(self) -> str:
        return f"<LoanRepayment loan={self.loan_id} {self.amount}>"
