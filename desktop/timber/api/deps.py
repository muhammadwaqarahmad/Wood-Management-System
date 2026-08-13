"""Shared FastAPI dependencies: a DB session and the current signed-in user."""
from __future__ import annotations

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from timber.api.security import decode_token
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import User

_bearer = HTTPBearer(auto_error=True)


def get_session() -> Iterator[Session]:
    """One DB session per request, always closed."""
    with SessionLocal() as session:
        yield session


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_session),
) -> CurrentUser:
    """Resolve the caller from their bearer token, or 401."""
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired login. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(creds.credentials, expected_type="access")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise cred_exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise cred_exc
    return CurrentUser.from_user(user)


def require_permission(permission: Permission):
    """Dependency factory for write endpoints: allow the request only if the
    caller's role has ``permission``, else 403. Reuses the SAME permission table
    the desktop enforces (``timber.core.permissions``), so the web can never do
    anything a role isn't allowed to."""

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to do this.",
            )
        return user

    return _dep
