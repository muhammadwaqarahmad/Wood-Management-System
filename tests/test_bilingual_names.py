"""Bilingual master-data names: the same party / account reads in whichever
language the app is set to, for seeded and newly-entered rows alike."""

from decimal import Decimal

import pytest

from timber.core import admin_service, bank_service
from timber.core.search import global_search
from timber.db.models.party import PARTY_BAPARI
from timber import i18n


@pytest.fixture(autouse=True)
def _english():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def test_party_reads_in_current_language(session):
    admin_service.create_party(
        session, name_en="Khalid Hussain", name_ur="خالد حسین",
        party_type=PARTY_BAPARI,
    )
    session.flush()
    p = session.query(admin_service.Party).first()
    i18n.set_language("en")
    assert p.name == "Khalid Hussain"
    i18n.set_language("ur")
    assert p.name == "خالد حسین"


def test_single_name_mirrors_to_both(session):
    # Only one name given → shows the same in both languages (never blank).
    p = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    session.flush()
    assert p.name_en == "Karim" and p.name_ur == "Karim"
    i18n.set_language("ur")
    assert p.name == "Karim"


def test_search_matches_either_language(session):
    admin_service.create_party(
        session, name_en="Best Board Nooriabad", name_ur="بیسٹ بورڈ نوری آباد",
        party_type=PARTY_BAPARI,
    )
    session.flush()
    # Searching either language finds the party (shown with its English name
    # here because the app is in English).
    assert any(r.name == "Best Board Nooriabad"
               for r in global_search(session, "Nooriabad"))
    assert any(r.name == "Best Board Nooriabad"
               for r in global_search(session, "بیسٹ"))


def test_cash_account_not_duplicated_in_urdu(session):
    first = bank_service.cash_account(session)
    session.flush()
    i18n.set_language("ur")
    again = bank_service.cash_account(session)  # must find, not re-create
    assert again.id == first.id
    assert again.name == "نقد"          # localized
    assert again._name == "Cash"        # stable key


def test_account_dedup_across_languages(session):
    bank_service.create_account(session, name_en="HBL Main", name_ur="ایچ بی ایل مین")
    session.flush()
    # Same English name → rejected even though we're in Urdu now.
    i18n.set_language("ur")
    with pytest.raises(ValueError, match="already exists"):
        bank_service.create_account(session, name_en="HBL Main", name_ur="کچھ اور")


def test_ordering_follows_language(session):
    for en, ur in (("Zebra", "الف"), ("Apple", "ی")):
        admin_service.create_party(
            session, name_en=en, name_ur=ur, party_type=PARTY_BAPARI
        )
    session.flush()
    from sqlalchemy import select
    from timber.db.models import Party

    i18n.set_language("en")
    en_order = [p.name for p in session.scalars(select(Party).order_by(Party.name))]
    assert en_order == ["Apple", "Zebra"]
    i18n.set_language("ur")
    ur_order = [p.name for p in session.scalars(select(Party).order_by(Party.name))]
    assert ur_order == ["الف", "ی"]  # Zebra(الف) before Apple(ی)
