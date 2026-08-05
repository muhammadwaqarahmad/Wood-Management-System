"""Overdue reminders — factories holding your money past their credit
period, with how much and how many days late.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import overdue_report
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class OverdueScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)


        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_amt, self.total_label = design.stat_tile(
            i18n.tr("outstanding"), design.TONES["rose"], "alert-triangle")
        t_cnt, self.tile_count = design.stat_tile(
            i18n.tr("factory"), design.c("accent"), "factory")
        t_worst, self.tile_worst = design.stat_tile(
            i18n.tr("days_overdue"), design.TONES["amber"], "alarm-clock")
        for t in (t_amt, t_cnt, t_worst):
            tiles.addWidget(t, 1)
        tiles.addStretch(1)
        root.addLayout(tiles)

        self.table = make_table(
            [
                i18n.tr("factory"),
                i18n.tr("outstanding"),
                i18n.tr("oldest_unpaid"),
                i18n.tr("days_outstanding"),
                i18n.tr("credit_days"),
                i18n.tr("days_overdue"),
            ]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)

        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = overdue_report(session)
        fill_table(
            self.table,
            [
                [
                    r.name, fmt(r.outstanding), str(r.oldest_date),
                    str(r.days_outstanding), str(r.credit_days), str(r.days_overdue),
                ]
                for r in rows
            ],
        )
        # Tint the "days overdue" cell red.
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 5)
            if item:
                item.setBackground(QColor(design.tint(design.NEG, 40)))
        self.search.apply()
        total = sum((r.outstanding for r in rows), Decimal("0"))
        self.total_label.setText(fmt(total))
        self.tile_count.setText(str(len(rows)))
        worst = max((r.days_overdue for r in rows), default=0)
        self.tile_worst.setText(str(worst))
