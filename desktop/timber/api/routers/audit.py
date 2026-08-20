"""Audit log — read-only feed of every create / edit / delete.

Reuses timber.core.audit.recent_audit (the SAME data the desktop shows) and is
gated on VIEW_AUDIT, matching the desktop's own permission.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from timber.api.deps import get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.audit import recent_audit
from timber.core.permissions import Permission

router = APIRouter(prefix="/audit", tags=["audit"])
_VIEW = require_permission(Permission.VIEW_AUDIT)


@router.get("")
def list_audit(limit: int = 500, session: Session = Depends(get_session), _=Depends(_VIEW)) -> list[dict]:
    """Most recent audit entries (newest first)."""
    rows = recent_audit(session, limit=min(max(limit, 1), 2000))
    return [
        {
            "when": jsonable(r.when),
            "username": r.username,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "details": r.details,
        }
        for r in rows
    ]
