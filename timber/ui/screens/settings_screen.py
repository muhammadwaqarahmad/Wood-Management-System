"""Settings — appearance (language / theme) and backup & restore.

Native, theme-aware card layout: colours come from the active theme palette and
every label is an i18n key, so the page follows light/dark AND translates. The
behaviour (apply, backup, restore, auto-backup options) is unchanged.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from timber import config, i18n
from timber.core import backup
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.ui import design, icons, theme
from timber.ui.toast import err_toast, info_toast

_P: dict = {}
_P_THEME: str | None = None


def _refresh_palette() -> None:
    global _P, _P_THEME
    _P = theme.palette()
    _P_THEME = theme.get_theme()


def _c(key: str) -> str:
    # Self-healing: a widget can be built before the palette is primed (or
    # after a theme switch). Without this every colour fell back to black,
    # which is invisible on the dark theme.
    if not _P or _P_THEME != theme.get_theme():
        _refresh_palette()
    return _P.get(key, "#000000")


def _t(key: str) -> str:
    r = i18n.tr(key)
    return r if r else key


def _input_style() -> str:
    return (
        f"QComboBox,QSpinBox{{background:{_c('input_bg')};border:1px solid {_c('input_border')};"
        f"border-radius:8px;padding:6px 8px;color:{_c('text')};min-height:20px;}}"
        f"QComboBox:focus,QSpinBox:focus{{border:1px solid {_c('accent')};}}"
        f"QComboBox QAbstractItemView{{background:{_c('input_bg')};color:{_c('text')};"
        f"selection-background-color:{_c('accent')};selection-color:#ffffff;}}"
    )


def _btn_style(kind: str = "ghost") -> str:
    if kind == "primary":
        return (f"QPushButton{{background:{_c('accent')};color:#fff;border:none;border-radius:9px;"
                "padding:9px 20px;font-weight:800;}"
                "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    return (f"QPushButton{{background:{_c('surface')};color:{_c('text')};"
            f"border:1px solid {_c('border')};border-radius:9px;padding:8px 16px;font-weight:700;}}"
            f"QPushButton:hover{{background:{_c('tab_bg')};}}"
            f"QPushButton:disabled{{color:{_c('muted')};}}")


class _Card(QFrame):
    """Rounded panel with an icon + title, matching the other pages."""

    def __init__(self, title: str, icon_name: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("setCard")
        self.setStyleSheet(
            "#setCard{background:" + _c("surface") + ";border:1px solid "
            + _c("border") + ";border-radius:16px;}")
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(18); eff.setXOffset(0); eff.setYOffset(2)
        eff.setColor(QColor(15, 23, 42, 40 if theme.get_theme() == "dark" else 24))
        self.setGraphicsEffect(eff)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(22, 18, 22, 20)
        self.box.setSpacing(14)

        head = QHBoxLayout(); head.setSpacing(9)
        if icon_name:
            ic = QLabel()
            try:
                ic.setPixmap(icons.pixmap(icon_name, _c("accent"), 18))
            except Exception:  # noqa: BLE001
                pass
            head.addWidget(ic)
        h = QLabel(title)
        h.setStyleSheet(f"color:{_c('text')};font-size:15px;font-weight:800;")
        head.addWidget(h); head.addStretch()
        self.box.addLayout(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color:{_c('muted')};font-size:12px;")
            self.box.addWidget(sub)

    def add(self, w):
        self.box.addWidget(w)

    def addL(self, lay):
        self.box.addLayout(lay)


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"color:{_c('muted')};font-size:11px;font-weight:700;letter-spacing:0.5px;")
    return lbl


class SettingsScreen(QWidget):
    def __init__(
        self,
        current_user: CurrentUser,
        on_language_change: Callable[[], None],
        parent=None,
        on_open_audit: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        _refresh_palette()
        self._on_language_change = on_language_change
        self._on_open_audit = on_open_audit
        can_backup = has_permission(current_user.role, Permission.BACKUP_RESTORE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;}")
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(2, 4, 2, 10)
        root.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ---------------- Appearance ----------------
        appearance = _Card(_t("settings"), "settings")
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(6)
        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(_input_style())
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(i18n.get_language()))
        self.theme_combo = QComboBox()
        self.theme_combo.setStyleSheet(_input_style())
        for code, name in theme.THEMES.items():
            self.theme_combo.addItem(_t(code), code)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme.get_theme()))
        grid.addWidget(_field_label(_t("choose_language")), 0, 0)
        grid.addWidget(_field_label(_t("theme")), 0, 1)
        grid.addWidget(self.lang_combo, 1, 0)
        grid.addWidget(self.theme_combo, 1, 1)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1); grid.setColumnStretch(2, 2)
        appearance.addL(grid)
        self.apply_btn = QPushButton(_t("apply"))
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet(_btn_style("primary"))
        self.apply_btn.clicked.connect(self._apply)
        row = QHBoxLayout(); row.addWidget(self.apply_btn); row.addStretch()
        appearance.addL(row)
        root.addWidget(appearance)

        # ---------------- Backup folder ----------------
        folder_card = _Card(_t("backup_folder"), "database", _t("google_backup_hint"))
        frow = QHBoxLayout(); frow.setSpacing(10)
        self.folder_label = QLabel(str(backup.get_backup_dir()))
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet(
            f"background:{_c('tab_bg')};color:{_c('accent')};border-radius:8px;"
            "padding:8px 10px;font-weight:600;")
        self.change_folder_btn = QPushButton(_t("change_folder"))
        self.open_folder_btn = QPushButton(_t("open_folder"))
        for b in (self.change_folder_btn, self.open_folder_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_btn_style())
        self.change_folder_btn.clicked.connect(self._change_folder)
        self.open_folder_btn.clicked.connect(self._open_folder)
        frow.addWidget(self.folder_label, 1)
        frow.addWidget(self.change_folder_btn)
        frow.addWidget(self.open_folder_btn)
        folder_card.addL(frow)
        root.addWidget(folder_card)

        # ---------------- Automatic backups ----------------
        auto = _Card(_t("auto_backup_on_close"), "history")
        agrid = QGridLayout(); agrid.setHorizontalSpacing(18); agrid.setVerticalSpacing(6)
        self.auto_close_check = QCheckBox(_t("auto_backup_on_close_hint"))
        self.auto_close_check.setChecked(backup.get_auto_on_close())
        self.auto_close_check.toggled.connect(backup.set_auto_on_close)
        self.auto_close_check.setStyleSheet(f"color:{_c('text')};")
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 168)
        self.interval_spin.setSuffix(f" {_t('hours_short')}")
        self.interval_spin.setSpecialValueText(_t("off"))
        self.interval_spin.setValue(backup.get_interval_hours())
        self.interval_spin.valueChanged.connect(backup.set_interval_hours)
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(0, 3650)
        self.keep_spin.setSuffix(f" {_t('days_short')}")
        self.keep_spin.setSpecialValueText(_t("keep_forever"))
        self.keep_spin.setValue(backup.get_keep_days())
        self.keep_spin.valueChanged.connect(backup.set_keep_days)
        for s in (self.interval_spin, self.keep_spin):
            s.setStyleSheet(_input_style())
        agrid.addWidget(_field_label(_t("backup_every")), 0, 0)
        agrid.addWidget(_field_label(_t("keep_backups")), 0, 1)
        agrid.addWidget(_field_label(_t("last_backup")), 0, 2)
        agrid.addWidget(self.interval_spin, 1, 0)
        agrid.addWidget(self.keep_spin, 1, 1)
        self.last_backup_label = QLabel("")
        agrid.addWidget(self.last_backup_label, 1, 2)
        for i in range(3):
            agrid.setColumnStretch(i, 1)
        auto.add(self.auto_close_check)
        auto.addL(agrid)
        root.addWidget(auto)

        # ---------------- Backup / restore actions ----------------
        actions = _Card(_t("backup_now"), "file-check")
        arow = QHBoxLayout(); arow.setSpacing(10)
        self.backup_btn = QPushButton(_t("backup_now"))
        self.backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_btn.setStyleSheet(_btn_style("primary"))
        self.backup_btn.clicked.connect(self._backup)
        arow.addWidget(self.backup_btn)
        arow.addStretch()
        actions.addL(arow)

        rrow = QHBoxLayout(); rrow.setSpacing(10)
        self.restore_combo = QComboBox()
        self.restore_combo.setMinimumWidth(260)
        self.restore_combo.setStyleSheet(_input_style())
        self.restore_btn = QPushButton(_t("restore"))
        self.restore_file_btn = QPushButton(_t("restore_from_file"))
        for b in (self.restore_btn, self.restore_file_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_btn_style())
        self.restore_btn.clicked.connect(self._restore_selected)
        self.restore_file_btn.clicked.connect(self._restore)
        rrow.addWidget(self.restore_combo, 1)
        rrow.addWidget(self.restore_btn)
        rrow.addWidget(self.restore_file_btn)
        col = QVBoxLayout(); col.setSpacing(6)
        col.addWidget(_field_label(_t("choose_backup")))
        col.addLayout(rrow)
        actions.addL(col)
        root.addWidget(actions)

        # ---------------- Audit log ----------------
        # Reached from here rather than sitting as its own top-level page.
        audit = _Card(_t("audit_log"), "history", _t("audit_log_hint"))
        arow2 = QHBoxLayout(); arow2.setSpacing(10)
        self.audit_btn = QPushButton(_t("audit_log"))
        self.audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audit_btn.setStyleSheet(_btn_style("primary"))
        self.audit_btn.setIcon(icons.icon("history", "#ffffff", 15))
        self.audit_btn.clicked.connect(
            lambda: self._on_open_audit() if self._on_open_audit else None
        )
        self.audit_btn.setEnabled(self._on_open_audit is not None)
        arow2.addWidget(self.audit_btn)
        arow2.addStretch()
        audit.addL(arow2)
        root.addWidget(audit)

        root.addStretch()

        for w in (self.auto_close_check, self.interval_spin, self.keep_spin,
                  self.backup_btn, self.restore_btn, self.restore_file_btn,
                  self.change_folder_btn):
            w.setEnabled(can_backup)

        self._refresh_backups()

    # -- backup helpers --
    def _human_ago(self, when) -> str:
        from datetime import datetime

        secs = (datetime.now() - when).total_seconds()
        if secs < 60:
            return _t("just_now")
        if secs < 3600:
            return f"{int(secs // 60)} {_t('minutes_ago')}"
        if secs < 86400:
            return f"{int(secs // 3600)} {_t('hours_ago')}"
        return f"{int(secs // 86400)} {_t('days_ago')}"

    def _refresh_backups(self) -> None:
        files = backup.list_backups()
        self.restore_combo.clear()
        for p in files:
            from datetime import datetime

            when = datetime.fromtimestamp(p.stat().st_mtime)
            size_mb = p.stat().st_size / (1024 * 1024)
            self.restore_combo.addItem(
                f"{when:%Y-%m-%d %H:%M}   ({size_mb:.1f} MB)", str(p)
            )
        last = backup.last_backup_time()
        dark = theme.get_theme() == "dark"
        if last is None:
            self.last_backup_label.setText(_t("never"))
            self.last_backup_label.setStyleSheet(
                f"color:{'#fca5a5' if dark else '#c62828'};font-weight:700;")
        else:
            self.last_backup_label.setText(
                f"{last:%Y-%m-%d %H:%M}  ({self._human_ago(last)})"
            )
            self.last_backup_label.setStyleSheet(
                f"color:{'#86efac' if dark else '#2e7d32'};font-weight:700;")

    def _restore_selected(self) -> None:
        path = self.restore_combo.currentData()
        if not path:
            info_toast(self, _t("restore"), _t("no_backups"))
            return
        self._do_restore(path)

    def _change_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _t("choose_backup_folder"), str(backup.get_backup_dir())
        )
        if not path:
            return
        backup.set_backup_dir(path)
        self.folder_label.setText(path)

    def _open_folder(self) -> None:
        folder = backup.get_backup_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _backup(self) -> None:
        try:
            dest = backup.backup_now()
            backup.prune_backups(backup.get_keep_days())
        except Exception as exc:  # noqa: BLE001
            err_toast(self, _t("error"), str(exc))
            return
        self._refresh_backups()
        info_toast(self, _t("backup_done"), str(dest))

    def _restore(self) -> None:
        file_filter = (
            "SQL dump (*.sql)" if config.DB_BACKEND == "postgresql"
            else "DB (*.db)"
        )
        path, _sel = QFileDialog.getOpenFileName(
            self, _t("choose_backup"), str(backup.get_backup_dir()), file_filter,
        )
        if path:
            self._do_restore(path)

    def _do_restore(self, path) -> None:
        if not design.confirm(self, _t("restore"), _t("restore_warning"), danger=True):
            return
        try:
            backup.restore_from(path)
        except Exception as exc:  # noqa: BLE001
            err_toast(self, _t("error"), str(exc))
            return
        info_toast(self, _t("restore_done"), _t("restart_after_restore"))

    def refresh(self) -> None:
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(i18n.get_language()))
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme.get_theme()))
        self._refresh_backups()

    def _apply(self) -> None:
        changed = False
        chosen_lang = self.lang_combo.currentData()
        if chosen_lang != i18n.get_language():
            i18n.set_language(chosen_lang)
            changed = True
        chosen_theme = self.theme_combo.currentData()
        if chosen_theme != theme.get_theme():
            theme.set_theme(chosen_theme)
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(theme.build_stylesheet())
            changed = True
        if changed:
            # Defer the rebuild to the next event-loop tick. It calls
            # MainWindow._build() -> setCentralWidget(), which DELETES the old
            # central widget — i.e. this very Settings screen, while we are
            # still inside its button handler. Returning into a destroyed C++
            # object froze the app on every theme/language change. Deferring
            # lets this slot unwind first, then the rebuild happens safely.
            QTimer.singleShot(0, self._on_language_change)
