"""Aging report — factory receivables split into 30/60/90 buckets."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import aging_report
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class AgingScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # The age buckets are the story on this page — show them as tiles,
        # greener when the money is young, redder as it ages.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t1, self.tile_0_30 = design.stat_tile(
            i18n.tr("b_0_30"), design.TONES["emerald"], "calendar-clock")
        t2, self.tile_31_60 = design.stat_tile(
            i18n.tr("b_31_60"), design.TONES["sky"], "calendar-clock")
        t3, self.tile_61_90 = design.stat_tile(
            i18n.tr("b_61_90"), design.TONES["amber"], "alarm-clock")
        t4, self.tile_90p = design.stat_tile(
            i18n.tr("b_90p"), design.TONES["rose"], "alert-triangle")
        t5, self.total_label = design.stat_tile(
            i18n.tr("total_receivable"), design.c("accent"), "wallet")
        for t in (t1, t2, t3, t4, t5):
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        self.table = make_table(
            [
                i18n.tr("factory"), i18n.tr("b_0_30"), i18n.tr("b_31_60"),
                i18n.tr("b_61_90"), i18n.tr("b_90p"), i18n.tr("outstanding"),
            ]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = aging_report(session)
        fill_table(
            self.table,
            [
                [r.name, fmt(r.b0_30), fmt(r.b31_60), fmt(r.b61_90), fmt(r.b90p), fmt(r.total)]
                for r in rows
            ],
        )
        self.search.apply()
        total = sum((r.total for r in rows), Decimal("0"))
        self.tile_0_30.setText(fmt(sum((r.b0_30 for r in rows), Decimal("0"))))
        self.tile_31_60.setText(fmt(sum((r.b31_60 for r in rows), Decimal("0"))))
        self.tile_61_90.setText(fmt(sum((r.b61_90 for r in rows), Decimal("0"))))
        self.tile_90p.setText(fmt(sum((r.b90p for r in rows), Decimal("0"))))
        self.total_label.setText(fmt(total))
