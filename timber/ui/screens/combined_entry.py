"""Combined entry screen — link a bapari load with a factory load and
record the margin. Shows a live profit preview before saving.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core.calculations import compute_profit
from timber.core.current_user import CurrentUser
from timber.core.lookups import txn_options
from timber.core.permissions import Permission, has_permission
from timber.core.transaction_service import create_combined_txn
from timber.db.engine import SessionLocal
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


class CombinedEntryScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)
        header = QLabel(i18n.tr("combined_profit"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        form = QFormLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(i18n.tr("date"), self.date_edit)

        self.bapari_combo = QComboBox()
        self.bapari_combo.currentIndexChanged.connect(self._recalculate)
        form.addRow(i18n.tr("bapari_load"), self.bapari_combo)

        self.factory_combo = QComboBox()
        self.factory_combo.currentIndexChanged.connect(self._recalculate)
        form.addRow(i18n.tr("factory_load"), self.factory_combo)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(60)
        form.addRow(i18n.tr("notes"), self.notes_edit)

        root.addLayout(form)

        self.profit_label = QLabel()
        self.profit_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2e7d32;"
        )
        root.addWidget(self.profit_label)

        self.save_btn = QPushButton(i18n.tr("save"))
        self.save_btn.clicked.connect(self._on_save)
        root.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignRight)
        root.addStretch()

        if not has_permission(current_user.role, Permission.CREATE_TXN):
            self.save_btn.setEnabled(False)
            self.save_btn.setText(i18n.tr("no_permission"))

        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            baparis = txn_options(session, PARTY_BAPARI)
            factories = txn_options(session, PARTY_FACTORY)
        self.bapari_combo.clear()
        for opt in baparis:
            self.bapari_combo.addItem(opt["label"], opt)
        self.factory_combo.clear()
        for opt in factories:
            self.factory_combo.addItem(opt["label"], opt)
        self._recalculate()

    def _recalculate(self) -> None:
        bapari = self.bapari_combo.currentData()
        factory = self.factory_combo.currentData()
        if not bapari or not factory:
            self.profit_label.setText(f"{i18n.tr('profit')}: —")
            return
        profit = compute_profit(factory["rate"], bapari["rate"], bapari["weight"])
        colour = "#2e7d32" if profit >= 0 else "#c62828"
        self.profit_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {colour};"
        )
        self.profit_label.setText(f"{i18n.tr('profit')}: {profit:,.2f}")

    def _on_save(self) -> None:
        bapari = self.bapari_combo.currentData()
        factory = self.factory_combo.currentData()
        if not bapari or not factory:
            warn_toast(
                self, i18n.tr("cannot_save"), i18n.tr("select_both_loads")
            )
            return
        try:
            with SessionLocal() as session:
                combined = create_combined_txn(
                    session,
                    bapari_txn_id=bapari["id"],
                    factory_txn_id=factory["id"],
                    txn_date=self.date_edit.date().toPython(),
                    notes=self.notes_edit.toPlainText().strip(),
                    created_by=self.current_user.id,
                )
                session.commit()
                summary = f"#{combined.id} — {i18n.tr('profit')} {combined.profit:,.2f}"
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(
                self, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
            )
            return

        info_toast(self, i18n.tr("saved"), f"{i18n.tr('saved')} {summary}")
        self.notes_edit.clear()
