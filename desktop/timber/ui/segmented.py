"""A modern segmented control (pill switcher) shared by the pages.

Used for the Master Data sections, the Reports sub-pages and the period
filters, so all three look and behave the same. Theme-aware: the colours come
from the active palette, so it follows light/dark.

    seg = SegmentedControl([("all", "All", ""), ("day", "Today", "")])
    seg.changed.connect(handler)      # emits the key
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from timber.ui import icons, theme


class SegmentedControl(QWidget):
    """Rounded pill switcher. ``items`` is a list of (key, label, icon_name)."""

    changed = Signal(str)

    def __init__(self, items, current=None, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._p = theme.palette()
        self._items = [(k, lbl, (ico if len(t) > 2 else ""))
                       for t in items
                       for (k, lbl, ico) in [(t[0], t[1], t[2] if len(t) > 2 else "")]]
        self._compact = compact
        self._current = current or (self._items[0][0] if self._items else "")
        self._btns: dict[str, QPushButton] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._track = QFrame()
        self._track.setObjectName("segTrack")
        # A hairline border makes the track read as a real inset groove instead
        # of a flat grey bar — that flatness was what made the old strip look
        # like an unfinished heading rather than a control.
        self._track.setStyleSheet(
            "#segTrack{background:" + self._c("tab_bg") + ";border:1px solid "
            + self._c("border") + ";border-radius:"
            + ("12px" if compact else "15px") + ";}")
        row = QHBoxLayout(self._track)
        pad = 3 if compact else 4
        row.setContentsMargins(pad, pad, pad, pad)
        row.setSpacing(pad)

        for key, label, icon_name in self._items:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_name:
                b.setProperty("iconName", icon_name)
            b.clicked.connect(lambda _=False, k=key: self.set_current(k, emit=True))
            self._btns[key] = b
            row.addWidget(b)

        outer.addWidget(self._track)
        outer.addStretch()
        self._restyle()

    # -- palette helper ------------------------------------------------
    def _c(self, key: str) -> str:
        return self._p.get(key, "#000000")

    # -- state ---------------------------------------------------------
    def current(self) -> str:
        return self._current

    def set_current(self, key: str, emit: bool = False) -> None:
        if key not in self._btns:
            return
        changed = key != self._current
        self._current = key
        self._restyle()
        if emit and changed:
            self.changed.emit(key)

    def _tint(self, hex_color: str, alpha: int) -> str:
        c = QColor(hex_color)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"

    def _restyle(self) -> None:
        pad_v, pad_h, fs = (6, 15, 12) if self._compact else (10, 22, 13)
        radius = 9 if self._compact else 11
        accent = self._c("accent")
        accent2 = self._p.get("accent2") or accent
        for key, btn in self._btns.items():
            on = key == self._current
            btn.setChecked(on)
            if on:
                # Gradient fill + an accent-tinted glow, so the selected pill
                # clearly floats above the track instead of just changing hue.
                btn.setStyleSheet(
                    "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 "
                    f"{accent2}, stop:1 {accent});color:#ffffff;border:none;"
                    f"border-radius:{radius}px;padding:{pad_v}px {pad_h}px;"
                    f"font-size:{fs}px;font-weight:800;}}")
                eff = QGraphicsDropShadowEffect(btn)
                eff.setBlurRadius(16); eff.setXOffset(0); eff.setYOffset(3)
                eff.setColor(QColor(*QColor(accent).getRgb()[:3], 110))
                btn.setGraphicsEffect(eff)
            else:
                btn.setGraphicsEffect(None)
                # Hover tints toward the accent rather than plain grey — it
                # previews what selecting will look like.
                btn.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{self._c('muted')};border:none;"
                    f"border-radius:{radius}px;padding:{pad_v}px {pad_h}px;"
                    f"font-size:{fs}px;font-weight:700;}}"
                    f"QPushButton:hover{{color:{accent};"
                    f"background:{self._tint(accent, 26)};}}")
            name = btn.property("iconName")
            if name:
                try:
                    btn.setIcon(icons.icon(name, "#ffffff" if on else self._c("muted"),
                                           14 if self._compact else 16))
                except Exception:  # noqa: BLE001 - a missing icon must not break it
                    pass
