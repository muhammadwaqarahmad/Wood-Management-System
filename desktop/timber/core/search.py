"""Global search across parties, transactions, and payments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date  # noqa: F401 (type hint)

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from timber.db.models import BapariTxn, FactoryTxn, Party, PartyPhone, Payment


@dataclass
class SearchResult:
    kind: str   # "party" | "purchase" | "sale" | "payment"
    date: str
    name: str
    detail: str
    amount: str


def global_search(
    session: Session, query: str, limit: int = 50,
    kinds: "set[str] | None" = None,
    start: "date | None" = None, end: "date | None" = None,
) -> list[SearchResult]:
    """Search parties, loads and payments.

    ``kinds`` limits which result types are returned ("party", "purchase",
    "sale", "payment"); ``start``/``end`` limit dated results to a range.
    Parties carry no date, so a date range excludes them.
    """
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    results: list[SearchResult] = []
    want = kinds or {"party", "purchase", "sale", "payment"}
    dated = start is not None or end is not None

    phone_party_ids = list(
        session.scalars(
            select(PartyPhone.party_id).where(PartyPhone.phone.ilike(like))
        )
    )
    conds = [
        # Match either language's name (plus the physical fallback).
        Party.name_en.ilike(like),
        Party.name_ur.ilike(like),
        Party._name.ilike(like),
        Party.email.ilike(like),
        Party.address.ilike(like),
    ]
    if phone_party_ids:
        conds.append(Party.id.in_(phone_party_ids))
    parties = list(
        session.scalars(select(Party).where(or_(*conds)).limit(limit))
    )
    party_ids = [p.id for p in parties]
    if "party" in want and not dated:
        for p in parties:
            results.append(
                SearchResult("party", "", p.name,
                             f"{p.party_type} {p.email or ''}".strip(), "")
            )

    for model, kind in ((BapariTxn, "purchase"), (FactoryTxn, "sale")):
        if kind not in want:
            continue
        cond = or_(model.vehicle_no.ilike(like), model.notes.ilike(like))
        if party_ids:
            cond = or_(cond, model.party_id.in_(party_ids))
        date_conds = []
        if start is not None:
            date_conds.append(model.txn_date >= start)
        if end is not None:
            date_conds.append(model.txn_date <= end)
        for t in session.scalars(
            select(model)
            # Pull the party in the same query — each row reads t.party.name,
            # which was lazy-loading one query per result (~50 round trips a
            # search, i.e. seconds on the cloud database).
            .options(joinedload(model.party))
            .where(model.is_void.is_(False), cond, *date_conds)
            .order_by(model.id.desc())
            .limit(limit)
        ):
            results.append(
                SearchResult(
                    kind,
                    str(t.txn_date),
                    t.party.name,
                    f"{t.vehicle_no or ''} {t.weight:g}@{t.rate:g}".strip(),
                    f"{t.net_amount:,.2f}",
                )
            )

    pay_cond = or_(Payment.reference_no.ilike(like), Payment.notes.ilike(like))
    if party_ids:
        pay_cond = or_(pay_cond, Payment.party_id.in_(party_ids))
    pay_dates = []
    if start is not None:
        pay_dates.append(Payment.txn_date >= start)
    if end is not None:
        pay_dates.append(Payment.txn_date <= end)
    for p in (session.scalars(
        select(Payment)
        .options(joinedload(Payment.party))
        .where(Payment.is_void.is_(False), pay_cond, *pay_dates)
        .order_by(Payment.id.desc())
        .limit(limit)
    ) if "payment" in want else []):
        results.append(
            SearchResult(
                "payment", str(p.txn_date), p.party.name,
                f"{p.direction} {p.method}", f"{p.amount:,.2f}",
            )
        )

    return results
