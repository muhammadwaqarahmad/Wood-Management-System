"""Tests for the entry-screen lookup helpers."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core.lookups import (
    last_rate_for_party,
    last_txn,
    recent_vehicles,
    txn_options,
)
from timber.core.transaction_service import create_bapari_txn
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI


@pytest.fixture
def bapari(session):
    p = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add(p)
    session.flush()
    return p


def test_last_rate_for_party(session, bapari):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=1000
    )
    create_bapari_txn(
        session, txn_date=date(2026, 1, 2), party_id=bapari.id, weight=1, rate=1100
    )
    assert last_rate_for_party(session, bapari.id, PARTY_BAPARI) == Decimal("1100.00")


def test_last_rate_none_when_no_txns(session, bapari):
    assert last_rate_for_party(session, bapari.id, PARTY_BAPARI) is None


def test_recent_vehicles_distinct(session, bapari):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=1,
        vehicle_no="LEA-1",
    )
    create_bapari_txn(
        session, txn_date=date(2026, 1, 2), party_id=bapari.id, weight=1, rate=1,
        vehicle_no="LEA-1",
    )
    create_bapari_txn(
        session, txn_date=date(2026, 1, 3), party_id=bapari.id, weight=1, rate=1,
        vehicle_no="LEA-2",
    )
    vehicles = recent_vehicles(session)
    assert "LEA-1" in vehicles and "LEA-2" in vehicles
    assert vehicles.count("LEA-1") == 1


def test_last_txn(session, bapari):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=1, rate=1
    )
    second = create_bapari_txn(
        session, txn_date=date(2026, 1, 2), party_id=bapari.id, weight=2, rate=2
    )
    assert last_txn(session, PARTY_BAPARI).id == second.id


def test_txn_options_shape(session, bapari):
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=bapari.id, weight=10, rate=1000
    )
    opts = txn_options(session, PARTY_BAPARI)
    assert len(opts) == 1
    assert opts[0]["rate"] == Decimal("1000.00")
    assert "Karim" in opts[0]["label"]
