"""User accounts and roles (the `users` table).

Roles drive the permission matrix in Phase 2:
Admin, Manager, Data Entry, Accountant, Viewer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from timber.db.engine import Base


class User(Base):
    __tablename__ = "users"

    # Primary key — auto-incrementing integer.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Login name — must be unique, cannot be empty (no `| None`).
    username: Mapped[str] = mapped_column(unique=True)

    # bcrypt hash of the password (never store the plain password).
    password_hash: Mapped[str]

    # Display name — optional, so it's nullable (`str | None`).
    full_name: Mapped[str | None]

    # Role string. We'll tighten this to an Enum later if we want.
    role: Mapped[str] = mapped_column(default="Viewer")

    # Soft on/off switch for an account instead of deleting it.
    is_active: Mapped[bool] = mapped_column(default=True)

    # Set by the database server when the row is inserted.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
