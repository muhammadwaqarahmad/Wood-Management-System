"""Audit-log retention: entries older than the window are pruned; recent ones
and the whole table (when retention is 0) are kept."""

from sqlalchemy import func, select, text

from timber.core.audit import log_action, prune_audit_log
from timber.db.models import AuditLog, User


def _admin(session):
    u = User(username="admin", password_hash="x", role="admin")
    session.add(u)
    session.flush()
    return u


def test_prune_removes_only_old_entries(session):
    u = _admin(session)
    old_ids = []
    for i in range(3):
        a = log_action(session, u.id, "create", "trades", i)
        session.flush()
        old_ids.append(a.id)
    # Backdate the three entries to 10 days ago.
    session.execute(
        text("UPDATE audit_log SET created_at = datetime('now','-10 days') "
             "WHERE id IN (:a,:b,:c)"),
        {"a": old_ids[0], "b": old_ids[1], "c": old_ids[2]},
    )
    for _ in range(2):  # two fresh entries
        log_action(session, u.id, "login", "users", None)
    session.flush()

    assert session.scalar(select(func.count(AuditLog.id))) == 5
    removed = prune_audit_log(session, days=3)
    assert removed == 3
    assert session.scalar(select(func.count(AuditLog.id))) == 2


def test_retention_zero_keeps_everything(session):
    u = _admin(session)
    log_action(session, u.id, "create", "trades", 1)
    session.flush()
    assert prune_audit_log(session, days=0) == 0
    assert session.scalar(select(func.count(AuditLog.id))) == 1
