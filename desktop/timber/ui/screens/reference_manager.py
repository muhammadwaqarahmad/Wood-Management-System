"""Generic manager for simple name lookups (locations, wood types)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
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
        # This screen is ALWAYS embedded in the Master Data card (Wood-types
        # tab), which supplies its own padding — so no side inset here (that
        # would double up), and no in-page title (the segment tab labels it),
        # matching the sibling PartyTypePanel.
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(12)

        # Wood types carry default rates (one per side); other lookups don't.
        self._has_rate = hasattr(model, "default_supplier_rate")
        headers = [i18n.tr("name")]
        if self._has_rate:
            headers += [i18n.tr("supplier_rate"), i18n.tr("factory_rate")]
        headers.append(i18n.tr("status"))
        self.table = make_table(headers)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        # One "Manage" dropdown holds every action (add / rename / [set rates] /
        # deactivate / delete) for a clean, consistent toolbar.
        _actions = [
            (i18n.tr("add"), self._add, "plus"),
            (i18n.tr("rename"), self._rename, "pencil"),
        ]
        if self._has_rate:
            _actions.append((i18n.tr("set_rates"), self._set_rates, "trending-up"))
        _actions += [
            (i18n.tr("deactivate"), self._toggle, "eye-off"),
            None,
            (i18n.tr("delete"), self._delete, "trash", "danger"),
        ]
        self.manage_btn = design.manage_button(_actions, parent=self)
        buttons.addWidget(self.manage_btn)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        # Everything except delete needs MANAGE_SETTINGS; delete needs DELETE_RECORD.
        _acts = self.manage_btn._manage_actions
        if not has_permission(current_user.role, Permission.MANAGE_SETTINGS):
            for a in _acts[:-1]:
                a.setEnabled(False)
        _acts[-1].setEnabled(
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
