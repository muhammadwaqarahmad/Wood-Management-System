"""Factory transactions (the `factory_txns` table) — wood you SOLD.

Same shape as bapari_txns, but `rate` here is the factory (selling)
rate. The difference between the two rates is your margin.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base


class FactoryTxn(Base):
    __tablename__ = "factory_txns"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)

    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    wood_type_id: Mapped[int | None] = mapped_column(ForeignKey("wood_types.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))

    vehicle_no: Mapped[str | None]

    # Maunds + kg. On a sale the kg also count (weight = muds + kg/40).
    muds: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    kg: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))

    weight: Mapped[Decimal] = mapped_column(Numeric(12, 3))  # billable weight
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # factory rate
    # Charges attributed to the factory (paid-by-factory expenses).
    freight: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    loading: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    bill: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    notes: Mapped[str | None]
    is_void: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    party: Mapped["Party"] = relationship()
    wood_type: Mapped["WoodType | None"] = relationship()
    location: Mapped["Location | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FactoryTxn id={self.id} date={self.txn_date} "
            f"weight={self.weight} rate={self.rate}>"
        )
