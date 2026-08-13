"""Advance register — baparis we've paid in advance (unworked-off)."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

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
        # Side inset; no in-page title (the page bar shows the page name).
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        # Total advance as a KPI tile, matching the other summary pages.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_total, self.total_label = design.stat_tile(
            i18n.tr("total_advance"), design.TONES["violet"], "hand-coins")
        tiles.addWidget(t_total, 1)
        tiles.addStretch(2)
        root.addLayout(tiles)

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
        self.total_label.setText(fmt(total))
