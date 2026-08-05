"""Bapari transactions (the `bapari_txns` table) — wood you BOUGHT.

Formulas (computed in Phase 2 business logic and stored here):
    bill       = weight * rate
    net_amount = bill + freight + loading
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base


class BapariTxn(Base):
    __tablename__ = "bapari_txns"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)

    # Which bapari, what wood, which location.
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    wood_type_id: Mapped[int | None] = mapped_column(ForeignKey("wood_types.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))

    vehicle_no: Mapped[str | None]

    # Weight is recorded as maunds (mud) + kg. On a purchase only the
    # maunds are billed; ``weight`` holds the billable weight used.
    muds: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    kg: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))

    # Core numbers.
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 3))  # billable weight
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # bapari rate
    # ``freight`` holds the per-load charges attributed to this party
    # (loading/freight/unloading paid by the bapari). loading kept for
    # backward-compat (unused by the trade flow).
    freight: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    loading: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Derived totals (kept for fast reporting).
    bill: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    notes: Mapped[str | None]

    # Soft delete — we void instead of deleting (audit-friendly).
    is_void: Mapped[bool] = mapped_column(default=False)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Navigation.
    party: Mapped["Party"] = relationship()
    wood_type: Mapped["WoodType | None"] = relationship()
    location: Mapped["Location | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<BapariTxn id={self.id} date={self.txn_date} "
            f"weight={self.weight} rate={self.rate}>"
        )
