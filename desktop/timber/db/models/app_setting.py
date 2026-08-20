"""Key-value application settings (the `app_settings` table).

A small store for admin-editable, DB-backed config that must be shared across
every client PC + the API/website — e.g. the business name. The env vars
(TIMBER_BUSINESS_NAME[_UR]) remain the default/fallback when a key is unset.
"""
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]

    def __repr__(self) -> str:
        return f"<AppSetting {self.key!r}={self.value!r}>"
