"""Suppliers / factories — balances, statements, and create/edit/delete.

Writes reuse ``admin_service`` and follow the desktop's rules: add/edit/
deactivate need MANAGE_SETTINGS; hard delete needs DELETE_RECORD.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload
from starlette.background import BackgroundTask

from timber.api.deps import get_current_user, get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.admin_service import (
    create_party,
    delete_party,
    set_party_active,
    update_party,
)
from timber.core.current_user import CurrentUser
from timber.core.ledger import (
    all_party_balances,
    build_party_ledger,
    detailed_party_statement,
)
from timber.core.permissions import Permission
from timber.core.reports import overdue_factory_ids, party_summaries
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

router = APIRouter(prefix="/parties", tags=["parties"])

_KIND = {"supplier": PARTY_BAPARI, "factory": PARTY_FACTORY}
_SETTINGS = require_permission(Permission.MANAGE_SETTINGS)
_DELETE = require_permission(Permission.DELETE_RECORD)


class PartyIn(BaseModel):
    party_type: str                       # 'supplier' or 'factory'
    name_en: str | None = None
    name_ur: str | None = None
    email: str | None = None
    address: str | None = None
    credit_days: int | None = None
    location_id: int | None = None
    opening_balance: float = 0
    phones: list[str] | None = None
    banks: list[dict] | None = None


class PartyEditIn(BaseModel):
    name_en: str | None = None
    name_ur: str | None = None
    email: str | None = None
    address: str | None = None
    credit_days: int | None = None
    location_id: int | None = None
    opening_balance: float | None = None
    phones: list[str] | None = None
    banks: list[dict] | None = None


@router.get("")
def list_parties(
    kind: str = Query(..., description="'supplier' or 'factory'"),
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Every party of this kind (active AND inactive) with the same columns the
    desktop Master Data table shows: name, phones, location, address, banks,
    balance (internal 'what we owe' value), status, and factory overdue flag."""
    ptype = _KIND.get(kind)
    if ptype is None:
        raise HTTPException(422, "kind must be 'supplier' or 'factory'")
    balances = all_party_balances(session)
    overdue = overdue_factory_ids(session) if ptype == PARTY_FACTORY else set()
    parties = session.scalars(
        select(Party)
        .where(Party.party_type == ptype)
        .options(
            selectinload(Party.phones),
            selectinload(Party.banks),
            joinedload(Party.location),
        )
        .order_by(Party.name)
    ).unique().all()
    out = []
    for p in parties:
        banks = []
        for b in p.banks:
            head = " — ".join(x for x in (b.account_title, b.bank_name) if x)
            if head:
                banks.append(head)
        out.append({
            "id": p.id,
            "name": p.name,
            "party_type": p.party_type,
            "phones": [ph.phone for ph in p.phones],
            "location": p.location.name if p.location else None,
            "address": p.address or None,
            "banks": banks,
            "balance": float(balances.get(p.id, 0)),
            "is_active": bool(p.is_active),
            "overdue": p.id in overdue,
        })
    return out


@router.get("/{party_id}")
def party_detail(
    party_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Full detail for the edit dialog — bilingual names, contact, phones, and
    bank accounts as objects."""
    p = session.scalars(
        select(Party)
        .where(Party.id == party_id)
        .options(selectinload(Party.phones), selectinload(Party.banks),
                 joinedload(Party.location))
    ).unique().one_or_none()
    if p is None:
        raise HTTPException(404, "Party not found")
    return {
        "id": p.id, "name": p.name, "name_en": p.name_en, "name_ur": p.name_ur,
        "party_type": p.party_type, "email": p.email, "address": p.address,
        "credit_days": p.credit_days, "location_id": p.location_id,
        "opening_balance": float(p.opening_balance), "is_active": bool(p.is_active),
        # Factories enrolled in the weekly/irregular split sub-ledger show the
        # "Which side" selector on the payment form (same flag as the desktop).
        "split_enrolled": p.split_rate is not None,
        "phones": [ph.phone for ph in p.phones],
        "banks": [
            {"id": b.id, "account_title": b.account_title or "", "bank_name": b.bank_name or "",
             "iban": b.iban or "", "account_number": b.account_number or ""}
            for b in p.banks
        ],
    }


@router.get("/{party_id}/ledger")
def party_ledger(
    party_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Full running statement for one party (every load and payment)."""
    try:
        pl = build_party_ledger(session, party_id)
    except ValueError:
        raise HTTPException(404, "Party not found")
    return {
        "party": {"id": pl.party.id, "name": pl.party.name,
                  "type": pl.party.party_type},
        "opening": float(pl.opening_balance),
        "closing": float(pl.closing_balance),
        "entries": [
            {
                "date": e.entry_date.isoformat(),
                "kind": e.kind,
                "ref_id": e.ref_id,
                "description": e.description,
                "debit": float(e.debit),
                "credit": float(e.credit),
                "balance": float(e.balance),
            }
            for e in pl.entries
        ],
    }


@router.get("/{party_id}/statement")
def party_statement(
    party_id: int,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The rich per-party statement the desktop Supplier/Factory ledger shows —
    each load with vehicle, wood, weight, rate, freight, bill and running
    balance; each payment with its bank route — plus period totals."""
    try:
        st = detailed_party_statement(session, party_id, start, end)
    except ValueError:
        raise HTTPException(404, "Party not found")
    return {
        "party": {"id": st.party.id, "name": st.party.name, "type": st.party_type},
        "opening": float(st.opening),
        "closing": float(st.closing),
        "total_loads": float(st.total_loads),
        "total_paid": float(st.total_paid),
        "entries": [
            {
                "entry_date": e.entry_date.isoformat(),
                "kind": e.kind,                      # "load" | "payment"
                "counterparty": e.counterparty,
                "vehicle": e.vehicle,
                "wood": e.wood,
                "weight_text": e.weight_text,
                "rate": float(e.rate),
                "freight": float(e.freight),
                "total": float(e.total),
                "debit": float(e.debit),
                "credit": float(e.credit),
                "expenses": e.expenses,
                "payment_detail": e.payment_detail,
                "balance": float(e.balance),
            }
            for e in st.entries
        ],
    }


@router.get("/{party_id}/statement/export")
def party_statement_export(
    party_id: int,
    fmt: str = "pdf",
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download one party's detailed statement as PDF/Excel — the desktop's
    Supplier/Factory ledger export."""
    from timber.core.report_data import detailed_statement_report

    try:
        report = detailed_statement_report(session, party_id, start, end)
    except ValueError:
        raise HTTPException(404, "Party not found")
    # reportlab / openpyxl are heavy — import only when someone actually exports.
    from timber.core import excel_export, pdf_export

    is_xlsx = fmt == "xlsx"
    writer = excel_export if is_xlsx else pdf_export
    suffix = "xlsx" if is_xlsx else "pdf"
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if is_xlsx else "application/pdf")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + suffix)
    tmp.close()
    try:
        writer.write(report, tmp.name)
    except Exception as exc:  # noqa: BLE001
        os.unlink(tmp.name)
        raise HTTPException(500, f"Export failed: {exc}")
    return FileResponse(
        tmp.name, filename=f"statement.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )


# ------------------------------------------------------------------ writes ---

@router.post("")
def create(body: PartyIn, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_SETTINGS)) -> dict:
    ptype = _KIND.get(body.party_type)
    if ptype is None:
        raise HTTPException(422, "party_type must be 'supplier' or 'factory'")
    try:
        party = create_party(
            session, party_type=ptype, name_en=body.name_en, name_ur=body.name_ur,
            email=body.email, address=body.address, credit_days=body.credit_days,
            location_id=body.location_id, opening_balance=body.opening_balance,
            phones=body.phones, banks=body.banks, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": party.id}


@router.put("/{party_id}")
def update(party_id: int, body: PartyEditIn,
           session: Session = Depends(get_session),
           user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        update_party(
            session, party_id, name_en=body.name_en, name_ur=body.name_ur,
            email=body.email, address=body.address, credit_days=body.credit_days,
            location_id=body.location_id, opening_balance=body.opening_balance,
            phones=body.phones, banks=body.banks,
            update_credit_days=body.credit_days is not None, created_by=user.id,
        )
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.post("/{party_id}/active")
def set_active(party_id: int, active: bool = Query(...),
               session: Session = Depends(get_session),
               user: CurrentUser = Depends(_SETTINGS)) -> dict:
    try:
        set_party_active(session, party_id, active, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/{party_id}")
def delete(party_id: int, session: Session = Depends(get_session),
           user: CurrentUser = Depends(_DELETE)) -> dict:
    try:
        delete_party(session, party_id, created_by=user.id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
