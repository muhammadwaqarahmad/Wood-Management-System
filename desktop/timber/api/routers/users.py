"""User accounts — create / edit / reset password / activate / delete.

Admin-only surface: every endpoint requires MANAGE_USERS (same as the desktop's
User Manager). Reuses ``admin_service`` so validation and audit match exactly.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.api.deps import get_session, require_permission
from timber.core.admin_service import (
    create_user_account,
    delete_user,
    reset_password,
    update_user,
)
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.db.models import User

router = APIRouter(prefix="/users", tags=["users"])

_MANAGE = require_permission(Permission.MANAGE_USERS)


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str = "Viewer"
    full_name: str | None = None


class UserEditIn(BaseModel):
    role: str | None = None
    full_name: str | None = None
    is_active: bool | None = None


class PasswordIn(BaseModel):
    password: str


@router.get("")
def list_users(session: Session = Depends(get_session),
               _user: CurrentUser = Depends(_MANAGE)) -> list[dict]:
    rows = session.scalars(select(User).order_by(User.username)).all()
    return [
        {"id": u.id, "username": u.username, "full_name": u.full_name or "",
         "role": u.role, "is_active": bool(u.is_active)}
        for u in rows
    ]


@router.post("")
def create(body: UserCreateIn, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        u = create_user_account(
            session, username=body.username, password=body.password,
            role=body.role, full_name=body.full_name, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": u.id}


@router.put("/{user_id}")
def update(user_id: int, body: UserEditIn, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        update_user(
            session, user_id, role=body.role, full_name=body.full_name,
            is_active=body.is_active, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{user_id}/password")
def reset(user_id: int, body: PasswordIn, session: Session = Depends(get_session),
          user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        reset_password(session, user_id, body.password, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/{user_id}")
def delete(user_id: int, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_MANAGE)) -> dict:
    try:
        delete_user(session, user_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
