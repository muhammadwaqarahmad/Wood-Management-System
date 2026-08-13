"""Read-only lookup helpers for the entry screens: things like the
last rate used for a party, recent vehicle numbers (autocomplete), and
selectable transaction lists for combined entry.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.db.models import BapariTxn, FactoryTxn
from timber.db.models.party import PARTY_BAPARI


def _txn_model(party_type: str):
    return BapariTxn if party_type == PARTY_BAPARI else FactoryTxn


def last_rate_for_party(
    session: Session, party_id: int, party_type: str
) -> Decimal | None:
    """The rate from this party's most recent (non-void) load, or None."""
    model = _txn_model(party_type)
    return session.scalar(
        select(model.rate)
        .where(model.party_id == party_id, model.is_void.is_(False))
        .order_by(model.id.desc())
        .limit(1)
    )


def linked_factory_ids(session: Session, bapari_id: int) -> list[int]:
    """Factory ids linked to this bapari (empty if none configured)."""
    from timber.db.models import Party

    bapari = session.get(Party, bapari_id)
    if bapari is None:
        return []
    return [f.id for f in bapari.linked_factories]


def recent_vehicles(session: Session, limit: int = 100) -> list[str]:
    """Distinct vehicle numbers seen across both transaction tables."""
    seen: list[str] = []
    for model in (BapariTxn, FactoryTxn):
        rows = session.scalars(
            select(model.vehicle_no)
            .where(model.vehicle_no.is_not(None))
            .order_by(model.id.desc())
            .limit(limit)
        ).all()
        for v in rows:
            if v and v not in seen:
                seen.append(v)
    return seen


def last_txn(session: Session, party_type: str):
    """Most recent non-void transaction of the given side (or None)."""
    model = _txn_model(party_type)
    return session.scalar(
        select(model).where(model.is_void.is_(False)).order_by(model.id.desc()).limit(1)
    )


def txn_options(session: Session, party_type: str, limit: int = 200) -> list[dict]:
    """Selectable loads for combined entry, newest first.

    Returns lightweight dicts (resolved while the session is open) so
    callers don't hit detached-instance errors.
    """
    model = _txn_model(party_type)
    txns = session.scalars(
        select(model).where(model.is_void.is_(False)).order_by(model.id.desc()).limit(limit)
    ).all()
    options = []
    for t in txns:
        options.append(
            {
                "id": t.id,
                "weight": t.weight,
                "rate": t.rate,
                "label": (
                    f"#{t.id}  {t.txn_date}  {t.party.name}  "
                    f"{t.weight:g}@{t.rate:g}  (bill {t.bill:,.0f})"
                ),
            }
        )
    return options
