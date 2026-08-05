"""Report builders — turn queries into a format-neutral ``ReportData``
that the PDF and Excel exporters both consume. Labels use the current
language; values are pre-formatted strings, so the result is safe to
use after the DB session closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from datetime import date

from timber import i18n
from timber.core.dashboard import dashboard_cards
from timber.core.ledger import build_party_ledger
from timber.core.reports import (
    STATUS_DUE_SOON,
    STATUS_OVERDUE,
    STATUS_SETTLED,
    daily_book,
    factory_receivables,
    list_trades,
    profit_ledger,
    profit_totals,
)


def _fmt(value) -> str:
    return f"{Decimal(value):,.2f}"


@dataclass
class ReportSection:
    """A sub-table inside a report, with its own heading. ``bold_rows``
    are indexes of result rows (rendered bold on a tinted background)."""

    title: str
    headers: list[str]
    rows: list[list[str]]
    bold_rows: list[int] = field(default_factory=list)


@dataclass
class ReportData:
    title: str
    headers: list[str]
    rows: list[list[str]]
    summary: list[tuple[str, str]] = field(default_factory=list)
    # Rich layout (all optional): a big headline number, stat tiles, and
    # multiple titled sections. When ``sections`` is set the exporters render
    # them instead of the flat headers/rows table.
    hero: tuple[str, str] | None = None
    tiles: list[tuple[str, str]] = field(default_factory=list)
    sections: list[ReportSection] = field(default_factory=list)
    # Draw a bold vertical line AFTER this column index (e.g. the split
    # sub-ledger's divider between its left and right sides). None = no line.
    divider_after: int | None = None


def position_report(session: Session, section: str = "bank") -> ReportData:
    """One section of the Financial Position page (bank / receivable / payable)
    as its own exportable table, so each tab exports only its own data."""
    from timber.core.position import financial_position

    pos = financial_position(session)
    kind_key = {"supplier": "bapari", "factory": "factory", "loan": "loan"}
    title = i18n.tr("financial_position")

    if section == "bank":
        headers = [i18n.tr("name"), i18n.tr("bank_name"), i18n.tr("balance")]
        rows = [[a.name, a.bank_name or "", _fmt(a.closing)] for a in pos.accounts]
        summary = [
            (i18n.tr("bank_total"), _fmt(pos.bank_total)),
            (i18n.tr("cash_position"), _fmt(pos.cash_balance)),
            (i18n.tr("cheque_balance"), _fmt(pos.cheque_total)),
            (i18n.tr("unclaimed_total"), _fmt(pos.unclaimed_total)),
            (i18n.tr("grand_total"), _fmt(pos.grand_total)),
        ]
        return ReportData(f"{title} — {i18n.tr('bank_total')}", headers, rows, summary)

    headers = [i18n.tr("name"), i18n.tr("contact"), i18n.tr("type"), i18n.tr("amount")]
    if section == "receivable":
        src, label, total = pos.receivables, i18n.tr("to_receive"), pos.total_receivable
    else:
        src, label, total = pos.payables, i18n.tr("to_give"), pos.total_payable
    rows = [
        [r.name, r.contact, i18n.tr(kind_key.get(r.kind, r.kind)), _fmt(r.amount)]
        for r in src
    ]
    return ReportData(f"{title} — {label}", headers, rows, [(label, _fmt(total))])


def party_statement(session: Session, party_id: int) -> ReportData:
    ledger = build_party_ledger(session, party_id)
    headers = [
        i18n.tr("date"),
        i18n.tr("description"),
        i18n.tr("debit"),
        i18n.tr("credit"),
        i18n.tr("balance"),
    ]
    rows = [
        [
            str(e.entry_date),
            e.description,
            _fmt(e.debit) if e.debit else "",
            _fmt(e.credit) if e.credit else "",
            _fmt(e.balance),
        ]
        for e in ledger.entries
    ]
    title = f"{i18n.tr('party_ledger')} — {ledger.party.name}"
    summary = [(i18n.tr("balance"), _fmt(ledger.closing_balance))]
    return ReportData(title, headers, rows, summary)


def detailed_statement_report(
    session: Session, party_id: int,
    start: date | None = None, end: date | None = None,
) -> ReportData:
    from timber.core.ledger import detailed_party_statement
    from timber.db.models.party import PARTY_BAPARI

    st = detailed_party_statement(session, party_id, start, end)
    counter_label = "factory" if st.party_type == PARTY_BAPARI else "bapari"
    headers = [
        i18n.tr("date"), i18n.tr("description"), i18n.tr(counter_label),
        i18n.tr("vehicle_no"), i18n.tr("wood_type"), i18n.tr("weight"),
        i18n.tr("rate"), i18n.tr("freight"), i18n.tr("total"),
        i18n.tr("bill_amount"), i18n.tr("payment"),
        i18n.tr("expenses"), i18n.tr("balance"),
    ]
    # Opening balance is the oldest line — show it at the top.
    rows = [[i18n.tr("opening")] + [""] * 11 + [_fmt(st.opening)]]
    for e in st.entries:  # oldest first, newest at the bottom
        kind = i18n.tr("load") if e.kind == "load" else i18n.tr("payment")
        detail = e.expenses if e.kind == "load" else e.payment_detail
        rows.append([
            str(e.entry_date), kind, e.counterparty, e.vehicle, e.wood,
            e.weight_text,
            _fmt(e.rate) if e.kind == "load" else "",
            _fmt(-e.freight) if e.kind == "load" and e.freight else "",
            _fmt(e.total) if e.kind == "load" else "",
            _fmt(e.debit) if e.debit else "",
            _fmt(e.credit) if e.credit else "",
            detail, _fmt(e.balance),
        ])
    label = "bapari" if st.party_type == PARTY_BAPARI else "factory"
    title = f"{i18n.tr(label)} {i18n.tr('statement')} — {st.party.name}"
    if start or end:
        title += f" ({start or '…'} → {end or '…'})"
    summary = [
        (i18n.tr("total_loads"), _fmt(st.total_loads)),
        (i18n.tr("total_paid"), _fmt(st.total_paid)),
        (i18n.tr("balance"), _fmt(st.closing)),
    ]
    return ReportData(title, headers, rows, summary)


def trade_ledger_report(
    session: Session, start: date | None = None, end: date | None = None,
) -> ReportData:
    from timber.core.reports import trade_ledger

    from timber.core.labels import expenses_summary

    rows_src, purchase, sale, profit = trade_ledger(session, start, end)
    headers = [
        i18n.tr("date"), i18n.tr("vehicle_no"), i18n.tr("wood_type"),
        i18n.tr("weight"), i18n.tr("supplier"), i18n.tr("buy_rate"),
        i18n.tr("purchase_bill"), i18n.tr("status"), i18n.tr("factory"),
        i18n.tr("sell_rate"), i18n.tr("sale_bill"), i18n.tr("status"),
        i18n.tr("profit"), i18n.tr("freight"),
    ]
    rows = [
        [
            str(r.txn_date), r.vehicle, r.wood, r.weight_text,
            r.supplier_name, _fmt(r.buy_rate), _fmt(r.purchase_bill),
            i18n.tr(r.supplier_status), r.factory_name, _fmt(r.sell_rate),
            _fmt(r.sale_bill), i18n.tr(r.factory_status), _fmt(r.profit),
            expenses_summary(r),
        ]
        for r in rows_src
    ]
    title = i18n.tr("trade_ledger")
    if start or end:
        title += f" ({start or '…'} → {end or '…'})"
    summary = [
        (i18n.tr("total_purchases"), _fmt(purchase)),
        (i18n.tr("total_sales"), _fmt(sale)),
        (i18n.tr("total_profit"), _fmt(profit)),
    ]
    return ReportData(title, headers, rows, summary)


def profit_loss(session: Session) -> ReportData:
    c = dashboard_cards(session)
    headers = [i18n.tr("description"), i18n.tr("amount")]
    rows = [
        [i18n.tr("total_receivable"), _fmt(c.receivable)],
        [i18n.tr("total_payable"), _fmt(c.payable)],
        [i18n.tr("cash_in"), _fmt(c.cash_in)],
        [i18n.tr("cash_out"), _fmt(c.cash_out)],
        [i18n.tr("total_profit"), _fmt(c.total_profit)],
        [i18n.tr("net_position"), _fmt(c.net)],
    ]
    summary = [(i18n.tr("total_profit"), _fmt(c.total_profit))]
    return ReportData(i18n.tr("profit_loss"), headers, rows, summary)


def trades_report(
    session: Session, start: date | None = None, end: date | None = None
) -> ReportData:
    trades = list_trades(session, start, end)
    from timber.core.labels import expenses_summary

    headers = [
        i18n.tr("date"), i18n.tr("vehicle_no"), i18n.tr("wood_type"),
        i18n.tr("weight"), i18n.tr("bapari"), i18n.tr("buy_rate"),
        i18n.tr("factory"), i18n.tr("sell_rate"),
        i18n.tr("purchase_bill"), i18n.tr("sale_bill"),
        i18n.tr("freight"), i18n.tr("profit"),
    ]
    rows = [
        [
            str(t.txn_date), t.vehicle, t.wood, t.weight_text,
            t.bapari_name,
            "—" if t.is_mixed else _fmt(t.bapari_rate),
            t.factory_name,
            "—" if t.is_mixed else _fmt(t.factory_rate),
            _fmt(t.purchase_bill), _fmt(t.sale_bill),
            expenses_summary(t), _fmt(t.profit),
        ]
        for t in trades
    ]
    total = sum((t.profit for t in trades), Decimal("0"))
    title = i18n.tr("trades")
    if start or end:
        title += f" ({start or '…'} → {end or '…'})"
    summary = [(i18n.tr("total_profit"), _fmt(total))]
    return ReportData(title, headers, rows, summary)


def profit_ledger_report(session: Session) -> ReportData:
    rows_src, total = profit_ledger(session)
    totals = profit_totals(rows_src, total)
    headers = [
        i18n.tr("date"), i18n.tr("bapari"), i18n.tr("factory"),
        i18n.tr("weight"), i18n.tr("buy_rate"), i18n.tr("sell_rate"),
        i18n.tr("purchase"), i18n.tr("sale"), i18n.tr("profit"),
        i18n.tr("margin_pct"),
    ]
    rows = [
        [
            str(r.txn_date), r.bapari_name, r.factory_name, f"{r.weight:g}",
            _fmt(r.bapari_rate), _fmt(r.factory_rate), _fmt(r.purchase),
            _fmt(r.sale), _fmt(r.profit), f"{r.margin_pct:g}%",
        ]
        for r in rows_src
    ]
    summary = [
        (i18n.tr("total_sales"), _fmt(totals.sale)),
        (i18n.tr("total_purchases"), _fmt(totals.purchase)),
        (i18n.tr("total_profit"), _fmt(totals.profit)),
        (i18n.tr("avg_margin"), f"{totals.margin_pct:g}%"),
    ]
    return ReportData(i18n.tr("profit_ledger"), headers, rows, summary)


_RECV_STATUS_LABEL = {
    STATUS_SETTLED: "settled",
    STATUS_OVERDUE: "overdue",
    STATUS_DUE_SOON: "due_soon",
    "ok": "on_track",
}


def factory_receivables_report(session: Session) -> ReportData:
    rows_src = factory_receivables(session)
    headers = [
        i18n.tr("factory"), i18n.tr("billed"), i18n.tr("received"),
        i18n.tr("balance"), i18n.tr("oldest_unpaid"), i18n.tr("credit_days"),
        i18n.tr("status"),
    ]
    rows = [
        [
            r.name, _fmt(r.billed), _fmt(r.received), _fmt(r.balance),
            str(r.oldest_days) if r.balance > 0 else "—",
            str(r.credit_days) if r.credit_days is not None else "—",
            i18n.tr(_RECV_STATUS_LABEL.get(r.status, "on_track")),
        ]
        for r in rows_src
    ]
    owing = [r for r in rows_src if r.balance > 0]
    total_recv = sum((r.balance for r in owing), Decimal("0"))
    overdue = sum((r.balance for r in owing if r.status == STATUS_OVERDUE), Decimal("0"))
    summary = [
        (i18n.tr("total_receivable"), _fmt(total_recv)),
        (i18n.tr("overdue_amount"), _fmt(overdue)),
    ]
    return ReportData(i18n.tr("factory_ledger"), headers, rows, summary)


def bank_daily_report(
    session: Session, account_id: int,
    start: date | None = None, end: date | None = None,
) -> ReportData:
    from timber.core.bank_ledger import bank_daily_book

    book = bank_daily_book(session, account_id, start, end)
    headers = [
        i18n.tr("date"), i18n.tr("opening"), i18n.tr("money_in"),
        i18n.tr("money_out"), i18n.tr("closing"),
    ]
    rows = [
        [str(r.day), _fmt(r.opening), _fmt(r.money_in), _fmt(r.money_out),
         _fmt(r.closing)]
        for r in book.rows
    ]
    title = f"{i18n.tr('bank_book')} — {book.account_name}"
    if start or end:
        title += f" ({start or '…'} → {end or '…'})"
    closing = book.rows[-1].closing if book.rows else Decimal("0")
    summary = [(i18n.tr("closing"), _fmt(closing))]
    return ReportData(title, headers, rows, summary)


def bank_statement_report(
    session: Session, account_id: int,
    start: date | None = None, end: date | None = None,
) -> ReportData:
    from timber.core.bank_ledger import bank_statement

    st = bank_statement(session, account_id, start, end)
    headers = [
        i18n.tr("date"), i18n.tr("from"), i18n.tr("to"), i18n.tr("money_in"),
        i18n.tr("money_out"), i18n.tr("balance"),
    ]
    rows = [[i18n.tr("opening"), "", "", "", "", _fmt(st.opening)]]
    rows += [
        [str(e.entry_date), e.source, e.destination,
         _fmt(e.money_in) if e.money_in else "",
         _fmt(e.money_out) if e.money_out else "",
         _fmt(e.balance)]
        for e in st.entries
    ]
    title = f"{i18n.tr('statement')} — {st.account_name}"
    if start or end:
        title += f" ({start or '…'} → {end or '…'})"
    summary = [
        (i18n.tr("money_in"), _fmt(st.total_in)),
        (i18n.tr("money_out"), _fmt(st.total_out)),
        (i18n.tr("closing"), _fmt(st.closing)),
    ]
    return ReportData(title, headers, rows, summary)


def daily_book_report(session: Session, day: date) -> ReportData:
    entries = daily_book(session, day)
    headers = [
        i18n.tr("kind"),
        i18n.tr("party"),
        i18n.tr("detail"),
        i18n.tr("amount"),
    ]
    rows = [[e.kind, e.party_name, e.detail, _fmt(e.amount)] for e in entries]
    return ReportData(f"{i18n.tr('daily_book')} — {day}", headers, rows)


# --------------------------------------------------------------------------
# Dashboard / Reports exports — built from the SAME services the screens use,
# so a PDF/Excel always matches exactly what is on screen.
# --------------------------------------------------------------------------
_SUMMARY_LABELS = {
    "banks": "banks", "cash": "cash", "receivable": "to_receive",
    "loans_given": "loans_given", "payable": "to_give", "loans": "loans_taken",
    "net_worth": "net_position",
}
_CF_LABELS = {
    "banks": "banks", "cash": "cash", "available": "total_available",
    "cheques_in": "cheques_in", "unclaimed": "unclaimed",
    "receivable": "to_receive", "loans_given": "loans_given",
    "payable": "to_give", "loans": "loans_taken", "profit": "total_profit",
    "exp_business": "business_expenses", "exp_house": "house_expenses",
    "profit_after": "profit_after_expenses",
}
_CF_SECTIONS = {
    "position": "cf_position", "balances": "cf_balances",
    "cheques": "cf_cheques", "unclaimed": "cf_unclaimed", "flows": "cf_flows",
}


def _period_suffix(start, end) -> str:
    return f" ({start or '…'} → {end or '…'})" if (start or end) else ""


def dashboard_report(session: Session, start=None, end=None) -> ReportData:
    """The Dashboard as an exportable report: KPI tiles + Summary + banks."""
    from timber.core.dashboard_service import dashboard_summary

    d = dashboard_summary(session, start, end)
    c = d["cards"]
    tiles = [
        (i18n.tr("sale_bill"), _fmt(c["sales"])),
        (i18n.tr("purchase_bill"), _fmt(c["purchases"])),
        (i18n.tr("profit"), _fmt(c["profit"])),
        (i18n.tr("business_expenses"), _fmt(c["expBusiness"])),
        (i18n.tr("house_expenses"), _fmt(c["expHouse"])),
        (i18n.tr("trades"), str(c["trades"])),
        (i18n.tr("banks"), _fmt(c["bankTotal"])),
        (i18n.tr("cash"), _fmt(c["cash"])),
        (i18n.tr("total_available"), _fmt(c["available"])),
        (i18n.tr("unclaimed"), _fmt(c["unclaimed"])),
        (i18n.tr("to_receive"), _fmt(c["receivable"])),
        (i18n.tr("to_give"), _fmt(c["payable"])),
        (i18n.tr("loans_taken"), _fmt(c["loans"])),
        (i18n.tr("loans_given"), _fmt(c["loansGiven"])),
    ]
    rows, bold = [], []
    for i, r in enumerate(d["table"]):
        sign, amt = r["sign"], r["amount"]
        sign_txt = "+" if sign > 0 else "−" if sign < 0 else "="
        rows.append([i18n.tr(_SUMMARY_LABELS.get(r["key"], r["key"])), sign_txt,
                     _fmt(-amt if sign < 0 else amt)])
        if sign == 0:
            bold.append(i)
    sections = [
        ReportSection(i18n.tr("summary"),
                      [i18n.tr("name"), "", i18n.tr("amount")], rows, bold),
        ReportSection(i18n.tr("bank_balances"),
                      [i18n.tr("name"), i18n.tr("balance")],
                      [[b["name"], _fmt(b["balance"])] for b in d["banks"]]),
    ]
    return ReportData(
        i18n.tr("dashboard") + _period_suffix(start, end), [], [],
        tiles=tiles, sections=sections,
    )


def cashflow_statement_report(session: Session, start=None, end=None) -> ReportData:
    """Reports → Cash flow tab, as an exportable statement."""
    from timber.core.stats_service import cashflow_report

    d = cashflow_report(session, start, end)
    grouped: list[tuple[str, list]] = []
    for r in d["rows"]:
        if r["section"] == "worth":
            continue
        if not grouped or grouped[-1][0] != r["section"]:
            grouped.append((r["section"], [r]))
        else:
            grouped[-1][1].append(r)

    sections = []
    for sec, rws in grouped:
        rows, bold = [], []
        for i, r in enumerate(rws):
            sign, amt = r["sign"], r["amount"]
            sign_txt = "+" if sign > 0 else "−" if sign < 0 else "="
            rows.append([i18n.tr(_CF_LABELS.get(r["key"], r["key"])), sign_txt,
                         _fmt(-amt if sign < 0 else amt)])
            if sign == 0:
                bold.append(i)
        sections.append(ReportSection(
            i18n.tr(_CF_SECTIONS.get(sec, sec)),
            [i18n.tr("name"), "", i18n.tr("amount")], rows, bold))

    return ReportData(
        i18n.tr("cash_flow") + _period_suffix(start, end), [], [],
        hero=(i18n.tr("total_business_worth"), _fmt(d["worth"])),
        sections=sections,
    )


def party_performance_report(
    session: Session, party_type: str, start=None, end=None
) -> ReportData:
    """Reports → Factories / Suppliers tab, as an exportable table."""
    from timber.core.stats_service import party_stats
    from timber.db.models.party import PARTY_FACTORY

    d = party_stats(session, party_type, start, end)
    is_factory = party_type == PARTY_FACTORY
    o = d["overall"]
    vol = i18n.tr("total_sales") if is_factory else i18n.tr("total_purchases")
    tiles = [
        (i18n.tr("trades"), str(o["trades"])),
        (vol, _fmt(o["volume"])),
        (i18n.tr("profit"), _fmt(o["profit"])),
        (i18n.tr("to_receive"), _fmt(o["receivable"])),
        (i18n.tr("to_give"), _fmt(-o["payable"])),
    ]
    headers = [i18n.tr("name"), i18n.tr("trades"), vol,
               i18n.tr("profit"), i18n.tr("balance")]
    if is_factory:
        tiles += [(i18n.tr("overdue_30"), _fmt(o["over30"])),
                  (i18n.tr("overdue_60"), _fmt(o["over60"]))]
        headers += [i18n.tr("overdue_30"), i18n.tr("overdue_60")]
    rows = []
    for r in d["rows"]:
        row = [r["name"], str(r["trades"]), _fmt(r["volume"]),
               _fmt(r["profit"]), _fmt(r["balance"])]
        if is_factory:
            row += [_fmt(r["over30"]), _fmt(r["over60"])]
        rows.append(row)
    title = i18n.tr("factories") if is_factory else i18n.tr("suppliers")
    return ReportData(title + _period_suffix(start, end), headers, rows, tiles=tiles)
