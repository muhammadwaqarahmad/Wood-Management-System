"""Combined transactions (the `combined_txns` table).

Links one purchase (bapari_txn) to its matching sale (factory_txn) for
the same truck, so the margin is tracked in one place:

    profit = (factory_rate - bapari_rate) * weight
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base

# Who paid a per-load expense.
PAYER_US = "us"
PAYER_BAPARI = "bapari"
PAYER_FACTORY = "factory"


class CombinedTxn(Base):
    __tablename__ = "combined_txns"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)

    bapari_txn_id: Mapped[int] = mapped_column(ForeignKey("bapari_txns.id"))
    factory_txn_id: Mapped[int] = mapped_column(ForeignKey("factory_txns.id"))

    # Groups the wood lines of one mixed-load truck into a single trade.
    # NULL or == own id means a standalone (single-wood) trade.
    group_id: Mapped[int | None] = mapped_column(default=None)

    # Per-load expenses with who paid each (us / bapari / factory). An
    # expense can be split between two payers: ``*_payer`` pays the rupee
    # amount ``*_split`` and the rest goes to ``*_payer2`` (NULL = single
    # payer, who pays the whole amount).
    loading_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    loading_payer: Mapped[str] = mapped_column(default=PAYER_US)
    loading_payer2: Mapped[str | None] = mapped_column(default=None)
    loading_split: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    freight_payer: Mapped[str] = mapped_column(default=PAYER_US)
    freight_payer2: Mapped[str | None] = mapped_column(default=None)
    freight_split: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    unloading_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    unloading_payer: Mapped[str] = mapped_column(default=PAYER_US)
    unloading_payer2: Mapped[str | None] = mapped_column(default=None)
    unloading_split: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Total expenses we (the business) bore on this load.
    own_expense: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Derived margin for this load (stored for reporting).
    profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    notes: Mapped[str | None]

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    bapari_txn: Mapped["BapariTxn"] = relationship()
    factory_txn: Mapped["FactoryTxn"] = relationship()

    def __repr__(self) -> str:
        return f"<CombinedTxn id={self.id} profit={self.profit}>"
