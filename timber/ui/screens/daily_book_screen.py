"""Daily book (روزنامچہ) — everything that happened on a chosen day."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.report_data import ReportData, daily_book_report
from timber.core.reports import daily_book
from timber.db.engine import SessionLocal
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class DailyBookScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        header = QLabel(i18n.tr("daily_book"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"{i18n.tr('date')}:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self._load)
        top.addWidget(self.date_edit)
        top.addStretch()
        root.addWidget(design.toolbar_wrap(top))

        self.table = make_table(
            [i18n.tr("kind"), i18n.tr("party"), i18n.tr("detail"), i18n.tr("amount")]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        root.addLayout(export_buttons(self, self._build_report, "daily_book"))
        self._load()

    def _build_report(self) -> ReportData:
        with SessionLocal() as session:
            return daily_book_report(session, self.date_edit.date().toPython())

    def refresh(self) -> None:
        self._load()

    def _load(self) -> None:
        day = self.date_edit.date().toPython()
        with SessionLocal() as session:
            entries = daily_book(session, day)
        fill_table(
            self.table,
            [[e.kind, e.party_name, e.detail, fmt(e.amount)] for e in entries],
        )
        self.search.apply()
