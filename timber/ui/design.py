"""The shared design system — one source of truth for how the app looks.

Every page used to carry its own private copy of ``_c`` / ``_btn_style`` /
``_Card``. That is exactly why the pages drifted apart: fixing a colour on the
Dashboard did nothing for Reports. Everything visual now lives here, so a
change lands on every screen at once.

    from timber.ui import design as d

    card = d.Card(d.t("banks"), "wallet")
    btn.setStyleSheet(d.btn("primary"))
    if d.confirm(self, d.t("delete"), d.t("confirm_delete")):
        ...

Call ``d.refresh()`` at the top of a screen's ``__init__`` (or after a theme
change) so the module-level palette matches the active theme.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QScrollArea,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import icons, theme

# ---------------------------------------------------------------- palette ---

_P: dict = {}
_P_THEME: str | None = None      # which theme _P was built for

#: Accent tones for KPI tiles / status chips, vivid in both themes.
TONES = {
    "indigo": "#6366f1", "sky": "#0ea5e9", "emerald": "#10b981",
    "amber": "#f59e0b", "rose": "#f43f5e", "violet": "#8b5cf6",
    "slate": "#64748b",
}

#: Semantic colours. Re-read by refresh() because they differ per theme.
POS, NEG, ZERO = "#059669", "#e11d48", "#64748b"


def refresh() -> None:
    """Re-read the active palette. Call before building widgets."""
    global _P, POS, NEG, ZERO, _P_THEME
    _P = theme.palette()
    _P_THEME = theme.get_theme()
    dark = theme.get_theme() == "dark"
    POS = "#34d399" if dark else "#059669"
    NEG = "#fb7185" if dark else "#e11d48"
    ZERO = _P.get("muted", "#64748b")


def c(key: str) -> str:
    """A colour from the active palette.

    Re-reads whenever the theme has changed since the cache was built. Only
    checking for an EMPTY cache was not enough: after a light/dark switch the
    cache still held the OLD theme's colours, so widgets built afterwards came
    out in the previous theme — a dark toolbar sitting on a light page.
    """
    if not _P or _P_THEME != theme.get_theme():
        refresh()
    return _P.get(key, "#000000")


def t(key: str) -> str:
    """A translated string, falling back to the key so nothing renders blank."""
    r = i18n.tr(key)
    return r if r else key


def is_dark() -> bool:
    return theme.get_theme() == "dark"


def tint(hex_color: str, alpha: int = 30) -> str:
    """Translucent version of a colour — readable on light AND dark cards."""
    q = QColor(hex_color)
    return f"rgba({q.red()},{q.green()},{q.blue()},{alpha})"


def amt_color(v) -> str:
    """Green / red / grey for a signed amount."""
    v = float(v)
    return POS if v > 0 else NEG if v < 0 else ZERO


def money(v, dec: int = 2) -> str:
    return f"{float(v):,.{dec}f}"


def shadow(w: QWidget, blur: int = 18, dy: int = 2, alpha: int | None = None) -> None:
    """The standard soft card shadow."""
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setXOffset(0)
    eff.setYOffset(dy)
    eff.setColor(QColor(15, 23, 42, alpha if alpha is not None else (40 if is_dark() else 24)))
    w.setGraphicsEffect(eff)


# ------------------------------------------------------------------ styles ---

def btn(kind: str = "ghost") -> str:
    """Button QSS. kind: primary | danger | success | ghost | subtle."""
    if kind == "primary":
        return (
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 "
            f"{c('accent2')},stop:1 {c('accent')});color:#fff;border:none;"
            "border-radius:9px;padding:9px 20px;font-weight:800;}"
            f"QPushButton:hover{{background:{c('accent')};}}"
            "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    if kind == "danger":
        return ("QPushButton{background:#e11d48;color:#fff;border:none;"
                "border-radius:9px;padding:9px 20px;font-weight:800;}"
                "QPushButton:hover{background:#be123c;}"
                "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    if kind == "success":
        return ("QPushButton{background:#059669;color:#fff;border:none;"
                "border-radius:9px;padding:9px 20px;font-weight:800;}"
                "QPushButton:hover{background:#047857;}"
                "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    if kind == "subtle":
        return (f"QPushButton{{background:transparent;color:{c('muted')};border:none;"
                "border-radius:9px;padding:8px 14px;font-weight:700;}"
                f"QPushButton:hover{{color:{c('accent')};background:{tint(c('accent'), 26)};}}")
    return (f"QPushButton{{background:{c('surface')};color:{c('text')};"
            f"border:1px solid {c('border')};border-radius:9px;padding:8px 16px;font-weight:700;}}"
            f"QPushButton:hover{{background:{c('tab_bg')};border-color:{c('accent')};}}"
            f"QPushButton:disabled{{color:{c('muted')};}}")


def input_style() -> str:
    """QSS for every kind of input, so forms match across pages."""
    return (
        "QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox,QDateEdit,QPlainTextEdit,QTextEdit{"
        f"background:{c('input_bg')};border:1px solid {c('input_border')};"
        f"border-radius:9px;padding:8px 11px;color:{c('text')};min-height:20px;}}"
        "QComboBox:focus,QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,"
        f"QDateEdit:focus,QPlainTextEdit:focus,QTextEdit:focus{{border:1px solid {c('accent')};}}"
        "QComboBox:hover,QLineEdit:hover,QSpinBox:hover,QDoubleSpinBox:hover,"
        f"QDateEdit:hover{{border-color:{c('accent')};}}"
        "QComboBox::drop-down{border:none;width:22px;}"
        f"QComboBox QAbstractItemView{{background:{c('input_bg')};color:{c('text')};"
        f"border:1px solid {c('border')};border-radius:8px;"
        f"selection-background-color:{c('accent')};selection-color:#ffffff;}}")


def card_style(object_name: str = "dsCard") -> str:
    return ("#" + object_name + "{background:" + c("surface") + ";border:1px solid "
            + c("border") + ";border-radius:16px;}")


def table_style() -> str:
    """Rounded, borderless-feeling table matching the cards."""
    return (
        f"QTableWidget{{background:{c('surface')};border:1px solid {c('border')};"
        f"border-radius:12px;gridline-color:{c('border')};"
        f"alternate-background-color:{c('alt_row')};}}"
        f"QHeaderView::section{{background:{c('th_bg')};color:{c('th_text')};"
        f"padding:11px 9px;border:none;border-bottom:2px solid {c('border')};"
        "font-weight:700;}"
        "QTableWidget::item{padding:8px 7px;}"
        f"QTableWidget::item:selected{{background:{c('sel_row')};color:{c('sel_text')};}}")


# ------------------------------------------------------------------ widgets ---

def field_label(text: str) -> QLabel:
    """Small uppercase caption that sits above an input."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"color:{c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;")
    return lbl


def icon_label(name: str, color: str | None = None, size: int = 18) -> QLabel:
    lbl = QLabel()
    try:
        lbl.setPixmap(icons.pixmap(name, color or c("accent"), size))
    except Exception:  # noqa: BLE001 - a missing icon must never break a page
        pass
    return lbl


class Card(QFrame):
    """Rounded surface panel with an optional icon + title + subtitle.

    The single card used by every page. ``add`` / ``addL`` append to its body.
    """

    def __init__(self, title: str = "", icon_name: str = "", subtitle: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dsCard")
        self.setStyleSheet(card_style())
        shadow(self)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(22, 18, 22, 20)
        self.box.setSpacing(13)

        if title:
            head = QHBoxLayout()
            head.setSpacing(9)
            if icon_name:
                head.addWidget(icon_label(icon_name))
            h = QLabel(title)
            h.setStyleSheet(f"color:{c('text')};font-size:15px;font-weight:800;")
            head.addWidget(h)
            head.addStretch()
            self.head = head
            self.box.addLayout(head)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color:{c('muted')};font-size:12px;")
            self.box.addWidget(sub)

    def add(self, w: QWidget):
        self.box.addWidget(w)
        return w

    def addL(self, lay):
        self.box.addLayout(lay)
        return lay


class Tile(QFrame):
    """KPI card: tinted icon chip + caption + value, accent bar on the edge."""

    def __init__(self, label: str, value: str, icon_name: str = "pie-chart",
                 tone: str = "slate", color: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dsTile")
        accent = TONES.get(tone, TONES["slate"])
        self.setStyleSheet(
            "#dsTile{background:" + c("surface") + ";border:1px solid " + c("border")
            + ";border-radius:16px;border-left:4px solid " + accent + ";}")
        shadow(self, blur=20, dy=3)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 14)
        lay.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(9)
        chip = QLabel()
        chip.setFixedSize(32, 32)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(f"background:{tint(accent, 38)};border-radius:9px;")
        try:
            chip.setPixmap(icons.pixmap(icon_name, accent, 17))
        except Exception:  # noqa: BLE001
            pass
        cap = QLabel(label.upper())
        cap.setStyleSheet(
            f"color:{c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;")
        cap.setWordWrap(True)
        top.addWidget(chip)
        top.addWidget(cap, 1)
        lay.addLayout(top)

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            f"color:{color or c('text')};font-size:21px;font-weight:800;")
        lay.addWidget(self.value_label)


def stat_tile(caption: str, accent: str = "", icon_name: str = "") -> tuple[QFrame, QLabel]:
    """A KPI tile whose value is written later — returns (frame, value_label).

    For pages that kept a running total in a plain QLabel and updated it on
    every refresh. They can keep doing exactly that; the label just lives in a
    tile now instead of floating on the page.
    """
    accent = accent or c("accent")
    frame = QFrame()
    frame.setObjectName("dsTile")
    frame.setStyleSheet(
        "#dsTile{background:" + c("surface") + ";border:1px solid " + c("border")
        + ";border-radius:16px;border-left:4px solid " + accent + ";}")
    shadow(frame, blur=20, dy=3)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 13, 16, 14)
    lay.setSpacing(8)

    top = QHBoxLayout()
    top.setSpacing(9)
    if icon_name:
        chip = QLabel()
        chip.setFixedSize(32, 32)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(f"background:{tint(accent, 38)};border-radius:9px;")
        try:
            chip.setPixmap(icons.pixmap(icon_name, accent, 17))
        except Exception:  # noqa: BLE001
            pass
        top.addWidget(chip)
    cap = QLabel(caption.upper())
    cap.setWordWrap(True)
    cap.setStyleSheet(
        f"color:{c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;")
    top.addWidget(cap, 1)
    lay.addLayout(top)

    value = QLabel("—")
    value.setStyleSheet(f"color:{accent};font-size:21px;font-weight:800;")
    lay.addWidget(value)
    return frame, value


class Toolbar(QFrame):
    """The bar above a table: search / filters on the left, actions on the right.

    Gives every list page the same header instead of a loose row of buttons.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dsToolbar")
        self.setStyleSheet(
            "#dsToolbar{background:" + c("surface") + ";border:1px solid " + c("border")
            + ";border-radius:14px;}")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(14, 10, 14, 10)
        self.row.setSpacing(9)
        self._stretched = False

    def add(self, w: QWidget):
        self.row.addWidget(w)
        return w

    def addL(self, lay):
        self.row.addLayout(lay)
        return lay

    def spacer(self):
        """Everything added after this is right-aligned."""
        if not self._stretched:
            self.row.addStretch()
            self._stretched = True


def toolbar_wrap(layout) -> QFrame:
    """Put an existing filter row inside a toolbar card.

    The ledger and money pages build their filters as a bare QHBoxLayout of
    combos and date pickers floating on the page background. Wrapping keeps
    all that code untouched while giving them the same framed bar the
    redesigned pages have.
    """
    bar = Toolbar()
    bar.row.setContentsMargins(14, 10, 14, 10)
    while bar.row.count():
        bar.row.takeAt(0)
    bar.row.addLayout(layout)
    return bar


def table_card(*widgets) -> QFrame:
    """A surface card holding a search box and/or a table, so lists sit on the
    same panel the Dashboard's charts and tables do."""
    card = QFrame()
    card.setObjectName("dsTableCard")
    card.setStyleSheet(
        "#dsTableCard{background:" + c("surface") + ";border:1px solid " + c("border")
        + ";border-radius:16px;}")
    shadow(card)
    box = QVBoxLayout(card)
    box.setContentsMargins(16, 14, 16, 16)
    box.setSpacing(11)
    for w in widgets:
        if w is None:
            continue
        if isinstance(w, QWidget):
            box.addWidget(w, 1 if w.__class__.__name__.endswith("Table") else 0)
        else:
            box.addLayout(w)
    return card


# ------------------------------------------------------------------ dialogs ---

def fit_to_screen(widget, want_w: int, want_h: int, margin: float = 0.92) -> None:
    """Size a window to what it wants, but never past what the screen has.

    Office PCs and laptops here are not the same size — a 1366x768 laptop has
    roughly 700px of usable height, so a dialog asking for 840 would have its
    buttons pushed off the bottom with no way to reach them. Anything that
    does not fit scrolls instead (see Dialog's scrollable body).
    """
    from PySide6.QtWidgets import QApplication

    screen = QApplication.primaryScreen()
    avail = screen.availableGeometry() if screen else None
    max_w = int(avail.width() * margin) if avail else want_w
    max_h = int(avail.height() * margin) if avail else want_h
    w, h = min(want_w, max_w), min(want_h, max_h)
    widget.resize(w, h)
    # A floor low enough for a small laptop, never larger than what we fit to.
    widget.setMinimumSize(min(640, w), min(420, h))


class Dialog(QDialog):
    """The standard add / edit / confirm box.

    A tinted header strip (icon + title + subtitle), a padded body, and a
    footer whose buttons follow the palette. The native window frame is kept
    deliberately: a frameless dialog would have to re-implement move, focus and
    Alt+F4 by hand, and this box is used every day for real data entry.

        dlg = Dialog(d.t("edit_party"), "user", parent=self)
        dlg.field(d.t("name"), name_edit)
        ok, cancel = dlg.buttons(d.t("save"))
        ok.clicked.connect(dlg.accept)
        if dlg.exec():
            ...
    """

    def __init__(self, title: str, icon_name: str = "", subtitle: str = "",
                 parent=None, width: int = 560, tone: str = "") -> None:
        super().__init__(parent)
        refresh()
        self.setWindowTitle(title)
        # Fitted, not fixed: ask for `width` but accept the screen's limit.
        fit_to_screen(self, width, int(width * 1.15))
        self.setStyleSheet(
            f"QDialog{{background:{c('window')};}}"
            f"QLabel{{color:{c('text')};}}" + input_style())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = TONES.get(tone, "") or c("accent")
        head = QFrame()
        head.setObjectName("dlgHead")
        head.setStyleSheet(
            "#dlgHead{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 "
            + tint(accent, 38) + ",stop:1 " + tint(accent, 14) + ");"
            "border-bottom:1px solid " + c("border") + ";}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(22, 16, 22, 16)
        hl.setSpacing(13)
        if icon_name:
            chip = QLabel()
            chip.setFixedSize(40, 40)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(f"background:{tint(accent, 46)};border-radius:12px;")
            try:
                chip.setPixmap(icons.pixmap(icon_name, accent, 21))
            except Exception:  # noqa: BLE001
                pass
            hl.addWidget(chip)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        ttl = QLabel(title)
        ttl.setStyleSheet(f"color:{c('text')};font-size:16px;font-weight:800;")
        texts.addWidget(ttl)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color:{c('muted')};font-size:12px;")
            texts.addWidget(sub)
        hl.addLayout(texts, 1)
        outer.addWidget(head)

        # The body SCROLLS. On a short screen a tall form would otherwise
        # push the Cancel/Save row off the bottom where it cannot be clicked.
        body_host = QWidget()
        self.body = QVBoxLayout(body_host)
        self.body.setContentsMargins(22, 18, 22, 18)
        self.body.setSpacing(13)
        self._body_scroll = QScrollArea()
        self._body_scroll.setWidgetResizable(True)
        self._body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Scroll sideways rather than CLIP. showEvent grows the dialog to the
        # width its body needs, but that is capped by the screen — on a small
        # laptop a wide form still has to go somewhere, and silently cutting
        # off the right-hand fields (with no scrollbar to reach them) is the
        # one outcome that loses data.
        self._body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        # A QScrollArea paints an OPAQUE viewport of its own. Styling only the
        # QScrollArea leaves that viewport at the system default — which turned
        # every dialog body light grey in dark mode. The viewport and the
        # scrolled widget must both be made transparent so the dialog's own
        # background shows through.
        self._body_scroll.viewport().setAutoFillBackground(False)
        body_host.setAutoFillBackground(False)
        self._body_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea > QWidget > QWidget{background:transparent;}"
        )
        self._body_scroll.setWidget(body_host)
        outer.addWidget(self._body_scroll, 1)

        self._footer = QFrame()
        self._footer.setObjectName("dlgFoot")
        self._footer.setStyleSheet(
            "#dlgFoot{background:" + c("surface") + ";border-top:1px solid "
            + c("border") + ";}")
        self._foot_row = QHBoxLayout(self._footer)
        self._foot_row.setContentsMargins(22, 13, 22, 13)
        self._foot_row.setSpacing(9)
        self._foot_row.addStretch()
        self._footer.hide()
        outer.addWidget(self._footer)

    def showEvent(self, event):  # noqa: N802 - Qt override
        """Shrink to the content the first time we are shown.

        The initial height is derived from the requested WIDTH, because the
        body is empty at construction time — callers add their fields
        afterwards. For a short dialog that left a large empty band above the
        content. Once everything is in, take the height the content actually
        needs (never more than the screen allows).
        """
        super().showEvent(event)
        if getattr(self, "_sized_to_content", False):
            return
        self._sized_to_content = True
        # Measure the SCROLLED widget, not the dialog: the dialog's own
        # sizeHint is small precisely because the body scrolls, so using it
        # would shrink a tall form down and make it scroll needlessly.
        inner = self._body_scroll.widget()
        body_h = inner.sizeHint().height() if inner is not None else 0
        body_w = inner.sizeHint().width() if inner is not None else 0
        chrome = self.height() - self._body_scroll.viewport().height()
        h_chrome = self.width() - self._body_scroll.viewport().width()
        want = body_h + chrome

        # Height SHRINKS to the content; width GROWS to it. A form laid out in
        # one wide row (Record payment, Unknown receipts) needs more than the
        # width its caller guessed, and without this the right-hand fields were
        # simply cut off. Never shrink the width — callers pick it deliberately.
        want_h = want if (want and want < self.height()) else self.height()
        want_w = max(self.width(), body_w + h_chrome)
        if want_h != self.height() or want_w != self.width():
            # Lower the height floor to the content first — fit_to_screen's
            # default floor (meant for laptop screens) would otherwise stop a
            # genuinely short dialog from shrinking past it.
            self.setMinimumHeight(0)
            fit_to_screen(self, want_w, want_h)
            self.setMinimumHeight(min(self.height(), want_h))

    # -- body helpers ---------------------------------------------------
    def add(self, w: QWidget):
        self.body.addWidget(w)
        return w

    def addL(self, lay):
        self.body.addLayout(lay)
        return lay

    def field(self, label: str, widget: QWidget, hint: str = ""):
        """A captioned input stacked vertically — reads better than a QFormLayout
        at dialog width, and keeps long Urdu labels from squeezing the input."""
        box = QVBoxLayout()
        box.setSpacing(5)
        box.addWidget(field_label(label))
        box.addWidget(widget)
        if hint:
            h = QLabel(hint)
            h.setWordWrap(True)
            h.setStyleSheet(f"color:{c('muted')};font-size:11px;")
            box.addWidget(h)
        self.body.addLayout(box)
        return widget

    def separator(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{c('border')};border:none;")
        self.body.addWidget(line)
        return line

    # -- footer ---------------------------------------------------------
    def buttons(self, ok_text: str = "", cancel_text: str = "",
                kind: str = "primary") -> tuple[QPushButton, QPushButton]:
        """Cancel (ghost) + confirm (primary/danger). Returns (ok, cancel)."""
        self._footer.show()
        cancel = QPushButton(cancel_text or t("cancel"))
        cancel.setStyleSheet(btn("ghost"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton(ok_text or t("save"))
        ok.setStyleSheet(btn(kind))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setDefault(True)
        self._foot_row.addWidget(cancel)
        self._foot_row.addWidget(ok)
        return ok, cancel

    def add_button(self, widget: QPushButton):
        self._footer.show()
        self._foot_row.addWidget(widget)
        return widget


def _message(parent, title: str, text: str, icon_name: str, tone: str,
             ok_text: str, cancel_text: str | None, kind: str) -> bool:
    dlg = Dialog(title, icon_name, parent=parent, width=430, tone=tone)
    msg = QLabel(text)
    msg.setWordWrap(True)
    msg.setStyleSheet(f"color:{c('text')};font-size:13px;")
    dlg.add(msg)
    if cancel_text is None:
        ok = QPushButton(ok_text)
        ok.setStyleSheet(btn(kind))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(dlg.accept)
        dlg.add_button(ok)
    else:
        ok, _cancel = dlg.buttons(ok_text, cancel_text, kind)
        ok.clicked.connect(dlg.accept)
    return bool(dlg.exec())


def confirm(parent, title: str, text: str, ok_text: str = "",
            danger: bool = False) -> bool:
    """Yes/no box. Returns True if the user confirmed."""
    return _message(parent, title, text, "alert-triangle" if danger else "help-circle",
                    "rose" if danger else "amber", ok_text or t("yes"),
                    t("no"), "danger" if danger else "primary")


def info(parent, title: str, text: str) -> None:
    _message(parent, title, text, "info", "sky", t("ok") or "OK", None, "primary")


def success(parent, title: str, text: str) -> None:
    _message(parent, title, text, "check-circle", "emerald", t("ok") or "OK", None, "success")


def error(parent, title: str, text: str) -> None:
    _message(parent, title, text, "alert-circle", "rose", t("ok") or "OK", None, "danger")
