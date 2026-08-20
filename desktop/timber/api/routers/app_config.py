"""App-wide settings the website can edit — currently the business name.

GET is public (the login page shows the name before anyone signs in); PUT needs
MANAGE_SETTINGS (admin), matching the desktop. Saving applies the name live in
this API process and persists it so every client/export picks it up too.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from timber.api.deps import get_session, require_permission
from timber.core.app_settings_service import business_name, save_business_name
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission

router = APIRouter(prefix="/settings", tags=["settings"])


class BusinessNameOut(BaseModel):
    name_en: str
    name_ur: str


class BusinessNameIn(BaseModel):
    name_en: str
    name_ur: str


@router.get("/business", response_model=BusinessNameOut)
def get_business_name(session: Session = Depends(get_session)) -> BusinessNameOut:
    """The active business name (English + Urdu). Public — the login screen and
    every page header show it, before sign-in included."""
    en, ur = business_name(session)
    return BusinessNameOut(name_en=en, name_ur=ur)


@router.put("/business", response_model=BusinessNameOut)
def set_business_name(
    body: BusinessNameIn,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(require_permission(Permission.MANAGE_SETTINGS)),
) -> BusinessNameOut:
    """Change the business name everywhere. Persists it and applies it live in
    this process (so /health, PDFs and the payer label update immediately);
    other clients/exports pick it up on their next start."""
    try:
        save_business_name(session, body.name_en, body.name_ur)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    en, ur = business_name(session)
    return BusinessNameOut(name_en=en, name_ur=ur)
