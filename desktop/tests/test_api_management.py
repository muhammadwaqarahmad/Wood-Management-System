"""API: management write endpoints — parties, bank accounts, unknown receipts,
master data (locations/wood types), users, and factory split rates.

Route-function level (in-memory ``session`` fixture + a CurrentUser), reusing the
desktop services. Proves each write path works end to end.
"""
from __future__ import annotations

from datetime import date

from timber.core.current_user import CurrentUser
from timber.db.models import Party, WoodType
from timber.db.models.party import PARTY_FACTORY
from timber.api.routers import ledgers as L
from timber.api.routers import master as MA
from timber.api.routers import money as MO
from timber.api.routers import parties as P
from timber.api.routers import payments as PAY
from timber.api.routers import users as U

# id well clear of any row we create, so deleting a created user isn't "self".
ADMIN = CurrentUser(id=999, username="admin", role="Admin")


# --- parties ---
def test_party_create_and_delete(session):
    r = P.create(P.PartyIn(party_type="factory", name_en="ABC Mills"),
                 session=session, user=ADMIN)
    assert r["id"] > 0
    assert P.delete(r["id"], session=session, user=ADMIN)["ok"] is True


def test_party_create_and_deactivate(session):
    r = P.create(P.PartyIn(party_type="supplier", name_en="Karim Traders"),
                 session=session, user=ADMIN)
    assert P.set_active(r["id"], active=False, session=session, user=ADMIN)["ok"]


# --- bank accounts ---
def test_account_create_and_update(session):
    r = MO.create_account_ep(MO.AccountIn(name_en="HBL Main", opening_balance=1000),
                             session=session, user=ADMIN)
    assert r["id"] > 0
    ok = MO.update_account_ep(r["id"], MO.AccountIn(name_en="HBL Main", branch="Model Town"),
                              session=session, user=ADMIN)
    assert ok["ok"] is True


# --- unknown receipts ---
def test_unknown_create_and_void(session):
    acct = MO.create_account_ep(MO.AccountIn(name_en="Cash", opening_balance=0),
                                session=session, user=ADMIN)["id"]
    r = PAY.create_unknown(
        PAY.UnknownIn(txn_date=date.today(), amount=2500, bank_account_id=acct),
        session=session, user=ADMIN)
    assert r["id"] > 0
    assert PAY.void_unknown(r["id"], session=session, user=ADMIN)["ok"] is True


# --- master data ---
def test_master_wood_type_create_rename_delete(session):
    r = MA.create("wood_type", MA.NameIn(name="Oak"), session=session, user=ADMIN)
    assert r["id"] > 0
    assert MA.rename("wood_type", r["id"], MA.NameIn(name="Red Oak"),
                     session=session, user=ADMIN)["ok"]
    assert MA.delete("wood_type", r["id"], session=session, user=ADMIN)["ok"]


# --- users ---
def test_user_create_and_delete(session):
    r = U.create(U.UserCreateIn(username="dataentry1", password="secret123",
                                role="Data Entry", full_name="Ali"),
                 session=session, user=ADMIN)
    assert r["id"] > 0
    assert U.delete(r["id"], session=session, user=ADMIN)["ok"] is True


# --- factory split rates ---
def test_set_factory_split_rates(session):
    fac = Party(name="Factory Z", party_type=PARTY_FACTORY, is_active=True)
    wood = WoodType(name="Deodar", is_active=True)
    session.add_all([fac, wood])
    session.commit()
    ok = L.set_factory_split_rates(
        fac.id, L.SplitRatesIn(rates={str(wood.id): 40.0}),
        session=session, _user=ADMIN)
    assert ok["ok"] is True
