"""Generic manager for simple name lookups (locations, wood types)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core import admin_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import fill_table, make_table


class ReferenceManagerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, model: type, title_key: str, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.model = model

        root = QVBoxLayout(self)
        header = QLabel(i18n.tr(title_key))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        root.addWidget(header)

        # Wood types carry default rates (one per side); other lookups don't.
        self._has_rate = hasattr(model, "default_supplier_rate")
        headers = [i18n.tr("name")]
        if self._has_rate:
            headers += [i18n.tr("supplier_rate"), i18n.tr("factory_rate")]
        headers.append(i18n.tr("status"))
        self.table = make_table(headers)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton(i18n.tr("add"))
        self.rename_btn = QPushButton(i18n.tr("rename"))
        self.toggle_btn = QPushButton(i18n.tr("deactivate"))
        self.delete_btn = QPushButton(i18n.tr("delete"))
        self.delete_btn.setStyleSheet(design.btn("danger"))
        self.rates_btn = QPushButton(i18n.tr("set_rates"))
        self.rates_btn.clicked.connect(self._set_rates)
        self.rates_btn.setVisible(self._has_rate)
        self.add_btn.clicked.connect(self._add)
        self.rename_btn.clicked.connect(self._rename)
        self.toggle_btn.clicked.connect(self._toggle)
        self.delete_btn.clicked.connect(self._delete)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.rename_btn)
        if self._has_rate:
            buttons.addWidget(self.rates_btn)
        buttons.addWidget(self.toggle_btn)
        buttons.addWidget(self.delete_btn)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        if not has_permission(current_user.role, Permission.MANAGE_SETTINGS):
            for b in (self.add_btn, self.rename_btn, self.rates_btn, self.toggle_btn):
                b.setEnabled(False)
        self.delete_btn.setEnabled(
            has_permission(current_user.role, Permission.DELETE_RECORD)
        )

        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            self._items = list(
                session.scalars(select(self.model).order_by(self.model.name))
            )
            status = lambda it: i18n.tr("active") if it.is_active else i18n.tr("inactive")
            if self._has_rate:
                def _shown(v):
                    # 0 means "no default set" — say so instead of "0.00".
                    return f"{float(v):,.2f}" if v and float(v) > 0 else "—"
                rows = [
                    [it.name, _shown(it.default_supplier_rate),
                     _shown(it.default_factory_rate), status(it)]
                    for it in self._items
                ]
            else:
                rows = [[it.name, status(it)] for it in self._items]
            self._ids = [it.id for it in self._items]
            self._active = [it.is_active for it in self._items]
        fill_table(self.table, rows)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return None
        return self._ids[row]

    def _run(self, func, *args) -> None:
        try:
            with SessionLocal() as session:
                func(session, *args, created_by=self.current_user.id)
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, i18n.tr("add"), i18n.tr("name"))
        if ok and name.strip():
            self._run(admin_service.create_lookup, self.model, name)

    def _rename(self) -> None:
        item_id = self._selected_id()
        if item_id is None:
            return
        name, ok = QInputDialog.getText(self, i18n.tr("rename"), i18n.tr("name"))
        if ok and name.strip():
            self._run(admin_service.rename_lookup, self.model, item_id, name)

    def _set_rates(self) -> None:
        """Set the default supplier / factory rate for the chosen wood."""
        item_id = self._selected_id()
        if item_id is None:
            return
        current = next((i for i in self._items if i.id == item_id), None)
        dlg = design.Dialog(i18n.tr("set_rates"), "database",
                            current.name if current else "", parent=self, width=460)
        sup = QDoubleSpinBox()
        sup.setDecimals(2)
        sup.setMaximum(1_000_000.0)
        sup.setGroupSeparatorShown(True)
        fac = QDoubleSpinBox()
        fac.setDecimals(2)
        fac.setMaximum(1_000_000.0)
        fac.setGroupSeparatorShown(True)
        if current is not None:
            sup.setValue(float(current.default_supplier_rate or 0))
            fac.setValue(float(current.default_factory_rate or 0))
        dlg.field(i18n.tr("supplier_rate"), sup, i18n.tr("rate_hint"))
        dlg.field(i18n.tr("factory_rate"), fac)
        ok, _cancel = dlg.buttons(i18n.tr("save"))
        ok.clicked.connect(dlg.accept)
        if not dlg.exec():
            return
        self._run(
            admin_service.set_lookup_rates, self.model, item_id,
            sup.value(), fac.value(),
        )

    def _toggle(self) -> None:
        row = self.table.currentRow()
        item_id = self._selected_id()
        if item_id is None:
            return
        new_active = not self._active[row]
        self._run(admin_service.set_lookup_active, self.model, item_id, new_active)

    def _delete(self) -> None:
        item_id = self._selected_id()
        if item_id is None:
            return
        if not design.confirm(self, i18n.tr("delete"), i18n.tr("confirm_delete"), danger=True):
            return
        self._run(admin_service.delete_lookup, self.model, item_id)
