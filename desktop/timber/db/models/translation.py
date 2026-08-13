"""Cache of machine-translated strings.

Free-text business data (names, notes) is typed in English but shown in
Urdu for Urdu users. Each unique source string is translated once via the
online service and cached here, so all machines sharing the database
reuse it instantly afterwards.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class Translation(Base):
    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint("source_text", "target_lang", name="uq_translation_src_lang"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_text: Mapped[str] = mapped_column(Text)
    target_lang: Mapped[str] = mapped_column(default="ur")
    translated_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Translation {self.source_text!r}->{self.translated_text!r}>"
