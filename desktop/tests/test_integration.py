"""End-to-end: data in via services -> dashboard/ledgers/reports all
reconcile with each other.
"""

from datetime import date
from decimal import Decimal

from timber.core import admin_service
from timber.core.dashboard import dashboard_cards
from timber.core.ledger import net_position, total_payable, total_receivable
from timber.core.payment_service import create_payment
from timber.core.report_data import profit_loss
from timber.core.reports import profit_ledger
from timber.core.transaction_service import (
    create_bapari_txn,
    create_combined_txn,
    create_factory_txn,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def test_full_business_flow(session):
    # Reference data + parties via the admin service.
    loc = admin_service.create_lookup(session, __import_location(), "Lahore")
    bapari = admin_service.create_party(
        session, name="Karim", party_type=PARTY_BAPARI
    )
    factory = admin_service.create_party(
        session, name="ABC", party_type=PARTY_FACTORY
    )

    # Buy, sell, link, and settle some money.
    b = create_bapari_txn(
        session, txn_date=date.today(), party_id=bapari.id,
        weight=10, rate=1000, freight=500, location_id=loc.id,
    )
    f = create_factory_txn(
        session, txn_date=date.today(), party_id=factory.id,
        weight=10, rate=1300, location_id=loc.id,
    )
    create_combined_txn(session, bapari_txn_id=b.id, factory_txn_id=f.id)
    create_payment(session, txn_date=date.today(), party_id=bapari.id, amount=4000)
    create_payment(session, txn_date=date.today(), party_id=factory.id, amount=5000)

    cards = dashboard_cards(session)

    # Payable = 10,500 - 4,000 ; Receivable = 13,000 - 5,000
    assert total_payable(session) == Decimal("6500.00")
    assert total_receivable(session) == Decimal("8000.00")
    assert cards.payable == total_payable(session)
    assert cards.receivable == total_receivable(session)
    assert cards.net == net_position(session)

    # Profit reconciles across dashboard, ledger, and P&L report.
    rows, profit_total = profit_ledger(session)
    assert profit_total == Decimal("3000.00")  # (1300-1000)*10
    assert cards.total_profit == profit_total

    pl = profit_loss(session)
    profit_line = [r for r in pl.rows if r[1] == "3,000.00"]
    assert profit_line, "profit should appear in the P&L report"


def __import_location():
    # Local import keeps the model out of the module's import list.
    from timber.db.models import Location

    return Location
