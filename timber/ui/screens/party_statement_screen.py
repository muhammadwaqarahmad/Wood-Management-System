"""Reusable per-party statement screen (Supplier / Factory ledgers).

Pick a party, filter by period, and see a rich running statement: each
load shows vehicle, wood, weight, rate, bill and whether it's paid; each
payment shows the method. Summary cards + PDF/Excel export.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.ledger import detailed_party_statement
from timber.core.report_data import ReportData, detailed_statement_report
from timber.db.engine import SessionLocal
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI
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


class PartyStatementScreen(QWidget):
    def __init__(self, current_user: CurrentUser, party_type: str,
                 title_key: str, parent=None) -> None:
        super().__init__(parent)
        self.party_type = party_type
        self._is_supplier = party_type == PARTY_BAPARI

        self._root = QVBoxLayout(self)
        header = QLabel(i18n.tr(title_key))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        self._root.addWidget(header)

        bar = QHBoxLayout()
        label = i18n.tr("bapari") if self._is_supplier else i18n.tr("factory")
        bar.addWidget(QLabel(f"{label}:"))
        # Type-to-filter picker, the same control Buy & Sell uses — a plain
        # combo means scrolling a list of ~95 parties to find one.
        from timber.ui.searchable import SearchableComboBox

        self.party_combo = SearchableComboBox(i18n.tr("search"))
        self.party_combo.setMinimumWidth(260)
        self.party_combo.currentIndexChanged.connect(self._load)
        bar.addWidget(self.party_combo)

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
        self.from_date.dateChanged.connect(self._load)
        bar.addWidget(self.from_date)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self._load)
        bar.addWidget(self.to_date)
        # Match the boxes to the starting period. _on_period_changed cannot be
        # used here — it reloads, and the table does not exist yet.
        self._sync_range_boxes()
        # The search sits WITH the filters rather than on its own row below.
        # It is appended after the table exists (a SearchBox needs its table),
        # but the row is already laid out so it lands in the right place.
        self._filter_bar = bar
        self._root.addWidget(design.toolbar_wrap(bar))

        self._cards = QWidget()
        self._root.addWidget(self._cards)

        counter_label = i18n.tr("factory") if self._is_supplier else i18n.tr("bapari")
        self.table = make_table([
            i18n.tr("date"), i18n.tr("description"), counter_label,
            i18n.tr("vehicle_no"), i18n.tr("wood_type"), i18n.tr("weight"),
            i18n.tr("rate"), i18n.tr("freight"), i18n.tr("total"),
            i18n.tr("bill_amount"), i18n.tr("payment"),
            i18n.tr("expenses"), i18n.tr("balance"),
        ])
        # Let the Detail/expenses column wrap onto several lines.
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(11, QHeaderView.ResizeMode.Fixed)  # expenses/detail
        self.table.setColumnWidth(11, 200)
        self.table.setWordWrap(True)
        self.search = SearchBox(self.table)
        self._filter_bar.addWidget(self.search, 1)
        self._root.addWidget(self.table, 1)
        self._root.addLayout(export_buttons(self, self._build_report, "statement"))

        self.refresh()

    # -- helpers --
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

    def _sync_range_boxes(self) -> None:
        """Show the from/to boxes only for the CUSTOM range.

        For Today / This week / This month / This year the period speaks for
        itself, so the boxes are hidden rather than sitting there greyed out.
        """
        custom = self.period_combo.currentData() == "custom"
        self.from_date.setVisible(custom)
        self.to_date.setVisible(custom)
        self.from_date.setEnabled(custom)
        self.to_date.setEnabled(custom)

    def _on_period_changed(self) -> None:
        self._sync_range_boxes()
        self._load()

    def _build_report(self) -> ReportData:
        party_id = self.party_combo.currentData()
        if not party_id:
            raise ValueError(i18n.tr("select_party"))
        start, end = self._date_range()
        with SessionLocal() as session:
            return detailed_statement_report(session, party_id, start, end)

    # -- data --
    def refresh(self) -> None:
        prev = self.party_combo.currentData()
        with SessionLocal() as session:
            parties = session.scalars(
                select(Party).where(
                    Party.party_type == self.party_type, Party.is_active.is_(True)
                ).order_by(Party.name)
            ).all()
        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        for p in parties:
            self.party_combo.addItem(p.name, p.id)
        if prev is not None:
            idx = self.party_combo.findData(prev)
            if idx >= 0:
                self.party_combo.setCurrentIndex(idx)
        self.party_combo.blockSignals(False)
        self._load()

    def _clear_cards(self) -> None:
        self._cards.deleteLater()
        self._cards = QWidget()
        self._root.insertWidget(2, self._cards)

    def _load(self) -> None:
        party_id = self.party_combo.currentData()
        if not party_id:
            self.table.setRowCount(0)
            self._clear_cards()
            return
        start, end = self._date_range()
        with SessionLocal() as session:
            st = detailed_party_statement(session, party_id, start, end)

        rows = []
        for e in st.entries:
            kind = i18n.tr("load") if e.kind == "load" else i18n.tr("payment")
            detail = e.expenses if e.kind == "load" else e.payment_detail
            rows.append([
                str(e.entry_date), kind, e.counterparty, e.vehicle, e.wood,
                e.weight_text,
                fmt(e.rate) if e.kind == "load" else "",
                fmt(-e.freight) if e.kind == "load" and e.freight else "",
                fmt(e.total) if e.kind == "load" else "",
                fmt(e.debit) if e.debit else "",
                fmt(e.credit) if e.credit else "",
                detail, fmt(e.balance),
            ])
        fill_table(self.table, rows, autosize=True)
        for i, e in enumerate(st.entries):
            if e.debit:
                colour_cell(self.table, i, 9, "#c62828")   # bill (we buy / they buy)
            if e.credit:
                colour_cell(self.table, i, 10, "#2e7d32")  # payment
            # Balance: negative = a debt, positive = in our favour.
            colour_cell(self.table, i, 12, "#c62828" if e.balance < 0 else "#2e7d32")
        hide_empty_columns(self.table, [2])  # hide counterparty if empty
        self.search.apply()

        self._rebuild_cards(st)

    def _balance_card(self, balance) -> "QWidget":
        # Universal rule: negative = we must GIVE (we owe); positive = we will
        # RECEIVE (owed to us). Same meaning for suppliers and factories.
        if balance < 0:
            label, colour, value = i18n.tr("you_owe"), "#c62828", fmt(-balance)
        elif balance > 0:
            label, colour, value = i18n.tr("owes_you"), "#16a34a", fmt(balance)
        else:
            label, colour, value = i18n.tr("balance"), "#64748b", fmt(ZERO)
        return stat_card(label, value, colour)

    def _rebuild_cards(self, st) -> None:
        self._cards.deleteLater()
        self._cards = QWidget()
        layout = QVBoxLayout(self._cards)
        layout.setContentsMargins(0, 0, 0, 0)
        loads_label = i18n.tr("purchases") if self._is_supplier else i18n.tr("sales")
        layout.addLayout(card_strip([
            self._balance_card(st.closing),
            stat_card(loads_label, fmt(st.total_loads), "#1565c0"),
            stat_card(i18n.tr("total_paid"), fmt(st.total_paid), "#2e7d32"),
        ]))
        self._root.insertWidget(2, self._cards)
