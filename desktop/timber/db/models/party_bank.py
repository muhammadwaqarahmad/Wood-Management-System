"""Bank accounts belonging to a party (the `party_banks` table).

A bapari or factory can have several bank accounts; each has an
account title, bank name, IBAN, and account number.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class PartyBank(Base):
    __tablename__ = "party_banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    account_title: Mapped[str | None]
    bank_name: Mapped[str | None]
    iban: Mapped[str | None]
    account_number: Mapped[str | None]

    def __repr__(self) -> str:
        return f"<PartyBank party={self.party_id} {self.bank_name!r}>"
