"""Wood-type ledger — weight bought vs sold per wood type."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import wood_type_summary
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, make_table


class WoodTypeLedgerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        header = QLabel(i18n.tr("wood_type_ledger"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        self.table = make_table(
            [i18n.tr("wood_type"), i18n.tr("bought"), i18n.tr("sold")]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = wood_type_summary(session)
        fill_table(
            self.table,
            [
                [r.name, f"{r.bought_weight:,.3f}", f"{r.sold_weight:,.3f}"]
                for r in rows
            ],
        )
        self.search.apply()
