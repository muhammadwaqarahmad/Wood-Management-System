"""Additional phone numbers for a party (the `party_phones` table)."""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class PartyPhone(Base):
    __tablename__ = "party_phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    phone: Mapped[str]

    def __repr__(self) -> str:
        return f"<PartyPhone party={self.party_id} {self.phone!r}>"
