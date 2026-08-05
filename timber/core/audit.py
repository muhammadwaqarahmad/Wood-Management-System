"""Audit trail helper — record who did what.

Every create/edit/void/login goes through here so the ``audit_log``
table stays a complete history. Does not commit; the caller controls
the transaction boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from timber.db.models import AuditLog


def prune_audit_log(session: Session, days: int | None = None) -> int:
    """Delete audit entries older than the retention window (default from
    ``config.AUDIT_RETENTION_DAYS``). Returns how many were removed; the caller
    commits. ``days <= 0`` keeps everything.

    The cutoff uses the DATABASE's own clock so it matches ``created_at`` (set
    by ``func.now()``) no matter what timezone the PC is in."""
    from timber import config

    if days is None:
        try:
            days = int(config.AUDIT_RETENTION_DAYS)
        except (TypeError, ValueError):
            days = 3
    if days <= 0:
        return 0

    n = int(days)  # int-cast guards the interval literal below
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        cutoff = func.now() - text(f"make_interval(days => {n})")
    else:  # sqlite (and anything else): UTC 'now' matches CURRENT_TIMESTAMP
        cutoff = func.datetime("now", f"-{n} days")
    result = session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    return result.rowcount or 0


def log_action(
    session: Session,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
    )
    session.add(entry)
    return entry


@dataclass
class AuditRow:
    when: datetime
    username: str
    action: str
    entity: str
    entity_id: int | None
    details: str | None


def recent_audit(session: Session, limit: int = 500) -> list[AuditRow]:
    """Most recent audit entries (newest first) with the user's name."""
    rows: list[AuditRow] = []
    for a in session.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    ):
        rows.append(
            AuditRow(
                when=a.created_at,
                username=a.user.username if a.user else "—",
                action=a.action,
                entity=a.entity,
                entity_id=a.entity_id,
                details=a.details,
            )
        )
    return rows
