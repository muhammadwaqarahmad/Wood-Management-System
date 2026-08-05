"""Unknown (unattributed) receipts — money that landed in one of our bank
accounts before we know who sent it.

It counts as cash in that account straight away, but belongs to no party's
ledger. When someone claims it (and we verify), it is CLAIMED: a normal
factory/supplier payment is created and this record is removed. Unclaimed
receipts simply wait.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base
from timber.db.models.payment import METHOD_ONLINE, PAYMENT_IN


class UnknownPayment(Base):
    __tablename__ = "unknown_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # The account the money moved through (drives that account's balance).
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))

    # Almost always "in" — money that arrived from someone we cannot yet
    # identify. "out" covers the mirror case: an unexplained debit that left an
    # account before we know who it went to.
    direction: Mapped[str] = mapped_column(default=PAYMENT_IN,
                                           server_default=PAYMENT_IN)
    method: Mapped[str] = mapped_column(default=METHOD_ONLINE)  # how it arrived
    reference_no: Mapped[str | None]
    notes: Mapped[str | None]

    is_void: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    bank_account: Mapped["BankAccount"] = relationship()

    def __repr__(self) -> str:
        return f"<UnknownPayment id={self.id} {self.amount} acct={self.bank_account_id}>"
