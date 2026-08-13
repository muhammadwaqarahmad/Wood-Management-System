"""Tests for first-run seeding (admin bootstrap)."""

from sqlalchemy import func, select

from timber.db.models import User
from timber.db.seed import ensure_admin


def test_ensure_admin_creates_once(session):
    assert ensure_admin(session) is True
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_ensure_admin_is_idempotent(session):
    # First run creates the admin; subsequent runs must NOT crash or
    # create a duplicate (the bug behind the "UNIQUE constraint failed:
    # users.username" startup error).
    assert ensure_admin(session) is True
    assert ensure_admin(session) is False
    assert ensure_admin(session) is False
    assert session.scalar(select(func.count()).select_from(User)) == 1
