"""Payment dual dates: the received date (``txn_date``, drives the ledger and
which week it settles) vs the entry date (``entry_date``, when it was booked —
audit only). Fixes "received in week 2, entered in week 3"."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.payment_service import create_payment, update_payment
from timber.core.report_data import detailed_statement_report
from timber.db.models.party import PARTY_FACTORY

D = Decimal


@pytest.fixture
def factory(session):
    return admin_service.create_party(
        session, name="Star Factory", party_type=PARTY_FACTORY
    )


def test_entry_date_defaults_to_received(session, factory):
    p = create_payment(
        session, txn_date=date(2026, 8, 3), party_id=factory.id, amount=1000
    )
    assert p.txn_date == date(2026, 8, 3)
    assert p.entry_date == date(2026, 8, 3)  # defaults to the received date


def test_entry_date_kept_separate(session, factory):
    # Received in week 2, but booked in week 3.
    p = create_payment(
        session, txn_date=date(2026, 8, 10), entry_date=date(2026, 8, 18),
        party_id=factory.id, amount=5000,
    )
    assert p.txn_date == date(2026, 8, 10)    # drives the ledger (week 2)
    assert p.entry_date == date(2026, 8, 18)  # audit only (week 3)


def test_update_changes_entry_date(session, factory):
    p = create_payment(
        session, txn_date=date(2026, 8, 3), party_id=factory.id, amount=1000
    )
    update_payment(
        session, p.id, txn_date=date(2026, 8, 3),
        entry_date=date(2026, 8, 20), amount=1000,
    )
    assert p.entry_date == date(2026, 8, 20)
    assert p.txn_date == date(2026, 8, 3)     # received date unchanged


def test_update_without_entry_date_preserves_it(session, factory):
    p = create_payment(
        session, txn_date=date(2026, 8, 3), entry_date=date(2026, 8, 5),
        party_id=factory.id, amount=1000,
    )
    update_payment(session, p.id, txn_date=date(2026, 8, 3), amount=2000)
    assert p.entry_date == date(2026, 8, 5)   # left alone when not passed


def test_statement_notes_backdated_entry(session, factory):
    """A back-dated payment shows its entry date in the statement export."""
    create_payment(
        session, txn_date=date(2026, 8, 10), entry_date=date(2026, 8, 18),
        party_id=factory.id, amount=5000,
    )
    rep = detailed_statement_report(session, factory.id)
    blob = " | ".join(str(c) for row in rep.rows for c in row)
    assert "2026-08-10" in blob   # received date is the row date
    assert "2026-08-18" in blob   # entry date noted in the description


def test_statement_no_note_when_dates_match(session, factory):
    create_payment(
        session, txn_date=date(2026, 8, 10), party_id=factory.id, amount=5000
    )
    rep = detailed_statement_report(session, factory.id)
    blob = " | ".join(str(c) for row in rep.rows for c in row)
    # Same-day entry: no separate entry-date note clutters the row.
    assert "Entry date" not in blob
