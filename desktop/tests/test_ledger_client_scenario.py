"""Client ledger scenario — reproduces the supplier/factory ledger sheets
the client shared, and verifies the balance sign convention, the payment
"bank route" detail, and newest-first ordering.

Universal rule (the client's): money we must GIVE shows NEGATIVE; money we
will RECEIVE shows POSITIVE. So:
  * supplier balance NEGATIVE  -> we owe the supplier (we must give)
  * supplier balance POSITIVE  -> the supplier owes us (we will receive)
  * factory  balance POSITIVE  -> the factory owes us (we will receive)
  * factory  balance NEGATIVE  -> we owe the factory (we must give)

For a supplier this is -(internal balance); for a factory it is +(internal).
"""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import admin_service
from timber.core.ledger import detailed_party_statement
from timber.core.payment_service import create_payment
from timber.core.transaction_service import create_trade
from timber.db.models import BankAccount
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import METHOD_ONLINE


@pytest.fixture
def world(session):
    hbl = BankAccount(name="HBL", opening_balance=Decimal("0"))
    session.add(hbl)
    supplier = admin_service.create_party(
        session, name="Malik Yaseen", party_type=PARTY_BAPARI
    )
    factory = admin_service.create_party(
        session, name="MORO", party_type=PARTY_FACTORY
    )
    session.flush()
    return dict(hbl=hbl, supplier=supplier, factory=factory)


def test_supplier_ledger_matches_sheet(session, world):
    sup = world["supplier"].id
    fac = world["factory"].id

    # Malik Yaseen row 1: 404 maunds @ 470 = 189,880 total; freight 104,235
    # paid by us → supplier's net bill = 85,645 (we keep the freight).
    create_trade(
        session, txn_date=date(2026, 6, 7),
        muds=404, kg=0, bapari_id=sup, bapari_rate=470,
        factory_id=fac, factory_rate=490, vehicle_no="6911",
        freight_amount=104235, freight_payer="us",
    )

    st = detailed_party_statement(session, sup)
    load = st.entries[0]
    assert load.total == Decimal("189880.00")          # weight × rate
    assert load.freight == Decimal("-104235.00")        # deduction
    assert load.debit == Decimal("85645.00")            # net bill
    # Only a purchase so far → we owe the supplier 85,645 (negative).
    assert st.closing == Decimal("-85645.00")

    # Pay the supplier 250,000 online via HBL.
    create_payment(
        session, txn_date=date(2026, 6, 9), party_id=sup, amount=250000,
        method=METHOD_ONLINE, bank_account_id=world["hbl"].id,
    )
    st = detailed_party_statement(session, sup)
    # -85,645 + 250,000 = 164,355 → now the SUPPLIER owes us (positive).
    assert st.closing == Decimal("164355.00")

    # Oldest first: the load is entry 0, the payment is entry 1 (newest last).
    load, pay = st.entries[0], st.entries[1]
    assert pay.kind == "payment"
    assert pay.credit == Decimal("250000.00")
    assert pay.payment_detail == "HBL → Malik Yaseen"   # money left HBL → supplier
    assert load.kind == "load"


def test_cash_payment_shows_cash(session, world):
    sup = world["supplier"].id
    fac = world["factory"].id
    create_trade(
        session, txn_date=date(2026, 6, 8),
        muds=100, kg=0, bapari_id=sup, bapari_rate=400,
        factory_id=fac, factory_rate=420,
    )
    create_payment(session, txn_date=date(2026, 6, 9), party_id=sup, amount=5000)
    st = detailed_party_statement(session, sup)
    # Payment is the newest entry -> last row.
    assert st.entries[-1].payment_detail.startswith("Cash")


def test_factory_ledger_sign(session, world):
    sup = world["supplier"].id
    fac = world["factory"].id
    # We sell to the factory: 305 maunds @ 750 = 228,750.
    create_trade(
        session, txn_date=date(2026, 6, 11),
        muds=305, kg=0, bapari_id=sup, bapari_rate=545,
        factory_id=fac, factory_rate=750, vehicle_no="454",
    )
    st = detailed_party_statement(session, fac)
    # Universal rule: factory owes us (we will receive) → POSITIVE.
    assert st.closing == Decimal("228750.00")

    # Factory pays us 228,750 via HBL → settled (0).
    create_payment(
        session, txn_date=date(2026, 6, 17), party_id=fac, amount=228750,
        method=METHOD_ONLINE, bank_account_id=world["hbl"].id,
    )
    st = detailed_party_statement(session, fac)
    assert st.closing == Decimal("0.00")
    # Money came IN from the factory → into HBL (newest entry -> last row).
    assert st.entries[-1].payment_detail == "MORO → HBL"


def test_same_day_payment_then_truck_order_and_balance(session, world):
    """Pay the supplier, then they send a truck the same day. Chronological
    order (oldest first): the payment is first, the truck is last and carries
    the final balance. The running balance follows the real entry order."""
    from datetime import datetime

    fac = world["factory"].id
    # We owe this supplier 146,480 to start.
    sup = admin_service.create_party(
        session, name="Waqar", party_type=PARTY_BAPARI,
        opening_balance=Decimal("146480"),
    )
    session.flush()

    # 1) Pay the supplier 500,000 (entered first).
    p = create_payment(
        session, txn_date=date(2026, 7, 1), party_id=sup.id, amount=500000,
        method=METHOD_ONLINE, bank_account_id=world["hbl"].id,
    )
    p.created_at = datetime(2026, 7, 1, 10, 0, 0)
    session.flush()
    # 2) Then the truck arrives: 254 mds @ 725 = 184,150, freight 48,175 → net 135,975.
    b, f, c = create_trade(
        session, txn_date=date(2026, 7, 1), muds=254, kg=0,
        bapari_id=sup.id, bapari_rate=725, factory_id=fac, factory_rate=725,
        vehicle_no="5918", freight_amount=48175, freight_payer="us",
    )
    b.created_at = datetime(2026, 7, 1, 11, 0, 0)
    session.flush()

    st = detailed_party_statement(session, sup.id)
    # Oldest first: payment on top (intermediate 353,520), then the truck
    # (final 217,545) at the bottom.
    assert st.entries[0].kind == "payment"
    assert st.entries[0].balance == Decimal("353520.00")
    assert st.entries[1].kind == "load"
    assert st.entries[1].balance == Decimal("217545.00")
    assert st.closing == Decimal("217545.00")


def test_opening_balance_then_payment(session, world):
    """The client's bug: a supplier opening balance, then a payment must
    REDUCE what we owe (move the balance up), not push it further down."""
    sup = admin_service.create_party(
        session, name="With Opening", party_type=PARTY_BAPARI,
        opening_balance=Decimal("100000"),   # we owe them 100,000 to start
    )
    session.flush()
    st = detailed_party_statement(session, sup.id)
    assert st.opening == Decimal("-100000.00")   # shown as a debt (negative)

    create_payment(session, txn_date=date(2026, 6, 10), party_id=sup.id, amount=30000)
    st = detailed_party_statement(session, sup.id)
    # 100,000 owed − 30,000 paid = 70,000 still owed → -70,000.
    assert st.closing == Decimal("-70000.00")
