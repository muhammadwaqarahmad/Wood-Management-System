"""Tests for management services and the audit reader."""

import pytest

from timber.core import admin_service
from timber.core.audit import recent_audit
from timber.core.auth import authenticate
from timber.core.permissions import Role
from timber.db.models import Location, Party, WoodType
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def test_create_lookup_and_duplicate(session):
    admin_service.create_lookup(session, Location, "Lahore")
    with pytest.raises(ValueError, match="already exists"):
        admin_service.create_lookup(session, Location, "Lahore")


def test_rename_and_deactivate_lookup(session):
    wt = admin_service.create_lookup(session, WoodType, "Kikar")
    admin_service.rename_lookup(session, WoodType, wt.id, "Babul")
    assert session.get(WoodType, wt.id).name == "Babul"
    admin_service.set_lookup_active(session, WoodType, wt.id, False)
    assert session.get(WoodType, wt.id).is_active is False


def test_create_party_validates_type(session):
    with pytest.raises(ValueError, match="bapari or factory"):
        admin_service.create_party(session, name="X", party_type="wholesaler")


def test_create_and_update_party(session):
    p = admin_service.create_party(
        session, name="Karim", party_type=PARTY_BAPARI,
        phones=["0300", "0311"], email="k@x.com",
    )
    assert {ph.phone for ph in p.phones} == {"0300", "0311"}
    admin_service.update_party(session, p.id, name="Karim Timber", phones=["0322"])
    fresh = session.get(Party, p.id)
    assert fresh.name == "Karim Timber"
    assert [ph.phone for ph in fresh.phones] == ["0322"]  # replaced


def test_party_bank_details(session):
    p = admin_service.create_party(
        session, name="ABC", party_type=PARTY_BAPARI,
        banks=[
            {"account_title": "ABC Traders", "bank_name": "HBL",
             "iban": "PK00HBL000", "account_number": "12345"},
        ],
    )
    fresh = session.get(Party, p.id)
    assert len(fresh.banks) == 1
    assert fresh.banks[0].bank_name == "HBL"
    assert fresh.banks[0].iban == "PK00HBL000"
    # add a second bank via update
    admin_service.update_party(
        session, p.id,
        banks=[
            {"account_title": "ABC Traders", "bank_name": "HBL",
             "iban": "PK00HBL000", "account_number": "12345"},
            {"account_title": "ABC2", "bank_name": "UBL",
             "iban": "PK00UBL999", "account_number": "999"},
        ],
    )
    fresh = session.get(Party, p.id)
    assert len(fresh.banks) == 2


def test_factory_credit_days(session):
    p = admin_service.create_party(
        session, name="ABC", party_type=PARTY_FACTORY, credit_days=30
    )
    assert session.get(Party, p.id).credit_days == 30


def test_delete_party_when_clean(session):
    p = admin_service.create_party(session, name="Temp", party_type=PARTY_BAPARI)
    admin_service.delete_party(session, p.id)
    assert session.get(Party, p.id) is None


def test_delete_party_blocked_with_transactions(session):
    from datetime import date

    from timber.core.transaction_service import create_bapari_txn

    p = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=p.id, weight=1, rate=1
    )
    with pytest.raises(ValueError, match="Cannot delete"):
        admin_service.delete_party(session, p.id)


def test_only_admin_can_delete():
    from timber.core.permissions import Permission, Role, has_permission

    assert has_permission(Role.ADMIN, Permission.DELETE_RECORD)
    assert not has_permission(Role.MANAGER, Permission.DELETE_RECORD)
    assert not has_permission(Role.DATA_ENTRY, Permission.DELETE_RECORD)


def test_link_bapari_to_factories(session):
    from timber.core.lookups import linked_factory_ids

    f1 = admin_service.create_party(session, name="F1", party_type=PARTY_FACTORY)
    f2 = admin_service.create_party(session, name="F2", party_type=PARTY_FACTORY)
    b = admin_service.create_party(
        session, name="B1", party_type=PARTY_BAPARI, linked_factory_ids=[f1.id]
    )
    assert linked_factory_ids(session, b.id) == [f1.id]
    admin_service.update_party(session, b.id, linked_factory_ids=[f1.id, f2.id])
    assert set(linked_factory_ids(session, b.id)) == {f1.id, f2.id}
    # unlink
    admin_service.update_party(session, b.id, linked_factory_ids=[])
    assert linked_factory_ids(session, b.id) == []


def test_user_lifecycle(session):
    u = admin_service.create_user_account(
        session, username="ali", password="pass123", role=Role.MANAGER
    )
    # duplicate
    with pytest.raises(ValueError, match="already exists"):
        admin_service.create_user_account(
            session, username="ali", password="x", role=Role.VIEWER
        )
    # change role + reset password
    admin_service.update_user(session, u.id, role=Role.ACCOUNTANT)
    admin_service.reset_password(session, u.id, "newpass")
    assert authenticate(session, "ali", "newpass") is not None
    assert session.get(type(u), u.id).role == "Accountant"


def test_audit_reader(session):
    admin_service.create_lookup(session, Location, "Lahore")
    rows = recent_audit(session)
    assert rows
    assert rows[0].entity == "locations"
    assert rows[0].action == "create"
