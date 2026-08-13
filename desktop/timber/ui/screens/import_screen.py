"""Bulk import screen — download a template, then import an .xlsx."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
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
from timber.core import excel_import
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

# (entity key, label key)
_ENTITIES = [
    ("parties", "parties"),
    ("bapari", "bapari_purchase"),
    ("factory", "factory_sale"),
]


class ImportScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)
        header = QLabel(i18n.tr("import_data"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"{i18n.tr('import_what')}:"))
        self.entity_combo = QComboBox()
        for key, label_key in _ENTITIES:
            self.entity_combo.addItem(i18n.tr(label_key), key)
        top.addWidget(self.entity_combo)
        top.addStretch()
        root.addWidget(design.toolbar_wrap(top))

        buttons = QHBoxLayout()
        self.template_btn = QPushButton(i18n.tr("download_template"))
        self.import_btn = QPushButton(i18n.tr("import_file"))
        self.template_btn.clicked.connect(self._download_template)
        self.import_btn.clicked.connect(self._import)
        buttons.addWidget(self.template_btn)
        buttons.addWidget(self.import_btn)
        buttons.addStretch()
        root.addLayout(buttons)

        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        root.addWidget(self.result)

        can = has_permission(current_user.role, Permission.MANAGE_SETTINGS)
        self.import_btn.setEnabled(can)

    def refresh(self) -> None:
        pass

    def _download_template(self) -> None:
        entity = self.entity_combo.currentData()
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("download_template"), f"{entity}_template.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            if entity == "parties":
                excel_import.write_party_template(path)
            else:
                excel_import.write_txn_template(path)
        except Exception as exc:  # noqa: BLE001
            err_toast(self, i18n.tr("error"), str(exc))
            return
        info_toast(self, i18n.tr("exported"), path)

    def _import(self) -> None:
        entity = self.entity_combo.currentData()
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("import_file"), "", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            with SessionLocal() as session:
                if entity == "parties":
                    report = excel_import.import_parties(
                        session, path, created_by=self.current_user.id
                    )
                else:
                    side = PARTY_BAPARI if entity == "bapari" else PARTY_FACTORY
                    report = excel_import.import_transactions(
                        session, path, side, created_by=self.current_user.id
                    )
                session.commit()
        except Exception as exc:  # noqa: BLE001
            err_toast(self, i18n.tr("error"), str(exc))
            return

        lines = [f"{i18n.tr('created_label')}: {report.created}",
                 f"{i18n.tr('errors_label')}: {len(report.errors)}"]
        for row_no, message in report.errors:
            lines.append(f"  {i18n.tr('row_label')} {row_no}: {message}")
        self.result.setPlainText("\n".join(lines))
