"""Password hashing — a thin, safe wrapper over bcrypt.

We only ever store the hash (``User.password_hash``), never the plain
password. bcrypt salts automatically, so identical passwords produce
different hashes.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain-text password; returns a utf-8 string to store."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the stored ``hashed`` value."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/empty hash — treat as a failed login, never crash.
        return False
