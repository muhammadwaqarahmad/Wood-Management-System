"""Business bank accounts (the `bank_accounts` table).

Each account has an opening balance; its closing balance is computed
live from the payments and expenses that flow through it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base
from timber.db.models._bilingual import BilingualName


class BankAccount(BilingualName, Base):
    __tablename__ = "bank_accounts"
    # The physical name column (from BilingualName) stays unique.
    __table_args__ = (UniqueConstraint("name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # ``name`` (bilingual) comes from BilingualName.
    bank_name: Mapped[str | None]
    account_number: Mapped[str | None]
    iban: Mapped[str | None]
    branch: Mapped[str | None]  # branch name / location

    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )

    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<BankAccount id={self.id} name={self.name!r}>"
