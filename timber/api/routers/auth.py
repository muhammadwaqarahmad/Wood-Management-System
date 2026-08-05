"""Login + token refresh — reuses the desktop's bcrypt authentication + throttle."""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from timber.api.deps import get_current_user, get_session
from timber.api.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from timber.core.auth import authenticate, seconds_until_retry
from timber.core.current_user import CurrentUser
from timber.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    name: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut


class AccessOut(BaseModel):
    access_token: str
    refresh_token: str


def _tokens_for(user: User) -> tuple[str, str]:
    return create_access_token(user.id, user.role), create_refresh_token(user.id)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: Session = Depends(get_session)) -> TokenOut:
    user = authenticate(session, body.username, body.password)
    if user is None:
        wait = seconds_until_retry(body.username)
        if wait > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in {int(wait) + 1}s.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong username or password.",
        )
    access, refresh = _tokens_for(user)
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        user=UserOut(id=user.id, username=user.username, role=user.role,
                     name=user.full_name),
    )


@router.post("/refresh", response_model=AccessOut)
def refresh(body: RefreshIn, session: Session = Depends(get_session)) -> AccessOut:
    """Exchange a valid refresh token for a fresh access token. The refresh
    token is ROTATED (a new one is issued) so a leaked/old one stops working."""
    bad = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired. Please sign in again.",
    )
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise bad
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise bad
    access, new_refresh = _tokens_for(user)
    return AccessOut(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(get_current_user)) -> UserOut:
    """Who the current access token belongs to — the app uses this to validate
    a restored session."""
    return UserOut(id=current.id, username=current.username, role=current.role,
                   name=current.full_name)
