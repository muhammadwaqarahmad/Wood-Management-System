"""Audit log (the `audit_log` table) — an immutable trail of who did
what and when (create / update / void / login), for accountability.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    action: Mapped[str]            # "create" | "update" | "void" | "login" ...
    entity: Mapped[str]            # table name affected, e.g. "bapari_txns"
    entity_id: Mapped[int | None]  # id of the affected row
    details: Mapped[str | None]    # free-text / JSON describing the change

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"entity={self.entity!r} entity_id={self.entity_id}>"
        )
