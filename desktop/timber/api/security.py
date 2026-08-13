"""Login tokens (JWT) built on the desktop's existing bcrypt user accounts.

Two token types:
  * access  — short-lived, sent with every request (Authorization: Bearer).
  * refresh — long-lived, stored in the phone's secure keystore behind a
              biometric, and exchanged for new access tokens at /auth/refresh.
The ``type`` claim keeps them from being used interchangeably.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from timber.api import settings

_ALG = "HS256"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(hours=settings.ACCESS_TTL_HOURS),
    }
    return jwt.encode(payload, settings.API_SECRET, algorithm=_ALG)


def create_refresh_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=settings.REFRESH_TTL_DAYS),
    }
    return jwt.encode(payload, settings.API_SECRET, algorithm=_ALG)


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """Return a valid token's payload, or raise jwt.PyJWTError. When
    ``expected_type`` is given, a token of the wrong type is rejected."""
    payload = jwt.decode(token, settings.API_SECRET, algorithms=[_ALG])
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload
