"""Transaction services — the only sanctioned way to create/void loads.

Each function validates input, runs the Phase 2 calculations, writes an
audit-log row, and flushes. It does NOT commit — the caller (UI) owns
the transaction so a failed save rolls back cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from timber import i18n
from timber.core.audit import log_action
from timber.core.calculations import (
    apply_txn_totals,
    compute_profit,
    money,
    sale_weight,
    to_decimal,
)
from timber.core.payment_service import reallocate_party
from timber.db.models import BapariTxn, CombinedTxn, FactoryTxn, Party
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def _positive(value: Any, label: str) -> Decimal:
    try:
        dec = to_decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if dec <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return dec


def _non_negative(value: Any, label: str) -> Decimal:
    try:
        dec = to_decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if dec < 0:
        raise ValueError(f"{label} cannot be negative.")
    return dec


def _require_party(session: Session, party_id: int | None, party_type: str) -> Party:
    party = session.get(Party, party_id) if party_id else None
    expected = "bapari" if party_type == PARTY_BAPARI else "factory"
    if party is None or party.party_type != party_type:
        raise ValueError(f"Please select a valid {expected}.")
    return party


def _create_txn(
    session: Session,
    model: type,
    party_type: str,
    entity: str,
    *,
    txn_date: date,
    party_id: int,
    weight: Any,
    rate: Any,
    muds: Any = 0,
    kg: Any = 0,
    wood_type_id: int | None = None,
    location_id: int | None = None,
    vehicle_no: str | None = None,
    freight: Any = 0,
    loading: Any = 0,
    notes: str | None = None,
    created_by: int | None = None,
):
    _require_party(session, party_id, party_type)
    txn = model(
        txn_date=txn_date,
        party_id=party_id,
        wood_type_id=wood_type_id,
        location_id=location_id,
        vehicle_no=(vehicle_no or None),
        muds=_non_negative(muds, "Maunds"),
        kg=_non_negative(kg, "Kg"),
        weight=_positive(weight, "Weight"),
        rate=_non_negative(rate, "Rate"),
        # Freight may be negative on a purchase: a supplier-borne freight is
        # deducted from what we owe them (bill = weight*rate - freight).
        freight=money(freight or 0),
        loading=_non_negative(loading, "Loading"),
        notes=(notes or None),
        created_by=created_by,
    )
    apply_txn_totals(txn)
    session.add(txn)
    session.flush()
    log_action(
        session,
        created_by,
        "create",
        entity,
        txn.id,
        f"weight={txn.weight} rate={txn.rate} bill={txn.bill}",
    )
    # A new load may be settled by an existing advance for this party.
    reallocate_party(session, party_id)
    return txn


def create_bapari_txn(session: Session, **kwargs) -> BapariTxn:
    """Record wood bought from a bapari."""
    return _create_txn(
        session, BapariTxn, PARTY_BAPARI, "bapari_txns", **kwargs
    )


def create_factory_txn(session: Session, **kwargs) -> FactoryTxn:
    """Record wood sold to a factory."""
    return _create_txn(
        session, FactoryTxn, PARTY_FACTORY, "factory_txns", **kwargs
    )


def _payer_amounts(amount, payer1, payer2=None, split=None) -> dict[str, Decimal]:
    """Split one expense into per-payer rupee amounts. With a second payer,
    ``payer1`` bears the rupee amount ``split`` and ``payer2`` the rest;
    otherwise ``payer1`` bears the whole amount."""
    res = {PAYER_US: Decimal("0"), PAYER_BAPARI: Decimal("0"), PAYER_FACTORY: Decimal("0")}
    amt = _non_negative(amount, "Expense")
    if amt <= 0:
        return res
    if payer1 not in res:
        raise ValueError(f"Invalid payer: {payer1!r}")
    if payer2 and payer2 in res and split is not None:
        primary = money(split)
        if primary < 0 or primary > amt:
            raise ValueError("The split amount can't exceed the expense.")
        if 0 < primary < amt:
            res[payer1] += primary
            res[payer2] += amt - primary
            return res
    res[payer1] += amt
    return res


def _split_expenses(expenses) -> dict[str, Decimal]:
    """Total per-load expenses by payer. ``expenses`` is a list of
    (amount, payer1, payer2, payer1_amount) tuples."""
    charges = {PAYER_US: Decimal("0"), PAYER_BAPARI: Decimal("0"), PAYER_FACTORY: Decimal("0")}
    for item in expenses:
        part = _payer_amounts(item[0], item[1],
                              item[2] if len(item) > 2 else None,
                              item[3] if len(item) > 3 else None)
        for k in charges:
            charges[k] += part[k]
    return charges


def _record_own_expenses(
    session: Session, combined_id: int, txn_date: date, items, account_id, created_by
) -> None:
    """Freight / loading / unloading are NOT cash transactions: they are only
    deductions on the supplier (and factory) ledgers — when the factory pays
    the driver they return us less, and we in turn pay the supplier less. So
    nothing is booked to any bank/Cash account here. A bank balance only moves
    on a REAL payment to a supplier / from a factory. (Kept as a no-op so the
    call sites and edit/void flow stay intact.)"""
    return None


def _delete_trade_expenses(session: Session, combined_ids) -> None:
    from timber.db.models import Expense

    ids = list(combined_ids)
    if ids:
        session.execute(delete(Expense).where(Expense.combined_id.in_(ids)))


def _reject_duplicate_trade(
    session: Session, txn_date: date, vehicle_no: str | None, total_weight
) -> None:
    """Block a second identical truck: same DATE + same VEHICLE + same total
    WEIGHT. All three must match — the same vehicle/weight on another day is a
    genuinely different load. Stops two data-entry staff double-entering the
    same slip (works hand-in-hand with the app's live auto-refresh)."""
    vehicle = (vehicle_no or "").strip()
    if not vehicle:
        return  # no vehicle number -> nothing to match on, allow it
    target = money(total_weight)
    # Existing non-void loads for this date+vehicle, summed per truck (group).
    rows = session.execute(
        select(func.coalesce(func.sum(BapariTxn.weight), 0))
        .join(CombinedTxn, CombinedTxn.bapari_txn_id == BapariTxn.id)
        .where(
            BapariTxn.txn_date == txn_date,
            func.lower(func.trim(BapariTxn.vehicle_no)) == vehicle.lower(),
            BapariTxn.is_void.is_(False),
        )
        .group_by(CombinedTxn.group_id)
    ).all()
    for (wsum,) in rows:
        if money(wsum) == target:
            raise ValueError(
                f"{i18n.tr('duplicate_trade')} "
                f"({i18n.tr('vehicle')} {vehicle}, {txn_date}, {target:g})"
            )


def _register_trade_key(
    session: Session, group_id: int, txn_date: date, vehicle_no: str | None,
    total_weight,
) -> None:
    """Atomic backstop for the millisecond race the query check can't cover:
    write a UNIQUE (date, vehicle, weight) fingerprint. If two staff save the
    same truck at the same instant, the second INSERT is rejected by the
    database itself. No vehicle number -> nothing to key on."""
    from sqlalchemy.exc import IntegrityError

    from timber.db.models import TradeKey

    vehicle = (vehicle_no or "").strip()
    if not vehicle:
        return
    session.add(TradeKey(
        group_id=group_id, txn_date=txn_date,
        vehicle_key=vehicle.lower(), total_weight=money(total_weight),
    ))
    try:
        session.flush()
    except IntegrityError as exc:
        raise ValueError(i18n.tr("duplicate_trade")) from exc


def create_trade(
    session: Session,
    *,
    txn_date: date,
    muds: Any,
    kg: Any = 0,
    bapari_id: int,
    bapari_rate: Any,
    factory_id: int,
    factory_rate: Any,
    factory_muds: Any = None,   # defaults to the supplier's muds
    factory_kg: Any = None,     # defaults to the supplier's kg
    wood_type_id: int | None = None,
    location_id: int | None = None,
    vehicle_no: str | None = None,
    loading_amount: Any = 0,
    loading_payer: str = PAYER_US,
    loading_payer2: str | None = None,
    loading_split: Any = 0,
    freight_amount: Any = 0,
    freight_payer: str = PAYER_US,
    freight_payer2: str | None = None,
    freight_split: Any = 0,
    unloading_amount: Any = 0,
    unloading_payer: str = PAYER_US,
    unloading_payer2: str | None = None,
    unloading_split: Any = 0,
    expense_account_id: int | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> tuple[BapariTxn, FactoryTxn, CombinedTxn]:
    """Record one load as a purchase AND its sale, linked for profit.

    Weight is maunds + kg: the buy is billed on maunds only, the sale on
    maunds + kg/40. Loading/freight/unloading each carry a payer (and an
    optional second payer with a percentage split); charges paid by the
    bapari raise the purchase cost, by the factory raise the sale, and by
    us are deducted from the trade's profit.
    """
    muds_d = _positive(muds, "Maunds")
    kg_d = _non_negative(kg, "Kg")
    # Duplicate guard (single-wood load): same date + vehicle + weight.
    _reject_duplicate_trade(session, txn_date, vehicle_no, sale_weight(muds_d, kg_d))
    # The factory (sale) weight defaults to the supplier (buy) weight but can
    # differ (e.g. weighed again at the factory).
    f_muds = _positive(factory_muds, "Maunds") if factory_muds not in (None, "") else muds_d
    f_kg = _non_negative(factory_kg, "Kg") if factory_kg not in (None, "") else kg_d
    charges = _split_expenses(
        [
            (loading_amount, loading_payer, loading_payer2, loading_split),
            (freight_amount, freight_payer, freight_payer2, freight_split),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split),
        ]
    )

    # Freight (and other expenses) the SUPPLIER bears is deducted from what
    # we owe them: supplier net = weight*rate - their share (matches the
    # manual ledger's "bill = total - freight"). OUR share is a cost that
    # reduces profit. Profit itself uses the gross bills (freight is a
    # pass-through), so it stays sale - purchase - our share.
    bapari_txn = create_bapari_txn(
        session,
        txn_date=txn_date,
        party_id=bapari_id,
        muds=muds_d,
        kg=kg_d,
        weight=sale_weight(muds_d, kg_d),   # buy: maunds + kg/40 (muds terms)
        rate=bapari_rate,
        # Supplier always BEARS the freight: whatever the factory or we
        # fronted to the driver is deducted from what we owe the supplier.
        freight=-(charges[PAYER_FACTORY] + charges[PAYER_US]),
        wood_type_id=wood_type_id,
        location_id=location_id,
        vehicle_no=vehicle_no,
        notes=notes,
        created_by=created_by,
    )
    factory_txn = create_factory_txn(
        session,
        txn_date=txn_date,
        party_id=factory_id,
        muds=f_muds,
        kg=f_kg,
        weight=sale_weight(f_muds, f_kg),   # sale: maunds + kg/40
        rate=factory_rate,
        # Factory fronted freight to the driver -> they return us that much
        # less (deducted from what the factory owes us).
        freight=-charges[PAYER_FACTORY],
        wood_type_id=wood_type_id,
        location_id=location_id,
        vehicle_no=vehicle_no,
        notes=notes,
        created_by=created_by,
    )
    combined = CombinedTxn(
        txn_date=txn_date,
        bapari_txn_id=bapari_txn.id,
        factory_txn_id=factory_txn.id,
        loading_amount=_non_negative(loading_amount, "Loading"),
        loading_payer=loading_payer,
        loading_payer2=loading_payer2,
        loading_split=Decimal(str(loading_split)),
        freight_amount=_non_negative(freight_amount, "Freight"),
        freight_payer=freight_payer,
        freight_payer2=freight_payer2,
        freight_split=Decimal(str(freight_split)),
        unloading_amount=_non_negative(unloading_amount, "Unloading"),
        unloading_payer=unloading_payer,
        unloading_payer2=unloading_payer2,
        unloading_split=Decimal(str(unloading_split)),
        own_expense=charges[PAYER_US],
        # Per-trade profit is the gross margin. Our share of expenses is
        # recorded as a real expense (below) so it hits cash + Net Profit.
        profit=money(factory_txn.bill - bapari_txn.bill),
        notes=(notes or None),
        created_by=created_by,
    )
    session.add(combined)
    session.flush()
    combined.group_id = combined.id  # standalone single-wood trade = its own group
    # Atomic dedup fingerprint (race backstop; friendly check ran above).
    _register_trade_key(
        session, combined.id, txn_date, vehicle_no, sale_weight(muds_d, kg_d)
    )
    _record_own_expenses(
        session, combined.id, txn_date,
        [
            (loading_amount, loading_payer, loading_payer2, loading_split, "loading"),
            (freight_amount, freight_payer, freight_payer2, freight_split, "freight"),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split, "unloading"),
        ],
        expense_account_id, created_by,
    )
    session.flush()
    log_action(session, created_by, "create", "combined_txns", combined.id,
               f"profit={combined.profit}")
    return bapari_txn, factory_txn, combined


@dataclass
class WoodLine:
    """One wood line of a mixed-load truck. ``muds``/``kg`` are the supplier
    (buy) weight; the factory (sale) weight defaults to the same but can
    differ."""
    wood_type_id: int | None
    muds: Any
    kg: Any
    bapari_rate: Any
    factory_rate: Any
    factory_muds: Any = None
    factory_kg: Any = None


def create_mixed_trade(
    session: Session,
    *,
    txn_date: date,
    bapari_id: int,
    factory_id: int,
    lines: list[WoodLine],
    location_id: int | None = None,
    vehicle_no: str | None = None,
    loading_amount: Any = 0,
    loading_payer: str = PAYER_US,
    loading_payer2: str | None = None,
    loading_split: Any = 0,
    freight_amount: Any = 0,
    freight_payer: str = PAYER_US,
    freight_payer2: str | None = None,
    freight_split: Any = 0,
    unloading_amount: Any = 0,
    unloading_payer: str = PAYER_US,
    unloading_payer2: str | None = None,
    unloading_split: Any = 0,
    expense_account_id: int | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> list[CombinedTxn]:
    """One truck, one bapari, one factory, several wood lines (each with
    its own muds/kg + bapari/factory rate). Truck expenses are entered
    once and counted once. Each line is stored as its own buy+sell load
    so ledgers and per-wood reporting keep working; all lines share a
    ``group_id`` so the Trades view treats them as one truck.
    """
    _require_party(session, bapari_id, PARTY_BAPARI)
    _require_party(session, factory_id, PARTY_FACTORY)
    clean = [ln for ln in lines if to_decimal(ln.muds or 0) > 0]
    if not clean:
        raise ValueError("Add at least one wood line with maunds.")

    # Single wood line -> a normal trade (keeps the simple path identical).
    if len(clean) == 1:
        ln = clean[0]
        _, _, combined = create_trade(
            session,
            txn_date=txn_date, muds=ln.muds, kg=ln.kg,
            bapari_id=bapari_id, bapari_rate=ln.bapari_rate,
            factory_id=factory_id, factory_rate=ln.factory_rate,
            factory_muds=ln.factory_muds, factory_kg=ln.factory_kg,
            wood_type_id=ln.wood_type_id, location_id=location_id,
            vehicle_no=vehicle_no,
            loading_amount=loading_amount, loading_payer=loading_payer,
            loading_payer2=loading_payer2, loading_split=loading_split,
            freight_amount=freight_amount, freight_payer=freight_payer,
            freight_payer2=freight_payer2, freight_split=freight_split,
            unloading_amount=unloading_amount, unloading_payer=unloading_payer,
            unloading_payer2=unloading_payer2, unloading_split=unloading_split,
            expense_account_id=expense_account_id,
            notes=notes, created_by=created_by,
        )
        return [combined]

    # Duplicate guard (mixed load): compare the WHOLE truck's total weight.
    total_weight = sum(
        (sale_weight(_positive(ln.muds, "Maunds"), _non_negative(ln.kg, "Kg"))
         for ln in clean),
        Decimal("0"),
    )
    _reject_duplicate_trade(session, txn_date, vehicle_no, total_weight)

    charges = _split_expenses(
        [
            (loading_amount, loading_payer, loading_payer2, loading_split),
            (freight_amount, freight_payer, freight_payer2, freight_split),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split),
        ]
    )

    created: list[CombinedTxn] = []
    for i, ln in enumerate(clean):
        first = i == 0
        muds_d = _positive(ln.muds, "Maunds")
        kg_d = _non_negative(ln.kg, "Kg")
        f_muds = _positive(ln.factory_muds, "Maunds") if ln.factory_muds not in (None, "") else muds_d
        f_kg = _non_negative(ln.factory_kg, "Kg") if ln.factory_kg not in (None, "") else kg_d
        bapari_txn = create_bapari_txn(
            session, txn_date=txn_date, party_id=bapari_id,
            muds=muds_d, kg=kg_d, weight=sale_weight(muds_d, kg_d), rate=ln.bapari_rate,
            # Supplier's freight share (whole truck) deducted on the first line.
            freight=(-(charges[PAYER_FACTORY] + charges[PAYER_US]) if first else 0),
            wood_type_id=ln.wood_type_id, location_id=location_id,
            vehicle_no=vehicle_no, notes=notes, created_by=created_by,
        )
        factory_txn = create_factory_txn(
            session, txn_date=txn_date, party_id=factory_id,
            muds=f_muds, kg=f_kg, weight=sale_weight(f_muds, f_kg),
            rate=ln.factory_rate,
            # Factory's freight share (whole truck) added on the first line.
            freight=(-charges[PAYER_FACTORY] if first else 0),
            wood_type_id=ln.wood_type_id, location_id=location_id,
            vehicle_no=vehicle_no, notes=notes, created_by=created_by,
        )
        own = charges[PAYER_US] if first else Decimal("0.00")
        line_profit = money(factory_txn.bill - bapari_txn.bill)  # gross margin
        combined = CombinedTxn(
            txn_date=txn_date,
            bapari_txn_id=bapari_txn.id,
            factory_txn_id=factory_txn.id,
            loading_amount=_non_negative(loading_amount, "Loading") if first else Decimal("0.00"),
            loading_payer=loading_payer if first else PAYER_US,
            loading_payer2=loading_payer2 if first else None,
            loading_split=Decimal(str(loading_split)) if first else Decimal("100"),
            freight_amount=_non_negative(freight_amount, "Freight") if first else Decimal("0.00"),
            freight_payer=freight_payer if first else PAYER_US,
            freight_payer2=freight_payer2 if first else None,
            freight_split=Decimal(str(freight_split)) if first else Decimal("100"),
            unloading_amount=_non_negative(unloading_amount, "Unloading") if first else Decimal("0.00"),
            unloading_payer=unloading_payer if first else PAYER_US,
            unloading_payer2=unloading_payer2 if first else None,
            unloading_split=Decimal(str(unloading_split)) if first else Decimal("100"),
            own_expense=own,
            profit=line_profit,
            notes=(notes or None),
            created_by=created_by,
        )
        session.add(combined)
        created.append(combined)

    session.flush()
    group_id = created[0].id
    for c in created:
        c.group_id = group_id
    # Atomic dedup fingerprint for the whole truck (race backstop).
    _register_trade_key(session, group_id, txn_date, vehicle_no, total_weight)
    _record_own_expenses(
        session, group_id, txn_date,
        [
            (loading_amount, loading_payer, loading_payer2, loading_split, "loading"),
            (freight_amount, freight_payer, freight_payer2, freight_split, "freight"),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split, "unloading"),
        ],
        expense_account_id, created_by,
    )
    session.flush()
    reallocate_party(session, bapari_id)
    reallocate_party(session, factory_id)
    total_profit = money(sum((c.profit for c in created), Decimal("0.00")))
    log_action(
        session, created_by, "create", "combined_txns", group_id,
        f"mixed {len(created)} lines profit={total_profit}",
    )
    return created


def update_trade(
    session: Session,
    combined_id: int,
    *,
    txn_date: date,
    muds: Any,
    kg: Any = 0,
    bapari_id: int,
    bapari_rate: Any,
    factory_id: int,
    factory_rate: Any,
    factory_muds: Any = None,   # defaults to the supplier's muds
    factory_kg: Any = None,     # defaults to the supplier's kg
    wood_type_id: int | None = None,
    location_id: int | None = None,
    vehicle_no: str | None = None,
    loading_amount: Any = 0,
    loading_payer: str = PAYER_US,
    loading_payer2: str | None = None,
    loading_split: Any = 0,
    freight_amount: Any = 0,
    freight_payer: str = PAYER_US,
    freight_payer2: str | None = None,
    freight_split: Any = 0,
    unloading_amount: Any = 0,
    unloading_payer: str = PAYER_US,
    unloading_payer2: str | None = None,
    unloading_split: Any = 0,
    expense_account_id: int | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> CombinedTxn:
    """Edit a saved trade: updates both linked loads + recomputes profit."""
    combined = session.get(CombinedTxn, combined_id)
    if combined is None:
        raise ValueError("Trade not found.")
    _require_party(session, bapari_id, PARTY_BAPARI)
    _require_party(session, factory_id, PARTY_FACTORY)
    # Remember the old parties in case the load was reassigned.
    affected = {combined.bapari_txn.party_id, combined.factory_txn.party_id,
                bapari_id, factory_id}
    muds_d = _positive(muds, "Maunds")
    kg_d = _non_negative(kg, "Kg")
    f_muds = _positive(factory_muds, "Maunds") if factory_muds not in (None, "") else muds_d
    f_kg = _non_negative(factory_kg, "Kg") if factory_kg not in (None, "") else kg_d
    b_rate = _non_negative(bapari_rate, "Rate")
    f_rate = _non_negative(factory_rate, "Rate")
    charges = _split_expenses(
        [
            (loading_amount, loading_payer, loading_payer2, loading_split),
            (freight_amount, freight_payer, freight_payer2, freight_split),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split),
        ]
    )

    bapari = combined.bapari_txn
    bapari.txn_date = txn_date
    bapari.party_id = bapari_id
    bapari.muds = muds_d
    bapari.kg = kg_d
    bapari.weight = sale_weight(muds_d, kg_d)
    bapari.rate = b_rate
    bapari.wood_type_id = wood_type_id
    bapari.location_id = location_id
    bapari.vehicle_no = vehicle_no or None
    bapari.freight = -(charges[PAYER_FACTORY] + charges[PAYER_US])  # supplier bears fronted freight
    apply_txn_totals(bapari)

    factory = combined.factory_txn
    factory.txn_date = txn_date
    factory.party_id = factory_id
    factory.muds = f_muds
    factory.kg = f_kg
    factory.weight = sale_weight(f_muds, f_kg)
    factory.rate = f_rate
    factory.wood_type_id = wood_type_id
    factory.location_id = location_id
    factory.vehicle_no = vehicle_no or None
    factory.freight = -charges[PAYER_FACTORY]  # factory fronted -> they owe us less
    apply_txn_totals(factory)

    combined.txn_date = txn_date
    combined.loading_amount = _non_negative(loading_amount, "Loading")
    combined.loading_payer = loading_payer
    combined.loading_payer2 = loading_payer2
    combined.loading_split = Decimal(str(loading_split))
    combined.freight_amount = _non_negative(freight_amount, "Freight")
    combined.freight_payer = freight_payer
    combined.freight_payer2 = freight_payer2
    combined.freight_split = Decimal(str(freight_split))
    combined.unloading_amount = _non_negative(unloading_amount, "Unloading")
    combined.unloading_payer = unloading_payer
    combined.unloading_payer2 = unloading_payer2
    combined.unloading_split = Decimal(str(unloading_split))
    combined.own_expense = charges[PAYER_US]
    combined.profit = money(factory.bill - bapari.bill)  # gross margin
    if notes is not None:
        combined.notes = notes or None

    # Replace the trade's us-paid expense rows.
    _delete_trade_expenses(session, [combined.id])
    _record_own_expenses(
        session, combined.id, txn_date,
        [
            (loading_amount, loading_payer, loading_payer2, loading_split, "loading"),
            (freight_amount, freight_payer, freight_payer2, freight_split, "freight"),
            (unloading_amount, unloading_payer, unloading_payer2, unloading_split, "unloading"),
        ],
        expense_account_id, created_by,
    )

    session.flush()
    for pid in affected:
        reallocate_party(session, pid)
    log_action(
        session, created_by, "update", "combined_txns", combined.id,
        f"profit={combined.profit}",
    )
    return combined


def void_txn(
    session: Session,
    model: type,
    txn_id: int,
    created_by: int | None = None,
) -> None:
    """Soft-delete (void) a transaction. Never hard-deletes."""
    txn = session.get(model, txn_id)
    if txn is None:
        raise ValueError("Transaction not found.")
    txn.is_void = True
    session.flush()
    log_action(session, created_by, "void", model.__tablename__, txn_id)


def void_trade(
    session: Session,
    combined_id: int,
    created_by: int | None = None,
) -> None:
    """Cancel a whole trade: voids BOTH the purchase and the sale loads
    and removes the profit link, then re-runs FIFO so balances, ledgers,
    dashboard and reports all reflect the removal everywhere.
    """
    combined = session.get(CombinedTxn, combined_id)
    if combined is None:
        raise ValueError("Trade not found.")

    # Void every wood line of the truck (the whole group), not just one.
    members = _group_members(session, combined)
    affected: set[int] = set()
    # Drop the dedup fingerprint so a corrected re-entry is allowed, and
    # remove any us-paid expense rows tied to this trade (both FK to the
    # combined rows we're about to delete).
    from timber.db.models import TradeKey

    group = combined.group_id or combined.id
    session.execute(delete(TradeKey).where(TradeKey.group_id == group))
    _delete_trade_expenses(session, [c.id for c in members])
    for c in members:
        c.bapari_txn.is_void = True
        c.factory_txn.is_void = True
        affected.add(c.bapari_txn.party_id)
        affected.add(c.factory_txn.party_id)
        session.delete(c)
    session.flush()

    # Freed loads -> recompute allocations (their payments become advances).
    for pid in affected:
        reallocate_party(session, pid)
    log_action(session, created_by, "void", "combined_txns", combined_id)


def _group_members(session: Session, combined: CombinedTxn) -> list[CombinedTxn]:
    """All wood lines belonging to the same truck/trade as ``combined``."""
    group = combined.group_id or combined.id
    members = list(
        session.scalars(
            select(CombinedTxn).where(
                (CombinedTxn.group_id == group) | (CombinedTxn.id == group)
            )
        )
    )
    if combined not in members:
        members.append(combined)
    return members


def update_mixed_trade(
    session: Session,
    group_id: int,
    *,
    txn_date: date,
    bapari_id: int,
    factory_id: int,
    lines: list[WoodLine],
    location_id: int | None = None,
    vehicle_no: str | None = None,
    loading_amount: Any = 0,
    loading_payer: str = PAYER_US,
    loading_payer2: str | None = None,
    loading_split: Any = 0,
    freight_amount: Any = 0,
    freight_payer: str = PAYER_US,
    freight_payer2: str | None = None,
    freight_split: Any = 0,
    unloading_amount: Any = 0,
    unloading_payer: str = PAYER_US,
    unloading_payer2: str | None = None,
    unloading_split: Any = 0,
    expense_account_id: int | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> list[CombinedTxn]:
    """Edit a (possibly mixed) trade: void the old group and recreate it.
    Payments are FIFO-reallocated, so balances stay correct."""
    existing = session.get(CombinedTxn, group_id)
    if existing is None:
        raise ValueError("Trade not found.")
    void_trade(session, group_id, created_by=created_by)
    return create_mixed_trade(
        session, txn_date=txn_date, bapari_id=bapari_id, factory_id=factory_id,
        lines=lines, location_id=location_id, vehicle_no=vehicle_no,
        loading_amount=loading_amount, loading_payer=loading_payer,
        loading_payer2=loading_payer2, loading_split=loading_split,
        freight_amount=freight_amount, freight_payer=freight_payer,
        freight_payer2=freight_payer2, freight_split=freight_split,
        unloading_amount=unloading_amount, unloading_payer=unloading_payer,
        unloading_payer2=unloading_payer2, unloading_split=unloading_split,
        expense_account_id=expense_account_id,
        notes=notes, created_by=created_by,
    )


def create_combined_txn(
    session: Session,
    *,
    bapari_txn_id: int,
    factory_txn_id: int,
    txn_date: date | None = None,
    notes: str | None = None,
    created_by: int | None = None,
) -> CombinedTxn:
    """Link a purchase and a sale of the same load and store the margin.

    profit = (factory rate − bapari rate) × weight (of the bapari load).
    """
    bapari = session.get(BapariTxn, bapari_txn_id)
    factory = session.get(FactoryTxn, factory_txn_id)
    if bapari is None or factory is None:
        raise ValueError("Both a bapari load and a factory load are required.")

    profit = compute_profit(factory.rate, bapari.rate, bapari.weight)
    combined = CombinedTxn(
        txn_date=txn_date or factory.txn_date,
        bapari_txn_id=bapari_txn_id,
        factory_txn_id=factory_txn_id,
        profit=profit,
        notes=(notes or None),
        created_by=created_by,
    )
    session.add(combined)
    session.flush()
    log_action(
        session, created_by, "create", "combined_txns", combined.id,
        f"profit={profit}",
    )
    return combined
