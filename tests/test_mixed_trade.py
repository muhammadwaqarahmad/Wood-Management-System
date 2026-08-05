"""Mixed-load trades: several wood lines on one truck."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import build_party_ledger
from timber.core.reports import list_trades
from timber.core.transaction_service import (
    PAYER_US,
    WoodLine,
    create_mixed_trade,
    update_mixed_trade,
    void_trade,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture
def parties(session):
    bapari = admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI)
    factory = admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY)
    return {"bapari": bapari, "factory": factory}


def _lines():
    # 10 mud @ buy 1000/sell 1200  -> profit 2000
    # 5  mud @ buy 800 /sell 1000  -> profit 1000
    return [
        WoodLine(wood_type_id=None, muds=10, kg=0, bapari_rate=1000, factory_rate=1200),
        WoodLine(wood_type_id=None, muds=5, kg=0, bapari_rate=800, factory_rate=1000),
    ]


def test_mixed_creates_grouped_lines_and_totals(session, parties):
    created = create_mixed_trade(
        session, txn_date=date(2026, 1, 1),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=_lines(),
    )
    assert len(created) == 2
    # all share one group
    assert {c.group_id for c in created} == {created[0].id}
    total_profit = sum((c.profit for c in created), Decimal("0"))
    assert total_profit == Decimal("3000.00")  # 2000 + 1000

    # The Trades view shows it as ONE aggregated row.
    rows = list_trades(session)
    assert len(rows) == 1
    row = rows[0]
    assert row.is_mixed is True
    assert row.lines == 2
    assert row.muds == Decimal("15.00")
    assert row.purchase_bill == Decimal("14000.00")  # 10*1000 + 5*800
    assert row.sale_bill == Decimal("17000.00")       # 10*1200 + 5*1000
    assert row.profit == Decimal("3000.00")


def test_mixed_expenses_counted_once(session, parties):
    create_mixed_trade(
        session, txn_date=date(2026, 1, 1),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=_lines(),
        freight_amount=500, freight_payer=PAYER_US,  # we bear 500 once
    )
    rows = list_trades(session)
    # per-trade profit is the gross margin (3000). Freight is NOT a cash
    # transaction — it never becomes an expense, only a ledger deduction.
    assert rows[0].profit == Decimal("3000.00")
    from timber.core import expense_service
    assert expense_service.total_expenses(session) == Decimal("0.00")


def test_void_mixed_removes_all_lines(session, parties):
    created = create_mixed_trade(
        session, txn_date=date(2026, 1, 1),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=_lines(),
    )
    void_trade(session, created[0].id)
    assert list_trades(session) == []
    # both parties back to zero
    assert build_party_ledger(session, parties["bapari"].id).closing_balance == Decimal("0.00")
    assert build_party_ledger(session, parties["factory"].id).closing_balance == Decimal("0.00")


def test_update_mixed_trade_replaces_lines(session, parties):
    created = create_mixed_trade(
        session, txn_date=date(2026, 1, 1),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=_lines(),
    )
    new = update_mixed_trade(
        session, created[0].id, txn_date=date(2026, 1, 2),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=[WoodLine(None, muds=20, kg=0, bapari_rate=1000, factory_rate=1100)],
    )
    rows = list_trades(session)
    assert len(rows) == 1
    assert rows[0].lines == 1
    assert rows[0].profit == Decimal("2000.00")  # 20 * (1100-1000)
