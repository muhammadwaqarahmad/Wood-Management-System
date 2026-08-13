"""Trade dedup fingerprint — a database-level guard against double entry.

One row per trade (truck), keyed on (date, normalized vehicle, total
weight). The UNIQUE constraint makes it *impossible* for two data-entry
staff to save the same slip at the same instant: the second INSERT is
rejected by the database atomically, even in the millisecond race the
application-level check can't cover.

The row is tied to the trade's ``group_id`` and is removed when the trade
is voided/edited, so a corrected re-entry is always allowed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class TradeKey(Base):
    __tablename__ = "trade_keys"
    __table_args__ = (
        UniqueConstraint(
            "txn_date", "vehicle_key", "total_weight", name="uq_trade_keys_dedup"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("combined_txns.id"))
    txn_date: Mapped[date] = mapped_column(Date)
    vehicle_key: Mapped[str]  # normalized: lower(trim(vehicle_no))
    total_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    def __repr__(self) -> str:
        return (
            f"<TradeKey group={self.group_id} {self.txn_date} "
            f"{self.vehicle_key!r} {self.total_weight}>"
        )
