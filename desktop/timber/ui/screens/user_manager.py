"""Manage user accounts (Admin only): add, edit role, reset password."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.core import admin_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, Role, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import User
from timber.ui import design, icons
from timber.ui.screens.table_utils import fill_table, make_table


class UserDialog(design.Dialog):
    def __init__(self, user=None, parent=None) -> None:
        self.is_edit = user is not None
        super().__init__(
            i18n.tr("edit") if user else i18n.tr("add"), "user",
            user.username if user else "", parent=parent, width=460)

        self.username_edit = QLineEdit(user.username if user else "")
        self.username_edit.setEnabled(not self.is_edit)
        self.field(i18n.tr("username"), self.username_edit)

        self.full_name_edit = QLineEdit(user.full_name if user and user.full_name else "")
        self.field(i18n.tr("full_name"), self.full_name_edit)

        self.role_combo = QComboBox()
        for role in Role:
            self.role_combo.addItem(role.value, role.value)
        if user:
            self.role_combo.setCurrentIndex(self.role_combo.findData(user.role))
        self.field(i18n.tr("role"), self.role_combo)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if not self.is_edit:
            self.field(i18n.tr("password"), self.password_edit)

        ok, _ = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            username=self.username_edit.text().strip(),
            full_name=self.full_name_edit.text().strip(),
            role=self.role_combo.currentData(),
            password=self.password_edit.text(),
        )


class UserManagerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.can_manage = has_permission(current_user.role, Permission.MANAGE_USERS)

        design.refresh()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.table = make_table(
            [
                i18n.tr("username"),
                i18n.tr("full_name"),
                i18n.tr("role"),
                i18n.tr("status"),
            ]
        )
        bar = design.Toolbar()
        bar.spacer()
        # One "Manage" dropdown for every user action, gated on MANAGE_USERS.
        self.manage_btn = design.manage_button([
            (i18n.tr("add"), self._add, "plus"),
            (i18n.tr("edit"), self._edit, "pencil"),
            (i18n.tr("reset_password"), self._reset, "key"),
            (i18n.tr("deactivate"), self._toggle, "lock"),
            None,
            (i18n.tr("delete"), self._delete, "trash", "danger"),
        ], parent=self)
        self.manage_btn.setEnabled(self.can_manage)
        bar.add(self.manage_btn)
        root.addWidget(bar)
        # (make_table already applied design.table_style().)
        root.addWidget(self.table, 1)

        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            users = list(session.scalars(select(User).order_by(User.username)))
            self._ids = [u.id for u in users]
            self._active = [u.is_active for u in users]
            rows = [
                [
                    u.username,
                    u.full_name or "",
                    u.role,
                    i18n.tr("active") if u.is_active else i18n.tr("inactive"),
                ]
                for u in users
            ]
        fill_table(self.table, rows)

    def _selected_row(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return None
        return row

    def _add(self) -> None:
        dialog = UserDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                admin_service.create_user_account(
                    session, username=v["username"], password=v["password"],
                    role=v["role"], full_name=v["full_name"],
                    created_by=self.current_user.id,
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _edit(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        user_id = self._ids[row]
        with SessionLocal() as session:
            user = session.get(User, user_id)
            dialog = UserDialog(user=user, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                admin_service.update_user(
                    session, user_id, role=v["role"], full_name=v["full_name"],
                    created_by=self.current_user.id,
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _reset(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        pwd, ok = QInputDialog.getText(
            self, i18n.tr("reset_password"), i18n.tr("new_password"),
            echo=QLineEdit.EchoMode.Password,
        )
        if not ok or not pwd:
            return
        try:
            with SessionLocal() as session:
                admin_service.reset_password(
                    session, self._ids[row], pwd, created_by=self.current_user.id
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        info_toast(self, i18n.tr("reset_password"), i18n.tr("saved"))

    def _toggle(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        try:
            with SessionLocal() as session:
                admin_service.update_user(
                    session, self._ids[row], is_active=not self._active[row],
                    created_by=self.current_user.id,
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _delete(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if not design.confirm(self, i18n.tr("delete"), i18n.tr("confirm_delete"),
                              danger=True):
            return
        try:
            with SessionLocal() as session:
                admin_service.delete_user(
                    session, self._ids[row], created_by=self.current_user.id
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()
