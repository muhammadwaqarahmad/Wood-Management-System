"""How much of a payment was applied to a specific load (FIFO matching).

Each row ties part of a payment to one bapari/factory transaction, so
we can see how much of each load is paid vs outstanding. Anything not
allocated is an advance.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    kind: Mapped[str]          # "bapari" | "factory"
    txn_id: Mapped[int]        # bapari_txns.id or factory_txns.id
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    def __repr__(self) -> str:
        return f"<PaymentAllocation pay={self.payment_id} {self.kind}#{self.txn_id} {self.amount}>"
