"""Duplicate-entry guard: the same truck (vehicle + date + weight) can't be
entered twice — stops two data-entry staff double-entering one slip. The
same vehicle/weight on a DIFFERENT date is a genuinely new load and allowed.
"""

from datetime import date

import pytest

from timber.core import admin_service
from timber.core.transaction_service import (
    WoodLine,
    create_mixed_trade,
    create_trade,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

D1 = date(2026, 7, 1)
D2 = date(2026, 7, 2)


@pytest.fixture
def world(session):
    s = admin_service.create_party(session, name="Sup", party_type=PARTY_BAPARI)
    f = admin_service.create_party(session, name="Fac", party_type=PARTY_FACTORY)
    session.flush()
    return dict(s=s.id, f=f.id)


def _trade(session, world, day, vehicle, muds):
    return create_trade(
        session, txn_date=day, muds=muds, kg=0,
        bapari_id=world["s"], bapari_rate=400,
        factory_id=world["f"], factory_rate=450, vehicle_no=vehicle,
    )


def test_same_truck_blocked(session, world):
    _trade(session, world, D1, "LEA-123", 200)
    with pytest.raises(ValueError, match="already entered"):
        _trade(session, world, D1, "LEA-123", 200)


def test_vehicle_matching_is_case_and_space_insensitive(session, world):
    _trade(session, world, D1, "LEA-123", 200)
    with pytest.raises(ValueError):
        _trade(session, world, D1, "  lea-123 ", 200)


def test_different_date_allowed(session, world):
    _trade(session, world, D1, "LEA-123", 200)
    # Same vehicle + weight but next day = a real new load.
    _trade(session, world, D2, "LEA-123", 200)


def test_different_weight_allowed(session, world):
    _trade(session, world, D1, "LEA-123", 200)
    _trade(session, world, D1, "LEA-123", 250)   # different weight


def test_no_vehicle_number_not_blocked(session, world):
    # With no vehicle number there's nothing to match on — both allowed.
    _trade(session, world, D1, "", 200)
    _trade(session, world, D1, None, 200)


def test_db_level_unique_constraint(session, world):
    """The fingerprint table itself refuses a second identical key — this is
    the atomic backstop for the same-millisecond race."""
    from sqlalchemy.exc import IntegrityError

    from timber.db.models import TradeKey

    _, _, combined = _trade(session, world, D1, "RACE-1", 200)
    session.add(TradeKey(
        group_id=combined.id, txn_date=D1, vehicle_key="race-1",
        total_weight=200,
    ))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_void_then_reenter_allowed(session, world):
    """Voiding a trade removes its fingerprint, so a corrected re-entry of the
    same truck is allowed again."""
    from timber.core.transaction_service import void_trade

    _, _, combined = _trade(session, world, D1, "LEA-999", 200)
    void_trade(session, combined.id)
    session.flush()
    # Same truck can now be entered again (the void cleared the key).
    _trade(session, world, D1, "LEA-999", 200)


def test_edit_keeps_guard_consistent(session, world):
    """Editing a trade (void + recreate) leaves exactly one live key, and the
    edited truck still can't be duplicated."""
    from timber.core.transaction_service import update_mixed_trade

    _, _, combined = _trade(session, world, D1, "EDIT-1", 200)
    update_mixed_trade(
        session, combined.group_id or combined.id,
        txn_date=D1, bapari_id=world["s"], factory_id=world["f"],
        lines=[WoodLine(wood_type_id=None, muds=250, kg=0,
                        bapari_rate=400, factory_rate=450)],
        vehicle_no="EDIT-1",
    )
    # The edited weight (250) is now the live key -> re-entering it is blocked.
    with pytest.raises(ValueError):
        _trade(session, world, D1, "EDIT-1", 250)
    # The OLD weight (200) was freed by the edit -> allowed again.
    _trade(session, world, D1, "EDIT-1", 200)


def test_mixed_load_total_weight_dedup(session, world):
    lines = [
        WoodLine(wood_type_id=None, muds=100, kg=0, bapari_rate=400, factory_rate=450),
        WoodLine(wood_type_id=None, muds=150, kg=0, bapari_rate=400, factory_rate=450),
    ]
    create_mixed_trade(
        session, txn_date=D1, bapari_id=world["s"], factory_id=world["f"],
        lines=lines, vehicle_no="TRUCK-9",
    )
    # Same truck, same total (250) -> blocked.
    with pytest.raises(ValueError, match="already entered"):
        create_mixed_trade(
            session, txn_date=D1, bapari_id=world["s"], factory_id=world["f"],
            lines=lines, vehicle_no="TRUCK-9",
        )
