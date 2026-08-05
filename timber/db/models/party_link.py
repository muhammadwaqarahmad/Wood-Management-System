"""Many-to-many link between baparis and the factories they serve."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Table

from timber.db.engine import Base

party_links = Table(
    "party_links",
    Base.metadata,
    Column("bapari_id", ForeignKey("parties.id"), primary_key=True),
    Column("factory_id", ForeignKey("parties.id"), primary_key=True),
)
