"""Bank Book — per-account daily Opening/In/Out/Closing (each day's
closing carries to the next day's opening) plus a per-transaction
running statement. Exportable to PDF/Excel."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber import i18n
from timber.ui import design
from timber.core.bank_ledger import bank_daily_book, bank_statement
from timber.core.current_user import CurrentUser
from timber.core.report_data import (
    ReportData,
    bank_daily_report,
    bank_statement_report,
)
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class BankBookScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)


        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"{i18n.tr('bank_accounts')}:"))
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(200)
        self.account_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.account_combo)

        bar.addWidget(QLabel(f"{i18n.tr('show')}:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem(i18n.tr("daily_summary"), "daily")
        self.view_combo.addItem(i18n.tr("statement"), "statement")
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        bar.addWidget(self.view_combo)

        bar.addWidget(QLabel(f"{i18n.tr('period')}:"))
        self.period_combo = QComboBox()
        for key in ("day", "week", "month", "year", "custom", "all"):
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
        bar.addStretch()
        root.addWidget(design.toolbar_wrap(bar))

        # Opening / in / out / closing as tiles instead of one crammed line.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_open, self.tile_opening = design.stat_tile(
            i18n.tr("opening"), design.TONES["slate"], "book-open")
        t_in, self.tile_in = design.stat_tile(
            i18n.tr("money_in"), design.TONES["emerald"], "trending-up")
        t_out, self.tile_out = design.stat_tile(
            i18n.tr("money_out"), design.TONES["rose"], "trending-down")
        t_close, self.tile_closing = design.stat_tile(
            i18n.tr("closing"), design.c("accent"), "wallet")
        for t in (t_open, t_in, t_out, t_close):
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        self.daily_table = make_table(
            [
                i18n.tr("date"), i18n.tr("opening"), i18n.tr("money_in"),
                i18n.tr("money_out"), i18n.tr("closing"),
            ]
        )
        self.stmt_table = make_table(
            [
                i18n.tr("date"), i18n.tr("from"), i18n.tr("to"),
                i18n.tr("money_in"), i18n.tr("money_out"), i18n.tr("balance"),
            ]
        )
        self.search = SearchBox(self.stmt_table)
        root.addWidget(self.search)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.daily_table)   # index 0
        self.stack.addWidget(self.stmt_table)     # index 1
        root.addWidget(self.stack)
        root.addLayout(export_buttons(self, self._build_report, "bank_book"))

        self._on_period_changed()
        self._on_view_changed()
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
        return anchor, self.to_date.date().toPython()  # custom

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

    def _on_view_changed(self) -> None:
        is_daily = self.view_combo.currentData() == "daily"
        self.stack.setCurrentIndex(0 if is_daily else 1)
        self.search.setVisible(not is_daily)  # search applies to the statement
        self.refresh()

    def _build_report(self) -> ReportData:
        account_id = self.account_combo.currentData()
        if not account_id:
            raise ValueError(i18n.tr("select_item"))
        start, end = self._date_range()
        with SessionLocal() as session:
            if self.view_combo.currentData() == "daily":
                return bank_daily_report(session, account_id, start, end)
            return bank_statement_report(session, account_id, start, end)

    # -- data --
    def refresh(self) -> None:
        prev = self.account_combo.currentData()
        with SessionLocal() as session:
            accounts = session.scalars(
                select(BankAccount).order_by(BankAccount.name)
            ).all()
            self.account_combo.blockSignals(True)
            self.account_combo.clear()
            for a in accounts:
                self.account_combo.addItem(a.name, a.id)
            if prev is not None:
                idx = self.account_combo.findData(prev)
                if idx >= 0:
                    self.account_combo.setCurrentIndex(idx)
            self.account_combo.blockSignals(False)

            account_id = self.account_combo.currentData()
            if not account_id:
                self.daily_table.setRowCount(0)
                self.stmt_table.setRowCount(0)
                for lbl in (self.tile_opening, self.tile_in,
                            self.tile_out, self.tile_closing):
                    lbl.setText("—")
                return

            start, end = self._date_range()
            if self.view_combo.currentData() == "daily":
                book = bank_daily_book(session, account_id, start, end)
                fill_table(
                    self.daily_table,
                    [
                        [str(r.day), fmt(r.opening), fmt(r.money_in),
                         fmt(r.money_out), fmt(r.closing)]
                        for r in book.rows
                    ],
                )
                closing = book.rows[-1].closing if book.rows else 0
                # The daily view only carries a closing figure.
                self.tile_opening.setText("—")
                self.tile_in.setText(fmt(sum(r.money_in for r in book.rows)))
                self.tile_out.setText(fmt(sum(r.money_out for r in book.rows)))
                self.tile_closing.setText(fmt(closing))
            else:
                st = bank_statement(session, account_id, start, end)
                fill_table(
                    self.stmt_table,
                    [
                        [str(e.entry_date), e.source, e.destination,
                         fmt(e.money_in) if e.money_in else "",
                         fmt(e.money_out) if e.money_out else "",
                         fmt(e.balance)]
                        for e in st.entries
                    ],
                )
                self.search.apply()
                self.tile_opening.setText(fmt(st.opening))
                self.tile_in.setText(fmt(st.total_in))
                self.tile_out.setText(fmt(st.total_out))
                self.tile_closing.setText(fmt(st.closing))
