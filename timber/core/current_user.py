"""A lightweight, session-independent snapshot of the logged-in user.

We pass this around the UI instead of the ORM ``User`` so we never hit
DetachedInstanceError after the login session closes. It carries just
what the UI needs: id (for created_by/audit) and role (for permissions).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str
    full_name: str | None = None

    @classmethod
    def from_user(cls, user) -> "CurrentUser":
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            full_name=user.full_name,
        )

    @property
    def display_name(self) -> str:
        return self.full_name or self.username
