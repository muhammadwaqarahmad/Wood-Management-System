"""Wood types (the `wood_types` table), e.g. Kikar, Sheesham, Poplar."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class WoodType(Base):
    __tablename__ = "wood_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None]
    #: Default per-maund rates for this wood, one per side of the trade: what
    #: we expect to PAY a supplier and what we expect to CHARGE a factory.
    #: Buy & Sell pre-fills both when a wood type is picked; the operator can
    #: type over either for that load, so these are starting points and never
    #: a fixed price. 0 means "no default" and leaves the field alone.
    default_supplier_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0"
    )
    default_factory_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<WoodType id={self.id} name={self.name!r}>"
