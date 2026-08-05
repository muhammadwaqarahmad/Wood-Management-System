"""First-run bootstrap and optional demo data.

- ``ensure_admin`` runs at every startup: if there are no users yet it
  creates a default admin (username ``admin`` / password ``admin123``)
  so the app is usable out of the box. Change the password after login.
- ``seed_sample_data`` is opt-in (``python -m timber.db.seed``) and adds
  example locations, wood types, and parties so the dropdowns aren't
  empty while we build the UI.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from timber.core.auth import create_user
from timber.core.permissions import Role
from timber.db.engine import SessionLocal
from timber.db.models import Location, Party, User, WoodType
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def ensure_admin(session) -> bool:
    """Create a default admin if no users exist. Returns True if created.

    Safe to call concurrently: if another instance creates the admin at the
    same time, the duplicate insert is caught and treated as "already done".
    """
    if session.scalar(select(User).limit(1)) is not None:
        return False
    try:
        create_user(
            session,
            "admin",
            "admin123",
            role=Role.ADMIN,
            full_name="Administrator",
        )
        session.commit()
        return True
    except IntegrityError:
        session.rollback()  # a concurrent first-run already created the admin
        return False


def _get_or_create(session, model, name, **extra):
    obj = session.scalar(select(model).where(model.name == name))
    if obj is None:
        obj = model(name=name, **extra)
        session.add(obj)
        session.flush()
    return obj


def seed_sample_data(session) -> None:
    """Add example reference data (idempotent)."""
    for city in ("Lahore", "Faisalabad", "Gujranwala"):
        _get_or_create(session, Location, city)

    for wood in ("Kikar", "Sheesham", "Poplar", "Eucalyptus"):
        _get_or_create(session, WoodType, wood)

    lahore = session.scalar(select(Location).where(Location.name == "Lahore"))
    for name in ("Karim Timber", "Rashid Wood Supply"):
        _get_or_create(
            session, Party, name,
            party_type=PARTY_BAPARI,
            location_id=lahore.id,
            opening_balance=Decimal("0.00"),
        )
    for name in ("Al-Madina Factory", "Pak Plywood Mills"):
        _get_or_create(
            session, Party, name,
            party_type=PARTY_FACTORY,
            location_id=lahore.id,
            opening_balance=Decimal("0.00"),
        )
    session.commit()


if __name__ == "__main__":
    with SessionLocal() as s:
        created = ensure_admin(s)
        seed_sample_data(s)
    print("Admin created." if created else "Admin already existed.")
    print("Sample locations, wood types, and parties seeded.")
