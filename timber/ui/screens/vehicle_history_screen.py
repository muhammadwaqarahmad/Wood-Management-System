"""Vehicle history — every load carried by a given vehicle."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import known_vehicles, vehicle_history
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class VehicleHistoryScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        # Side inset; no in-page title (the page bar shows the page name).
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"{i18n.tr('vehicle_no')}:"))
        self.vehicle_combo = QComboBox()
        self.vehicle_combo.setEditable(True)
        self.vehicle_combo.setMinimumWidth(220)
        self.vehicle_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self.vehicle_combo)
        top.addStretch()
        root.addWidget(design.toolbar_wrap(top))

        self.table = make_table(
            [
                i18n.tr("side"),
                i18n.tr("date"),
                i18n.tr("party"),
                i18n.tr("weight"),
                i18n.tr("rate"),
                i18n.tr("bill"),
            ]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            vehicles = known_vehicles(session)
        self.vehicle_combo.blockSignals(True)
        self.vehicle_combo.clear()
        self.vehicle_combo.addItems(vehicles)
        self.vehicle_combo.setCurrentIndex(0 if vehicles else -1)
        self.vehicle_combo.blockSignals(False)
        self._load()

    def _load(self) -> None:
        vehicle = self.vehicle_combo.currentText().strip()
        if not vehicle:
            self.table.setRowCount(0)
            return
        with SessionLocal() as session:
            rows = vehicle_history(session, vehicle)
        fill_table(
            self.table,
            [
                [r.side, str(r.txn_date), r.party_name, f"{r.weight:g}",
                 fmt(r.rate), fmt(r.bill)]
                for r in rows
            ],
        )
        self.search.apply()
