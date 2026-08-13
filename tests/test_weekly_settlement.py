"""Weekly settlement: the weekly (left) side cleared week by week, with any
unpaid balance rolling into the next week and payments placed by their
RECEIVED date (not the day they were entered)."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.payment_service import create_payment
from timber.core.report_data import weekly_settlement_report
from timber.core.weekly_settlement import weekly_settlement
from timber.db.models import FactoryTxn
from timber.db.models.party import PARTY_FACTORY

D = Decimal


@pytest.fixture
def factory(session):
    f = admin_service.create_party(
        session, name="Weekly Co", party_type=PARTY_FACTORY
    )
    f.split_rate = D("0")  # enrolled; no wood rate => whole rate is weekly
    session.flush()
    return f


def _load(session, factory, d, amount):
    """A load whose whole value lands on the weekly side (no split, no freight)."""
    session.add(FactoryTxn(
        txn_date=d, party_id=factory.id, weight=D("1"),
        rate=D(str(amount)), bill=D(str(amount)), freight=D("0"),
    ))
    session.flush()


def _pay(session, factory, d, amount, entry_date=None):
    create_payment(
        session, txn_date=d, entry_date=entry_date, party_id=factory.id,
        amount=amount, split_side="left",
    )


def test_weekly_rollover(session, factory):
    _load(session, factory, date(2026, 8, 3), 50000)   # week 1
    _load(session, factory, date(2026, 8, 10), 60000)  # week 2
    _load(session, factory, date(2026, 8, 17), 45000)  # week 3
    _pay(session, factory, date(2026, 8, 5), 50000)    # week 1
    _pay(session, factory, date(2026, 8, 12), 40000)   # week 2
    _pay(session, factory, date(2026, 8, 18), 65000)   # week 3

    ws = weekly_settlement(session, factory.id, 2026, 8)
    outs = [w.carried_out for w in ws.weeks]
    assert outs == [D("0.00"), D("20000.00"), D("0.00"), D("0.00")]
    # Week 2's unpaid 20,000 carries INTO week 3, then clears there.
    assert ws.weeks[2].carried_in == D("20000.00")
    assert ws.closing == D("0.00")
    assert ws.total_charged == D("155000.00")
    assert ws.total_paid == D("155000.00")


def test_opening_carries_prior_activity(session, factory):
    # A load last month with no payment carries into this month's week 1.
    _load(session, factory, date(2026, 7, 20), 30000)
    ws = weekly_settlement(session, factory.id, 2026, 8)
    assert ws.opening == D("30000.00")
    assert ws.weeks[0].carried_in == D("30000.00")
    assert ws.closing == D("30000.00")   # nothing paid in August


def test_payment_placed_by_received_date(session, factory):
    _load(session, factory, date(2026, 8, 10), 10000)  # week 2
    # Received in week 2, but ENTERED in week 3 — must clear week 2.
    _pay(session, factory, date(2026, 8, 12), 10000, entry_date=date(2026, 8, 20))
    ws = weekly_settlement(session, factory.id, 2026, 8)
    assert ws.weeks[1].paid == D("10000.00")
    assert ws.weeks[1].carried_out == D("0.00")


def test_report_shape(session, factory):
    _load(session, factory, date(2026, 8, 10), 60000)
    rep = weekly_settlement_report(session, factory.id, 2026, 8)
    assert rep.headers[0] == "Week"
    assert len(rep.rows) == 4   # four day-of-month weeks
    assert dict(rep.summary)["Closing"] == "60,000.00"
