"""Advance register — baparis we've paid in advance (unworked-off)."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import advance_register
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class AdvanceRegisterScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        header = QLabel(i18n.tr("advances"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        self.total_label = QLabel("")
        self.total_label.setStyleSheet(
            f"font-size:15px;font-weight:800;color:{design.c('accent2')};")
        root.addWidget(self.total_label)

        self.table = make_table([i18n.tr("bapari"), i18n.tr("advance")])
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = advance_register(session)
        fill_table(self.table, [[r.name, fmt(r.advance)] for r in rows])
        self.search.apply()
        total = sum((r.advance for r in rows), Decimal("0"))
        self.total_label.setText(f"{i18n.tr('total_advance')}: {fmt(total)}")
