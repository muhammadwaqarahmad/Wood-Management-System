"""Shared pytest fixtures.

Every test gets a fresh in-memory SQLite database, so tests are fast,
isolated, and never touch the real ``storage/timber.db``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from timber.db.engine import Base
import timber.db.models  # noqa: F401 - registers models on Base.metadata


@pytest.fixture(autouse=True)
def _reset_language(monkeypatch):
    """Language is global state (``i18n._current``). Pin it to English before
    each test so one test switching to Urdu can't leak into another. Tests
    that need Urdu set it themselves."""
    from timber import i18n

    monkeypatch.setattr(i18n, "_current", "en")
    yield


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s
