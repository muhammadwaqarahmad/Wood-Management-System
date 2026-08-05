"""Authentication: create users and verify logins."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.core.permissions import Role
from timber.core.security import hash_password, verify_password
from timber.db.models import User


def create_user(
    session: Session,
    username: str,
    password: str,
    role: Role | str = Role.VIEWER,
    full_name: str | None = None,
) -> User:
    """Create and persist a new user with a hashed password.

    Caller is responsible for committing the session.
    """
    role_value = role.value if isinstance(role, Role) else Role(role).value
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role_value,
        full_name=full_name,
    )
    session.add(user)
    session.flush()  # assigns user.id without committing
    return user


# A real bcrypt hash, verified against when the username does not exist so a
# missing user costs the same time as a wrong password (see authenticate).
_DUMMY_HASH = hash_password("not-a-real-password-constant-time-padding")

# Brute-force throttle. In-memory is enough here: the app is one desktop
# process per PC, so there is no other way in to spread attempts across.
_MAX_FAILURES = 5          # free attempts before any waiting starts
_BASE_DELAY = 2.0          # seconds, doubles per further failure
_MAX_DELAY = 60.0
_failures: dict[str, tuple[int, float]] = {}


def _key(username: str) -> str:
    return (username or "").strip().lower()


def seconds_until_retry(username: str) -> float:
    """Seconds this username must wait before another attempt is accepted."""
    entry = _failures.get(_key(username))
    if not entry:
        return 0.0
    count, last = entry
    if count < _MAX_FAILURES:
        return 0.0
    delay = min(_BASE_DELAY * (2 ** (count - _MAX_FAILURES)), _MAX_DELAY)
    return max(0.0, delay - (time.monotonic() - last))


def reset_throttle(username: str | None = None) -> None:
    """Clear the failure record — for one username, or all of them."""
    if username is None:
        _failures.clear()
    else:
        _failures.pop(_key(username), None)


#: The credential ``ensure_admin`` seeds on a brand-new database. It is in the
#: source, so an install still using it is effectively unprotected.
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def is_default_admin_password(user: User, password: str) -> bool:
    """True if this login used the out-of-the-box admin credential."""
    return (
        user is not None
        and user.username == DEFAULT_ADMIN_USERNAME
        and password == DEFAULT_ADMIN_PASSWORD
    )


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Return the matching active user, or None if login fails.

    Two deliberate properties:

    * A wrong password and an unknown username take the SAME time. Skipping
      the bcrypt check when no user was found made a valid username ~1000x
      slower to reject than an invalid one, which handed out a reliable way to
      discover who has an account.
    * Repeated failures for a username start costing an enforced wait, so a
      password cannot simply be guessed at full speed.
    """
    if seconds_until_retry(username) > 0:
        return None

    user = session.scalar(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    # Always run the hash comparison, even with nobody to compare against.
    stored = user.password_hash if user is not None else _DUMMY_HASH
    matched = verify_password(password, stored)

    if user is not None and matched:
        _failures.pop(_key(username), None)
        return user

    count = _failures.get(_key(username), (0, 0.0))[0]
    _failures[_key(username)] = (count + 1, time.monotonic())
    return None
