"""Parties — baparis (suppliers) and factories (buyers) in one table.

The `party_type` column tells them apart. A bapari is someone you BUY
wood from (a payable); a factory is someone you SELL to (a receivable).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base
from timber.db.models._bilingual import BilingualName
from timber.db.models.party_link import party_links

# Allowed values for Party.party_type.
PARTY_BAPARI = "bapari"
PARTY_FACTORY = "factory"


class Party(BilingualName, Base):
    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    # ``name`` (bilingual) comes from BilingualName.
    party_type: Mapped[str]  # "bapari" | "factory"

    email: Mapped[str | None]
    address: Mapped[str | None]

    # Credit period in days (factories): receivables older than this are
    # flagged overdue. None = no deadline.
    credit_days: Mapped[int | None]

    # Factories only: the part of the factory rate posted to the sub-ledger's
    # RIGHT side (cleared irregularly, 30-60 days). The LEFT side gets the
    # remaining rate minus the factory-paid freight and is cleared weekly.
    # None/0 = this factory has no split sub-ledger.
    split_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), default=None
    )

    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))

    # Balance carried over before the app started tracking. Positive =
    # we owe them (bapari) / they owe us (factory), per business rules.
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Convenience navigation.
    location: Mapped["Location | None"] = relationship()
    phones: Mapped[list["PartyPhone"]] = relationship(
        cascade="all, delete-orphan"
    )
    banks: Mapped[list["PartyBank"]] = relationship(
        cascade="all, delete-orphan"
    )

    # Bapari -> the factories it serves (writable from the bapari side).
    linked_factories: Mapped[list["Party"]] = relationship(
        "Party",
        secondary=party_links,
        primaryjoin=id == party_links.c.bapari_id,
        secondaryjoin=id == party_links.c.factory_id,
        overlaps="linked_baparis",
    )
    # Factory -> the baparis linked to it (read-only view).
    linked_baparis: Mapped[list["Party"]] = relationship(
        "Party",
        secondary=party_links,
        primaryjoin=id == party_links.c.factory_id,
        secondaryjoin=id == party_links.c.bapari_id,
        viewonly=True,
        overlaps="linked_factories",
    )

    def __repr__(self) -> str:
        return f"<Party id={self.id} name={self.name!r} type={self.party_type!r}>"
