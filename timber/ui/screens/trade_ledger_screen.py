"""Trade Ledger — the complete picture of every trade line: where the
wood came from (supplier, buy rate, purchase, paid?) and where it went
(factory, sell rate, sale, paid?), with vehicle, weight and profit."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QHeaderView

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.labels import expenses_summary
from timber.core.report_data import ReportData, trade_ledger_report
from timber.core.reports import trade_ledger
from timber.db.engine import SessionLocal
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import (
    SearchBox,
    card_strip,
    colour_cell,
    fill_table,
    fmt,
    hide_empty_columns,
    make_table,
    stat_card,
)

ZERO = Decimal("0.00")
_STATUS_COLOUR = {"paid": "#16a34a", "partial": "#b45309", "unpaid": "#c62828"}


class TradeLedgerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        # Side inset so filters / cards / table sit off the panel's rounded
        # edge, consistent with the other pages.
        self._root.setContentsMargins(22, 8, 22, 14)
        self._root.setSpacing(12)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"{i18n.tr('period')}:"))
        self.period_combo = QComboBox()
        for key in ("all", "day", "week", "month", "year", "custom"):
            self.period_combo.addItem(i18n.tr(key), key)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        bar.addWidget(self.period_combo)
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate())
        self.from_date.dateChanged.connect(self.refresh)
        bar.addWidget(self.from_date)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.refresh)
        bar.addWidget(self.to_date)
        # Rendering every row grows without bound (3,000 rows ~1.8s and
        # climbing). Cap what is DRAWN; the summary cards below always cover
        # the full range, and exports are unaffected.
        bar.addWidget(QLabel(f"{i18n.tr('show')}:"))
        self.limit_combo = QComboBox()
        for lbl, val in (("200", 200), ("500", 500), ("1000", 1000), (i18n.tr("all"), 0)):
            self.limit_combo.addItem(lbl, val)
        self.limit_combo.setCurrentIndex(0)
        self.limit_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.limit_combo)
        self._filter_bar = bar
        self._root.addWidget(design.toolbar_wrap(bar))

        self._cards = QWidget()
        self._root.addWidget(self._cards)

        self.table = make_table([
            i18n.tr("date"), i18n.tr("vehicle_no"), i18n.tr("wood_type"),
            i18n.tr("weight"), i18n.tr("bapari"), i18n.tr("buy_rate"),
            i18n.tr("purchase_bill"), i18n.tr("status"),
            i18n.tr("factory"), i18n.tr("sell_rate"), i18n.tr("sale_bill"),
            i18n.tr("status"), i18n.tr("profit"), i18n.tr("freight"),
        ])
        # Freight column (loading + freight + unloading) wraps onto several
        # lines instead of being truncated.
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(13, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(13, 190)
        self.table.setWordWrap(True)
        # Search joins the filter row instead of sitting on its own line.
        self.search = SearchBox(self.table)
        self._filter_bar.addWidget(self.search, 1)
        self._root.addWidget(self.table)
        self._root.addLayout(export_buttons(self, self._build_report, "trade_ledger"))

        self._on_period_changed()

    def _date_range(self):
        period = self.period_combo.currentData()
        # Day/week/month/year are anchored on TODAY. The from-box is the custom
        # range's start only — anchoring on it would let a date left over from a
        # previous custom range silently shift "This month" into the past, and
        # the box is now hidden so nobody could see why.
        anchor = (self.from_date.date().toPython()
                  if period == "custom" else date.today())
        if period == "all":
            return None, None
        if period == "day":
            return anchor, anchor
        if period == "week":
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        if period == "month":
            last = calendar.monthrange(anchor.year, anchor.month)[1]
            return anchor.replace(day=1), anchor.replace(day=last)
        if period == "year":
            return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
        return anchor, self.to_date.date().toPython()

    def _on_period_changed(self) -> None:
        period = self.period_combo.currentData()
        # The date boxes belong to the CUSTOM range only. For Today / This
        # week / This month / This year the period speaks for itself, so the
        # boxes are hidden rather than sitting there greyed out.
        custom = period == "custom"
        self.from_date.setVisible(custom)
        self.to_date.setVisible(custom)
        self.from_date.setEnabled(custom)
        self.to_date.setEnabled(custom)
        self.refresh()

    def _build_report(self) -> ReportData:
        start, end = self._date_range()
        with SessionLocal() as session:
            return trade_ledger_report(session, start, end)

    def _rebuild_cards(self, purchase, sale, profit, n) -> None:
        self._cards.deleteLater()
        self._cards = QWidget()
        layout = QVBoxLayout(self._cards)
        layout.setContentsMargins(0, 0, 0, 0)
        pcolour = "#2e7d32" if profit >= 0 else "#c62828"
        layout.addLayout(card_strip([
            stat_card(i18n.tr("total_purchases"), fmt(purchase), "#6d28d9",
                      f"{n} {i18n.tr('trades')}"),
            stat_card(i18n.tr("total_sales"), fmt(sale), "#1565c0"),
            stat_card(i18n.tr("total_profit"), fmt(profit), pcolour),
        ]))
        self._root.insertWidget(2, self._cards)

    def refresh(self) -> None:
        start, end = self._date_range()
        with SessionLocal() as session:
            rows, purchase, sale, profit = trade_ledger(session, start, end)

        self._rebuild_cards(purchase, sale, profit, len(rows))
        limit = self.limit_combo.currentData() or 0
        shown = rows[-limit:] if limit else rows   # newest N (rows are oldest-first)
        fill_table(self.table, [
            [
                str(r.txn_date), r.vehicle, r.wood, r.weight_text,
                r.supplier_name, fmt(r.buy_rate), fmt(r.purchase_bill),
                i18n.tr(r.supplier_status), r.factory_name, fmt(r.sell_rate),
                fmt(r.sale_bill), i18n.tr(r.factory_status), fmt(r.profit),
                expenses_summary(r, sep="\n"),
            ]
            for r in shown
        ], autosize=True)
        for i, r in enumerate(shown):
            colour_cell(self.table, i, 7, _STATUS_COLOUR.get(r.supplier_status, "#475569"))
            colour_cell(self.table, i, 11, _STATUS_COLOUR.get(r.factory_status, "#475569"))
            colour_cell(self.table, i, 12, "#2e7d32" if r.profit >= 0 else "#c62828")
        # Hide the freight column only if no trade has any expense.
        hide_empty_columns(self.table, [13])
        self.search.apply()
