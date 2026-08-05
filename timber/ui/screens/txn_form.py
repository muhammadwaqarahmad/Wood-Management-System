"""Shared entry form for bapari (purchase) and factory (sale) loads.

Bapari and factory transactions have the same fields, so both screens
subclass this. It shows live bill/net totals as you type and saves via
the transaction service (validation + audit + calculations).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core.calculations import compute_bill, compute_net_amount
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import Location, Party, WoodType

_MAX = 1_000_000_000.0


def _money_spin(decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setMaximum(_MAX)
    spin.setGroupSeparatorShown(True)
    return spin


class TxnEntryForm(QWidget):
    def __init__(
        self,
        current_user: CurrentUser,
        party_type: str,
        party_label_key: str,
        save_callable: Callable,
        title_key: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.party_type = party_type
        self.save_callable = save_callable

        root = QVBoxLayout(self)

        header = QLabel(i18n.tr(title_key))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        form = QFormLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(i18n.tr("date"), self.date_edit)

        self.party_combo = QComboBox()
        form.addRow(i18n.tr(party_label_key), self.party_combo)

        self.wood_combo = QComboBox()
        form.addRow(i18n.tr("wood_type"), self.wood_combo)

        self.location_combo = QComboBox()
        form.addRow(i18n.tr("location"), self.location_combo)

        self.vehicle_edit = QLineEdit()
        self.vehicle_edit.setPlaceholderText("LEA-1234")
        form.addRow(i18n.tr("vehicle_no"), self.vehicle_edit)

        self.weight_spin = _money_spin(3)
        form.addRow(i18n.tr("weight"), self.weight_spin)

        self.rate_spin = _money_spin(2)
        form.addRow(i18n.tr("rate"), self.rate_spin)

        self.freight_spin = _money_spin(2)
        form.addRow(i18n.tr("freight"), self.freight_spin)

        self.loading_spin = _money_spin(2)
        form.addRow(i18n.tr("loading"), self.loading_spin)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(60)
        form.addRow(i18n.tr("notes"), self.notes_edit)

        root.addLayout(form)

        totals = QHBoxLayout()
        self.bill_label = QLabel()
        self.bill_label.setStyleSheet("font-weight: bold;")
        self.net_label = QLabel()
        self.net_label.setStyleSheet("font-weight: bold; color: #1565c0;")
        totals.addWidget(self.bill_label)
        totals.addStretch()
        totals.addWidget(self.net_label)
        root.addLayout(totals)

        self.save_btn = QPushButton(i18n.tr("save"))
        self.save_btn.clicked.connect(self._on_save)
        root.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignRight)
        root.addStretch()

        for spin in (
            self.weight_spin,
            self.rate_spin,
            self.freight_spin,
            self.loading_spin,
        ):
            spin.valueChanged.connect(self._recalculate)

        if not has_permission(current_user.role, Permission.CREATE_TXN):
            self.save_btn.setEnabled(False)
            self.save_btn.setText(i18n.tr("no_permission"))

        self.refresh()
        self._recalculate()

    def refresh(self) -> None:
        with SessionLocal() as session:
            parties = session.scalars(
                select(Party)
                .where(
                    Party.party_type == self.party_type,
                    Party.is_active.is_(True),
                )
                .order_by(Party.name)
            ).all()
            woods = session.scalars(
                select(WoodType).where(WoodType.is_active.is_(True)).order_by(WoodType.name)
            ).all()
            locations = session.scalars(
                select(Location).where(Location.is_active.is_(True)).order_by(Location.name)
            ).all()

        self.party_combo.clear()
        for p in parties:
            self.party_combo.addItem(p.name, p.id)

        self.wood_combo.clear()
        self.wood_combo.addItem("—", None)
        for w in woods:
            self.wood_combo.addItem(w.name, w.id)

        self.location_combo.clear()
        self.location_combo.addItem("—", None)
        for loc in locations:
            self.location_combo.addItem(loc.name, loc.id)

    def _recalculate(self) -> None:
        bill = compute_bill(self.weight_spin.value(), self.rate_spin.value())
        net = compute_net_amount(
            bill, self.freight_spin.value(), self.loading_spin.value()
        )
        self.bill_label.setText(f"{i18n.tr('bill')}: {bill:,.2f}")
        self.net_label.setText(f"{i18n.tr('net')}: {net:,.2f}")

    def _on_save(self) -> None:
        data = dict(
            txn_date=self.date_edit.date().toPython(),
            party_id=self.party_combo.currentData(),
            wood_type_id=self.wood_combo.currentData(),
            location_id=self.location_combo.currentData(),
            vehicle_no=self.vehicle_edit.text().strip(),
            weight=self.weight_spin.value(),
            rate=self.rate_spin.value(),
            freight=self.freight_spin.value(),
            loading=self.loading_spin.value(),
            notes=self.notes_edit.toPlainText().strip(),
            created_by=self.current_user.id,
        )
        try:
            with SessionLocal() as session:
                txn = self.save_callable(session, **data)
                session.commit()
                summary = f"#{txn.id} — {i18n.tr('bill')} {txn.bill:,.2f}, {i18n.tr('net')} {txn.net_amount:,.2f}"
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(
                self, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
            )
            return

        info_toast(self, i18n.tr("saved"), f"{i18n.tr('saved')} {summary}")
        self._reset_inputs()

    def _reset_inputs(self) -> None:
        for spin in (
            self.weight_spin,
            self.rate_spin,
            self.freight_spin,
            self.loading_spin,
        ):
            spin.setValue(0)
        self.vehicle_edit.clear()
        self.notes_edit.clear()
        self._recalculate()
        self.weight_spin.setFocus()
