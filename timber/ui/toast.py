"""Modern toast notifications — non-blocking, animated cards that slide in
at the top-right and auto-dismiss. Replaces blocking QMessageBox popups for
saved / added / removed / error feedback across every screen.

The ``info_toast`` / ``warn_toast`` / ``err_toast`` helpers take the SAME
``(parent, title, text)`` signature as ``QMessageBox.information`` etc., so
existing call sites swap in with no change. Confirmations (QMessageBox.
question) stay as real blocking dialogs.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from PySide6.QtGui import QColor

from timber.ui import icons

# kind -> (accent colour, icon name)
_KINDS = {
    "success": ("#16a34a", "check"),
    "error": ("#dc2626", "x"),
    "warning": ("#d97706", "alert"),
    "info": ("#2563eb", "info"),
}
_DURATION = {"success": 2600, "info": 2600, "warning": 4200, "error": 4800}
_MARGIN = 18
_GAP = 10


class _Toast(QFrame):
    def __init__(self, host: QWidget, kind: str, text: str) -> None:
        super().__init__(host)
        self._host = host
        color, icon_name = _KINDS.get(kind, _KINDS["info"])
        self.setObjectName("toast")
        self.setFixedWidth(340)
        self.setStyleSheet(
            "QFrame#toast { background: palette(base); border: 1px solid"
            " rgba(148,163,184,0.35); border-radius: 12px; }"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(11)

        badge = QLabel()
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background: {color}; border-radius: 15px;")
        badge.setPixmap(icons.pixmap(icon_name, "#ffffff", 17))
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        msg = QLabel(str(text))
        msg.setWordWrap(True)
        msg.setStyleSheet("color: palette(text); font-size: 13px; font-weight: 600;")
        row.addWidget(msg, 1)

        # A slim coloured accent stripe on the leading edge (painted below).
        self._accent = color
        self.adjustSize()

        self._op = QGraphicsOpacityEffect(self)
        self._op.setOpacity(0.0)
        self.setGraphicsEffect(self._op)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PySide6.QtGui import QPainter

        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._accent))
        p.drawRoundedRect(0, 10, 4, self.height() - 20, 2, 2)
        p.end()

    def appear(self) -> None:
        self.show()
        self.raise_()
        self._fade(0.0, 1.0, 180)

    def dismiss(self) -> None:
        anim = self._fade(self._op.opacity(), 0.0, 220)
        anim.finished.connect(lambda: _dismiss(self._host, self))

    def _fade(self, start: float, end: float, ms: int) -> QPropertyAnimation:
        anim = QPropertyAnimation(self._op, b"opacity", self)
        anim.setDuration(ms)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim  # keep a reference alive
        return anim

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.dismiss()


def _host_window(anchor) -> QWidget | None:
    if isinstance(anchor, QWidget):
        w = anchor.window()
        if w is not None:
            return w
    return QApplication.activeWindow()


def _reposition(win: QWidget) -> None:
    stack = getattr(win, "_toast_stack", [])
    y = _MARGIN + 62  # below the header bar
    for t in stack:
        t.move(win.width() - t.width() - _MARGIN, y)
        y += t.height() + _GAP


def _dismiss(win: QWidget, toast: _Toast) -> None:
    stack = getattr(win, "_toast_stack", None)
    if stack and toast in stack:
        stack.remove(toast)
    toast.deleteLater()
    _reposition(win)


def show_toast(anchor, kind: str, text: str) -> None:
    """Show a toast anchored to ``anchor``'s top-level window."""
    win = _host_window(anchor)
    if win is None or not text:
        return
    stack = getattr(win, "_toast_stack", None)
    if stack is None:
        stack = win._toast_stack = []
    toast = _Toast(win, kind, text)
    stack.append(toast)
    _reposition(win)
    toast.appear()
    QTimer.singleShot(_DURATION.get(kind, 3000), toast.dismiss)


# --- drop-in replacements for QMessageBox.information/warning/critical ------
def info_toast(parent, title, text, *args, **kwargs):
    """QMessageBox.information replacement. A 'select an item' prompt shows as
    neutral info; a real confirmation (saved/exported/…) shows as success."""
    from timber import i18n

    kind = "info" if str(text) == i18n.tr("select_item") else "success"
    show_toast(parent, kind, text)


def warn_toast(parent, title, text, *args, **kwargs):
    show_toast(parent, "warning", text)


def err_toast(parent, title, text, *args, **kwargs):
    show_toast(parent, "error", text)


def success_toast(anchor, text: str) -> None:
    show_toast(anchor, "success", text)
