"""Quick-entry screen — fast load entry with minimal clicks.

Features: bapari/factory toggle, party + vehicle autocomplete,
remembered rate (auto-fills from the party's last load), and a
"duplicate last entry" button.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core.calculations import compute_bill
from timber.core.current_user import CurrentUser
from timber.core.lookups import last_rate_for_party, last_txn, recent_vehicles
from timber.core.permissions import Permission, has_permission
from timber.core.transaction_service import create_bapari_txn, create_factory_txn
from timber.db.engine import SessionLocal
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


class QuickEntryScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)
        header = QLabel(i18n.tr("quick_entry"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        toggle = QHBoxLayout()
        self.bapari_radio = QRadioButton(i18n.tr("bapari_purchase"))
        self.factory_radio = QRadioButton(i18n.tr("factory_sale"))
        self.bapari_radio.setChecked(True)
        self.bapari_radio.toggled.connect(self._on_type_changed)
        toggle.addWidget(self.bapari_radio)
        toggle.addWidget(self.factory_radio)
        toggle.addStretch()
        root.addLayout(toggle)

        form = QFormLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(i18n.tr("date"), self.date_edit)

        self.party_combo = QComboBox()
        self.party_combo.setEditable(True)
        self.party_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.party_combo.completer().setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.party_combo.currentIndexChanged.connect(self._on_party_changed)
        form.addRow(i18n.tr("party"), self.party_combo)

        self.vehicle_edit = QLineEdit()
        self.vehicle_edit.setPlaceholderText("LEA-1234")
        form.addRow(i18n.tr("vehicle_no"), self.vehicle_edit)

        self.weight_spin = self._spin(3)
        form.addRow(i18n.tr("weight"), self.weight_spin)

        self.rate_spin = self._spin(2)
        form.addRow(i18n.tr("rate"), self.rate_spin)

        self.freight_spin = self._spin(2)
        form.addRow(i18n.tr("freight"), self.freight_spin)

        root.addLayout(form)

        self.bill_label = QLabel()
        self.bill_label.setStyleSheet("font-weight: bold;")
        root.addWidget(self.bill_label)
        for spin in (self.weight_spin, self.rate_spin):
            spin.valueChanged.connect(self._recalculate)

        buttons = QHBoxLayout()
        self.duplicate_btn = QPushButton(i18n.tr("duplicate_last"))
        self.duplicate_btn.clicked.connect(self._duplicate_last)
        self.save_btn = QPushButton(i18n.tr("save"))
        self.save_btn.clicked.connect(self._on_save)
        buttons.addWidget(self.duplicate_btn)
        buttons.addStretch()
        buttons.addWidget(self.save_btn)
        root.addLayout(buttons)
        root.addStretch()

        if not has_permission(current_user.role, Permission.CREATE_TXN):
            for w in (self.save_btn, self.duplicate_btn):
                w.setEnabled(False)
            self.save_btn.setText(i18n.tr("no_permission"))

        self.refresh()
        self._recalculate()

    @staticmethod
    def _spin(decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setMaximum(1_000_000_000.0)
        spin.setGroupSeparatorShown(True)
        return spin

    def _current_type(self) -> str:
        return PARTY_BAPARI if self.bapari_radio.isChecked() else PARTY_FACTORY

    def refresh(self) -> None:
        ptype = self._current_type()
        with SessionLocal() as session:
            parties = session.scalars(
                select(Party)
                .where(Party.party_type == ptype, Party.is_active.is_(True))
                .order_by(Party.name)
            ).all()
            vehicles = recent_vehicles(session)

        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        for p in parties:
            self.party_combo.addItem(p.name, p.id)
        self.party_combo.setCurrentIndex(-1)
        self.party_combo.blockSignals(False)

        completer = QCompleter(vehicles, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.vehicle_edit.setCompleter(completer)
        from timber.ui.searchable import style_completer_popup
        style_completer_popup(completer)

    def _on_type_changed(self) -> None:
        if self.bapari_radio.isChecked() or self.factory_radio.isChecked():
            self.refresh()

    def _on_party_changed(self) -> None:
        party_id = self.party_combo.currentData()
        if not party_id:
            return
        with SessionLocal() as session:
            rate = last_rate_for_party(session, party_id, self._current_type())
        if rate is not None and self.rate_spin.value() == 0:
            self.rate_spin.setValue(float(rate))

    def _recalculate(self) -> None:
        bill = compute_bill(self.weight_spin.value(), self.rate_spin.value())
        self.bill_label.setText(f"{i18n.tr('bill')}: {bill:,.2f}")

    def _duplicate_last(self) -> None:
        with SessionLocal() as session:
            txn = last_txn(session, self._current_type())
            if txn is None:
                info_toast(
                    self, i18n.tr("duplicate_last"), i18n.tr("no_previous")
                )
                return
            party_id = txn.party_id
            vehicle = txn.vehicle_no or ""
            weight = float(txn.weight)
            rate = float(txn.rate)
            freight = float(txn.freight)

        idx = self.party_combo.findData(party_id)
        if idx >= 0:
            self.party_combo.setCurrentIndex(idx)
        self.vehicle_edit.setText(vehicle)
        self.weight_spin.setValue(weight)
        self.rate_spin.setValue(rate)
        self.freight_spin.setValue(freight)
        self._recalculate()

    def _on_save(self) -> None:
        service = (
            create_bapari_txn
            if self._current_type() == PARTY_BAPARI
            else create_factory_txn
        )
        data = dict(
            txn_date=self.date_edit.date().toPython(),
            party_id=self.party_combo.currentData(),
            vehicle_no=self.vehicle_edit.text().strip(),
            weight=self.weight_spin.value(),
            rate=self.rate_spin.value(),
            freight=self.freight_spin.value(),
            created_by=self.current_user.id,
        )
        try:
            with SessionLocal() as session:
                txn = service(session, **data)
                session.commit()
                summary = f"#{txn.id} — {i18n.tr('bill')} {txn.bill:,.2f}"
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(
                self, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
            )
            return

        info_toast(self, i18n.tr("saved"), f"{i18n.tr('saved')} {summary}")
        self.weight_spin.setValue(0)
        self.vehicle_edit.clear()
        self._recalculate()
        self.weight_spin.setFocus()
