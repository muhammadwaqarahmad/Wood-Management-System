"""Per-wood-type split rates for a factory's sub-ledger.

A split factory divides each load's rate into two sides. Instead of one
flat rate for the whole factory, the split amount is set **per wood type**:
e.g. for one factory Kikar splits 100/maund while Sheesham splits 150.

Each row is one (factory, wood type) pair. A wood type with **no row**
gets NO split for that factory — the whole rate stays on the weekly
(left) side. ``Party.split_rate`` remains only the enrolment flag (NULL =
this factory is not in the split ledger).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base


class FactorySplitRate(Base):
    __tablename__ = "factory_split_rates"
    __table_args__ = (
        UniqueConstraint(
            "factory_id", "wood_type_id", name="uq_factory_split_wood"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    factory_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    wood_type_id: Mapped[int] = mapped_column(ForeignKey("wood_types.id"))
    # Per-maund amount posted to the RIGHT (irregular) side for this wood;
    # the remaining rate stays on the LEFT (weekly) side.
    split_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    wood_type: Mapped["WoodType"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<FactorySplitRate factory={self.factory_id} "
            f"wood={self.wood_type_id} rate={self.split_rate}>"
        )
