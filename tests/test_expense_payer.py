"""Who-paid (loading/freight/unloading) shows the real party name."""

from datetime import date
from decimal import Decimal

import pytest

from timber import config, i18n
from timber.core import admin_service
from timber.core.labels import expense_text, payer_label
from timber.core.reports import list_trades, trade_ledger
from timber.core.transaction_service import create_trade
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setattr(i18n, "get_language", lambda: "en")


@pytest.fixture
def parties(session):
    return {
        "bapari": admin_service.create_party(session, name="Karim", party_type=PARTY_BAPARI),
        "factory": admin_service.create_party(session, name="ABC", party_type=PARTY_FACTORY),
    }


def test_payer_label_resolves_names():
    assert payer_label(PAYER_US) == config.APP_NAME            # business name
    assert payer_label(PAYER_BAPARI, "Karim", "ABC") == "Karim"
    assert payer_label(PAYER_FACTORY, "Karim", "ABC") == "ABC"


def test_expense_text_format():
    assert expense_text(0, PAYER_US) == ""
    assert expense_text(500, PAYER_BAPARI, "Karim", "ABC") == "500.00 (Karim)"
    assert expense_text(300, PAYER_FACTORY, "Karim", "ABC") == "300.00 (ABC)"


def test_expense_split_text_rupees():
    # single payer
    assert expense_text(500, PAYER_US) == f"500.00 ({config.APP_NAME})"
    # split: us pays 350, factory pays the rest (150)
    out = expense_text(500, PAYER_US, "Karim", "ABC", PAYER_FACTORY, 350)
    assert out == f"500.00 (350.00 {config.APP_NAME}, 150.00 ABC)"


def test_trade_split_expense_charges(session, parties):
    # freight 500 split: us 350, factory 150 -> factory portion raises sale
    create_trade(
        session, txn_date=date(2026, 1, 1), muds=10, kg=0,
        bapari_id=parties["bapari"].id, bapari_rate=1000,
        factory_id=parties["factory"].id, factory_rate=1200,
        freight_amount=500, freight_payer=PAYER_US,
        freight_payer2=PAYER_FACTORY, freight_split=350,
    )
    row = list_trades(session)[0]
    assert row.freight == Decimal("500.00")
    assert row.freight_payer == PAYER_US
    assert row.freight_payer2 == PAYER_FACTORY
    assert row.freight_split == Decimal("350.00")
    # Per-trade profit is gross (12000 - 10000 = 2000); our 350 share becomes
    # a real expense, the factory's 150 share is informational.
    led = trade_ledger(session)[0][0]
    assert led.sale_bill == Decimal("12000.00")
    assert led.profit == Decimal("2000.00")


def test_edit_preserves_split(session, parties):
    from timber.core.transaction_service import update_mixed_trade
    from timber.core.transaction_service import WoodLine

    b, f, c = create_trade(
        session, txn_date=date(2026, 1, 1), muds=10, kg=0,
        bapari_id=parties["bapari"].id, bapari_rate=1000,
        factory_id=parties["factory"].id, factory_rate=1200,
        freight_amount=500, freight_payer=PAYER_US,
        freight_payer2=PAYER_FACTORY, freight_split=350,
    )
    update_mixed_trade(
        session, c.id, txn_date=date(2026, 1, 1),
        bapari_id=parties["bapari"].id, factory_id=parties["factory"].id,
        lines=[WoodLine(None, 10, 0, 1000, 1200)],
        freight_amount=500, freight_payer=PAYER_US,
        freight_payer2=PAYER_FACTORY, freight_split=350,
    )
    row = trade_ledger(session)[0][0]
    assert row.freight_payer2 == PAYER_FACTORY
    assert row.freight_split == Decimal("350.00")
    assert row.profit == Decimal("2000.00")  # gross margin


def test_trade_history_carries_expense_payers(session, parties):
    create_trade(
        session, txn_date=date(2026, 1, 1), muds=10, kg=0,
        bapari_id=parties["bapari"].id, bapari_rate=1000,
        factory_id=parties["factory"].id, factory_rate=1200,
        freight_amount=500, freight_payer=PAYER_BAPARI,
        loading_amount=200, loading_payer=PAYER_US,
    )
    row = list_trades(session)[0]
    assert row.freight == Decimal("500.00")
    assert row.freight_payer == PAYER_BAPARI
    assert row.loading == Decimal("200.00")
    assert row.loading_payer == PAYER_US
    assert expense_text(row.freight, row.freight_payer, row.bapari_name, row.factory_name) == "500.00 (Karim)"

    led = trade_ledger(session)[0][0]
    assert led.freight == Decimal("500.00")
    assert led.freight_payer == PAYER_BAPARI
