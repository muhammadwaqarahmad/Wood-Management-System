"""Audit log viewer — read-only history of who did what, when."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from timber import i18n
from timber.ui import design, icons
from timber.core.audit import recent_audit
from timber.core.current_user import CurrentUser
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import fill_table, make_table


class AuditLogScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None,
                 on_back=None) -> None:
        super().__init__(parent)
        design.refresh()
        root = QVBoxLayout(self)
        # Side inset, consistent with the other pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        # This page has no sidebar entry (it opens from Settings), so it needs
        # its own way back — otherwise there is no route out of it.
        if on_back is not None:
            back_bar = design.Toolbar()
            self.back_btn = QPushButton(i18n.tr("back_to_settings"))
            self.back_btn.setStyleSheet(design.btn("ghost"))
            self.back_btn.setIcon(icons.icon("chevron-left", design.c("text"), 15))
            self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.back_btn.clicked.connect(lambda: on_back())
            back_bar.add(self.back_btn)
            back_bar.spacer()
            root.addWidget(back_bar)


        self.table = make_table(
            [
                i18n.tr("time"),
                i18n.tr("user"),
                i18n.tr("action"),
                i18n.tr("entity"),
                "ID",
                i18n.tr("details"),
            ]
        )
        root.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows = recent_audit(session)
        fill_table(
            self.table,
            [
                [
                    r.when.strftime("%Y-%m-%d %H:%M"),
                    r.username,
                    r.action,
                    r.entity,
                    str(r.entity_id) if r.entity_id is not None else "",
                    r.details or "",
                ]
                for r in rows
            ],
        )
