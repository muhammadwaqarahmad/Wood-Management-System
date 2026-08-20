"""Ledgers — Financial Position, Factory Sub-ledger (split), Trade Ledger,
Profit Ledger. Supplier/Factory party ledgers live under /parties.

Same data the desktop Ledgers section shows, from the same services."""
from __future__ import annotations

import os
import tempfile
from datetime import date

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from timber.api.deps import get_current_user, get_session, require_permission
from timber.api.serialize import jsonable
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission
from timber.core.position import financial_position
from timber.core.reports import profit_ledger, profit_totals, trade_ledger
from timber.core.split_ledger import (
    factory_split_statement,
    set_split_rates,
    split_rate_map,
    traded_wood_types,
)
from timber.db.models import Party
from timber.db.models.party import PARTY_FACTORY

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


@router.get("/position")
def position(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Firm-wide financial position: bank/cash, receivables, payables."""
    p = financial_position(session)
    return {
        "bank_total": float(p.bank_total),
        "cash_balance": float(p.cash_balance),
        "cheque_total": float(p.cheque_total),
        "unclaimed_total": float(p.unclaimed_total),
        "grand_total": float(p.grand_total),
        "total_receivable": float(p.total_receivable),
        "total_payable": float(p.total_payable),
        "accounts": [
            {"id": a.id, "name": a.name, "bank_name": a.bank_name,
             "closing": float(a.closing), "is_cash": a.is_cash}
            for a in p.accounts
        ],
        "receivables": [
            {"name": r.name, "contact": r.contact, "kind": r.kind,
             "amount": float(r.amount)}
            for r in p.receivables
        ],
        "payables": [
            {"name": r.name, "contact": r.contact, "kind": r.kind,
             "amount": float(r.amount)}
            for r in p.payables
        ],
    }


@router.get("/position/export")
def position_export(
    fmt: str = "pdf",
    sections: str = "bank",
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download the Financial Position (any of bank / receivable / payable) as a
    PDF/Excel file — the desktop's selectable export."""
    from timber.core.report_data import financial_position_report

    valid = {"bank", "receivable", "payable"}
    sel = {s for s in sections.split(",") if s in valid}
    if not sel:
        raise HTTPException(422, "sections must include bank, receivable and/or payable")
    report = financial_position_report(session, sel)
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
        tmp.name, filename=f"financial_position.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )


@router.get("/factory-split/{factory_id}")
def factory_split(
    factory_id: int,
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The two-sided (weekly / irregular) sub-ledger for one factory."""
    try:
        st = factory_split_statement(session, factory_id, start, end)
    except ValueError:
        raise HTTPException(404, "Factory not found")
    return {
        "factory_name": st.factory_name,
        "split_rate": float(st.split_rate),
        "opening_left": float(st.opening_left),
        "opening_right": float(st.opening_right),
        "closing_left": float(st.closing_left),
        "closing_right": float(st.closing_right),
        "closing_total": float(st.closing_total),
        "total_left": float(st.total_left),
        "total_right": float(st.total_right),
        "paid_left": float(st.paid_left),
        "paid_right": float(st.paid_right),
        "entries": [jsonable(e) for e in st.entries],
    }


@router.get("/trades")
def trade_ledger_ep(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Every wood line as a full trade row (supplier side + factory side)."""
    rows, purchase, sale, profit = trade_ledger(session, start, end)
    return {
        "totals": {"purchase": float(purchase), "sale": float(sale),
                   "profit": float(profit)},
        "rows": [jsonable(r) for r in rows],
    }


@router.get("/trades/export")
def trade_ledger_export(
    fmt: str = "pdf",
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download the Trade Ledger as PDF/Excel — the desktop's export."""
    from timber.core.report_data import trade_ledger_report

    report = trade_ledger_report(session, start, end)
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
        tmp.name, filename=f"trade_ledger.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )


@router.get("/profit")
def profit_ep(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Every combined load with its margin, plus headline totals."""
    rows, total = profit_ledger(session)
    t = profit_totals(rows, total)
    return {
        "totals": {
            "profit": float(t.profit),
            "sale": float(t.sale),
            "purchase": float(t.purchase),
            "trades": t.trades,
            "margin_pct": float(t.margin_pct),
        },
        "rows": [jsonable(r) for r in rows],
    }


@router.get("/profit/export")
def profit_ledger_export(
    fmt: str = "pdf",
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download the Profit Ledger as PDF/Excel — the desktop's export."""
    from timber.core.report_data import profit_ledger_report

    report = profit_ledger_report(session)
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
        tmp.name, filename=f"profit_ledger.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )


class SplitRatesIn(BaseModel):
    # {wood_type_id (as string in JSON): rate}. 0 removes the split for that wood.
    rates: dict[str, float]


@router.post("/factory-split/{factory_id}/rates")
def set_factory_split_rates(
    factory_id: int,
    body: SplitRatesIn,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(require_permission(Permission.MANAGE_SETTINGS)),
) -> dict:
    """Upsert a factory's per-wood split rates (reuses ``set_split_rates``)."""
    try:
        rates = {int(k): Decimal(str(v)) for k, v in body.rates.items()}
        set_split_rates(session, factory_id, rates)
        session.commit()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.get("/split-factories")
def split_factories(
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Factories enrolled in the split sub-ledger (split_rate set), for the
    Factory Sub-Ledger picker — the same list the desktop screen shows."""
    rows = session.scalars(
        select(Party).where(
            Party.party_type == PARTY_FACTORY,
            Party.is_active.is_(True),
            Party.split_rate.is_not(None),
        ).order_by(Party.name)
    ).all()
    return [{"id": p.id, "name": p.name} for p in rows]


@router.get("/factory-split/{factory_id}/wood-rates")
def factory_wood_rates(
    factory_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The wood types this factory has traded, plus its current per-wood split
    rates — what the desktop 'Set split rates' dialog edits (0 = no split)."""
    woods = traded_wood_types(session, factory_id)
    current = split_rate_map(session, factory_id)
    return {
        "woods": [{"id": wid, "name": name} for wid, name in woods],
        "rates": {str(wid): float(rate) for wid, rate in current.items()},
    }


@router.post("/factory-split/{factory_id}/enroll")
def enroll_split_factory(
    factory_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(require_permission(Permission.MANAGE_SETTINGS)),
) -> dict:
    """Add a factory to the split sub-ledger (rate set afterwards) — the
    desktop's 'Add factory'. Enrolment = split_rate is no longer NULL."""
    party = session.get(Party, factory_id)
    if party is None or party.party_type != PARTY_FACTORY:
        raise HTTPException(404, "Factory not found")
    if party.split_rate is None:
        party.split_rate = Decimal("0")
        session.commit()
    return {"ok": True}


@router.delete("/factory-split/{factory_id}")
def remove_split_factory(
    factory_id: int,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(require_permission(Permission.MANAGE_SETTINGS)),
) -> dict:
    """Remove a factory from the split sub-ledger — the desktop's 'Remove from
    split' (sets split_rate back to NULL)."""
    party = session.get(Party, factory_id)
    if party is None or party.party_type != PARTY_FACTORY:
        raise HTTPException(404, "Factory not found")
    party.split_rate = None
    session.commit()
    return {"ok": True}


@router.get("/factory-split/{factory_id}/export")
def factory_split_export(
    factory_id: int,
    fmt: str = "pdf",
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
):
    """Download the two-sided sub-ledger as PDF/Excel — the desktop's detailed
    export (weekly block | divider | regular block)."""
    from timber.core.report_data import ReportData
    from timber.core.weekly_settlement import week_label

    try:
        st = factory_split_statement(session, factory_id, start, end)
    except ValueError:
        raise HTTPException(404, "Factory not found")

    def f(v) -> str:
        return f"{float(v):,.2f}"

    def status(bal) -> str:
        if bal == 0:
            return "Settled"
        if bal > 0:
            return f"{f(bal)} →"
        return f(bal)

    def date_cell(e) -> str:
        if e.booked_date and e.booked_date != e.txn_date:
            return f"{e.txn_date} · Entry: {e.booked_date}"
        return str(e.txn_date)

    headers = [
        "Date", "Week", "Vehicle", "Wood",
        "Weekly — Rate", "Weight", "Kg", "Total", "Freight", "Sale",
        "Payment", "Balance", "Weekly status",
        "Regular — Rate", "Weight", "Kg", "Total", "Payment", "Balance",
    ]
    rows = []
    for e in st.entries:
        wk = week_label(e.txn_date)
        if e.kind == "load":
            rows.append([
                date_cell(e), wk, e.vehicle, e.wood,
                f(e.left_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                f(e.left_total), f(e.freight) if e.freight else "",
                f(e.left_net), "", f(e.left_balance), status(e.left_balance),
                f(e.right_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                f(e.right_amount), "", f(e.right_balance),
            ])
        else:
            rows.append([
                date_cell(e), wk, "", "", "", "", "", "", "", "",
                f(e.left_payment) if e.left_payment else "", f(e.left_balance),
                status(e.left_balance),
                "", "", "", "",
                f(e.right_payment) if e.right_payment else "", f(e.right_balance),
            ])
    report = ReportData(
        title=f"Factory Sub-Ledger — {st.factory_name}",
        headers=headers, rows=rows, divider_after=12,
        summary=[
            ("Weekly balance", f(st.closing_left)),
            ("Regular balance", f(st.closing_right)),
            ("Combined balance", f(st.closing_total)),
        ],
    )
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
        tmp.name, filename=f"factory_sub_ledger.{suffix}", media_type=media,
        background=BackgroundTask(os.unlink, tmp.name),
    )
