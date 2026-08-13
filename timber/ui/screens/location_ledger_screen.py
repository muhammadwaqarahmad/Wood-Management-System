"""Location ledger — purchases vs sales per city."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import location_summary
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class LocationLedgerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        # Side inset; no in-page title (the page bar shows the page name).
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        self.table = make_table(
            [
                i18n.tr("location"),
                i18n.tr("purchases"),
                i18n.tr("sales"),
                i18n.tr("difference"),
            ]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = location_summary(session)
        fill_table(
            self.table,
            [
                [r.name, fmt(r.purchases), fmt(r.sales), fmt(r.difference)]
                for r in rows
            ],
        )
        self.search.apply()
