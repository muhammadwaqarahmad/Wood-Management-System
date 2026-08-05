"""Login — a split-screen sign-in shown as an OVERLAY inside the main window.

The app is a single window from launch to dashboard: the shell (sidebar +
header + skeletons) is always the one window; ``LoginOverlay`` dims it and
floats the branded credential card on top until the user signs in. There is no
separate login window that could open/close/flicker.

``LoginView`` is the branded card + form (reusable widget); ``LoginOverlay``
is the dimming layer that centers it over a parent window.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber import config, i18n
from timber.core.auth import (
    authenticate,
    is_default_admin_password,
    seconds_until_retry,
)
from timber.core.current_user import CurrentUser
from timber.db.engine import SessionLocal
from timber.ui import design, icons, theme

# A warm, misty timber scene: layered treetop silhouettes over a golden-hour
# gradient. Rendered to fill the brand panel (aspect is allowed to stretch).
_BRAND_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 470 560' preserveAspectRatio='none'>
  <defs>
    <linearGradient id='sky' x1='0' y1='0' x2='0' y2='1'>
      <stop offset='0' stop-color='#f4ecda'/>
      <stop offset='0.42' stop-color='#e7d3b1'/>
      <stop offset='0.74' stop-color='#c49a67'/>
      <stop offset='1' stop-color='#7c5731'/>
    </linearGradient>
    <radialGradient id='glow' cx='0.5' cy='0.30' r='0.62'>
      <stop offset='0' stop-color='#fff8ea' stop-opacity='0.9'/>
      <stop offset='1' stop-color='#fff8ea' stop-opacity='0'/>
    </radialGradient>
  </defs>
  <rect width='470' height='560' fill='url(#sky)'/>
  <rect width='470' height='560' fill='url(#glow)'/>
  <path opacity='0.30' fill='#b98f5e'
    d='M0,560 L0,392 L22,412 L40,372 L60,410 L82,368 L104,410 L128,378 L150,356 L172,402
       L196,370 L220,410 L244,364 L268,406 L292,376 L316,410 L340,360 L364,406 L388,376
       L412,410 L436,370 L460,406 L470,388 L470,560 Z'/>
  <path opacity='0.55' fill='#8a6440'
    d='M0,560 L0,440 L26,462 L48,424 L72,464 L96,420 L122,464 L148,430 L172,466 L198,424
       L224,464 L250,428 L276,466 L302,430 L330,466 L356,422 L382,464 L408,432 L434,466
       L460,428 L470,452 L470,560 Z'/>
  <path opacity='0.92' fill='#573c22'
    d='M0,560 L0,494 L30,510 L56,480 L84,512 L112,484 L140,514 L170,486 L198,514 L228,484
       L256,514 L286,488 L316,514 L346,482 L376,514 L404,488 L434,514 L460,486 L470,504 L470,560 Z'/>
</svg>
"""


def _brand_pixmap(w: int, h: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_BRAND_SVG.encode("utf-8")))
    dpr = 2
    pm = QPixmap(w * dpr, h * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, w * dpr, h * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _gold_monogram(text: str, height: int = 108) -> QPixmap:
    """The business initials rendered as a gilded serif monogram."""
    font = QFont("Georgia", 10)
    font.setBold(True)
    font.setPixelSize(int(height * 0.92))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)

    path = QPainterPath()
    path.addText(0, height * 0.82, font, text)
    br = path.boundingRect()

    pad = 10
    dpr = 2
    w = int(br.width() + pad * 2)
    pm = QPixmap(w * dpr, height * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(pad - br.left(), 0)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor("#fbe7ad"))
    grad.setColorAt(0.45, QColor("#dcb761"))
    grad.setColorAt(0.7, QColor("#c79b3f"))
    grad.setColorAt(1.0, QColor("#9c7526"))
    p.fillPath(path, QBrush(grad))
    p.strokePath(path, QColor("#7c5c1f"))
    p.end()
    return pm


def _monogram_text() -> str:
    """Up to 3 Latin initials of the business name for the gilded monogram.
    Derived from the (English) brand name so it follows a rebrand and never
    turns into unrenderable Urdu glyphs in the serif font."""
    words = [w for w in config.APP_NAME.split() if w]
    return "".join(w[0] for w in words[:3]).upper() or "A"


class _BrandPanel(QWidget):
    """Left panel: paints the timber scene behind centered brand content."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("brandPanel")
        self._bg: QPixmap | None = None
        self._bg_size: tuple[int, int] = (0, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 44)
        lay.addStretch(3)

        self.logo = QLabel()
        self.logo.setPixmap(_gold_monogram(_monogram_text(), 112))
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.logo)
        lay.addSpacing(10)

        self.title = QLabel(i18n.tr("app_name"))
        self.title.setObjectName("brandTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        self.tagline = QLabel(i18n.tr("app_tagline"))
        self.tagline.setObjectName("brandTagline")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.tagline)
        lay.addStretch(2)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._bg is None or self._bg_size != (self.width(), self.height()):
            self._bg = _brand_pixmap(self.width(), self.height())
            self._bg_size = (self.width(), self.height())
        painter = QPainter(self)
        # Clip to rounded-left corners so the scene follows the card.
        path = QPainterPath()
        r = self.rect()
        radius = 18
        path.moveTo(r.right(), r.top())
        path.lineTo(r.left() + radius, r.top())
        path.quadTo(r.left(), r.top(), r.left(), r.top() + radius)
        path.lineTo(r.left(), r.bottom() - radius)
        path.quadTo(r.left(), r.bottom(), r.left() + radius, r.bottom())
        path.lineTo(r.right(), r.bottom())
        path.closeSubpath()
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), self._bg)


class LoginView(QFrame):
    """The branded credential card (brand panel + sign-in form) as a plain
    widget. Emits ``authenticated`` with a ``CurrentUser`` on success,
    ``cancelled`` when the user closes it, and ``language_changed`` when the
    language selector changes (the host rebuilds the shell to match)."""

    authenticated = Signal(object)
    cancelled = Signal()
    language_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_user: CurrentUser | None = None

        self.setObjectName("loginCard")
        # Was setFixedSize: on a small laptop the card could not shrink
        # and its edges fell outside the window.
        design.fit_to_screen(self, 884, 588)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(20, 20, 30, 150))
        self.setGraphicsEffect(shadow)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.brand = _BrandPanel()
        self.brand.setFixedWidth(392)
        row.addWidget(self.brand)
        row.addWidget(self._build_form(), 1)

        self.setStyleSheet(_build_style())
        self._retranslate()
        self.username_edit.setFocus()

    # -- form ---------------------------------------------------------
    def _build_form(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("formPanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(46, 40, 46, 40)
        lay.setSpacing(0)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.cancelled.emit)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch()
        top.addWidget(close_btn)
        lay.addLayout(top)

        self.welcome = QLabel(i18n.tr("login"))
        self.welcome.setObjectName("welcome")
        lay.addWidget(self.welcome)
        lay.addSpacing(20)

        # Language
        self.lang_label = QLabel(i18n.tr("language"))
        self.lang_label.setObjectName("fieldLabel")
        lay.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(self.lang_combo.findData(i18n.get_language()))
        self.lang_combo.currentIndexChanged.connect(self._change_language)
        lay.addWidget(self._field("globe", self.lang_combo))
        lay.addSpacing(14)

        # Username
        self.user_label = QLabel(i18n.tr("username"))
        self.user_label.setObjectName("fieldLabel")
        lay.addWidget(self.user_label)
        self.username_edit = QLineEdit()
        lay.addWidget(self._field("user", self.username_edit))
        lay.addSpacing(14)

        # Password
        self.pass_label = QLabel(i18n.tr("password"))
        self.pass_label.setObjectName("fieldLabel")
        lay.addWidget(self.pass_label)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Let the user check what they typed. Most failed logins are typos,
        # and with a lockout in place a typo now has a real cost.
        self._pw_visible = False
        self._pw_toggle = QPushButton()
        self._pw_toggle.setObjectName("pwToggle")
        self._pw_toggle.setFixedSize(28, 28)
        self._pw_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pw_toggle.setIcon(icons.icon("eye", "#9a8467", 17))
        self._pw_toggle.setToolTip(i18n.tr("show_password"))
        self._pw_toggle.clicked.connect(self._toggle_password)
        lay.addWidget(self._field("lock", self.password_edit, self._pw_toggle))
        lay.addSpacing(24)

        self.login_btn = QPushButton(i18n.tr("login"))
        self.login_btn.setObjectName("loginButton")
        self.login_btn.setIcon(icons.icon("key", "#ffffff", 17))
        self.login_btn.setDefault(True)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self._attempt_login)
        lay.addWidget(self.login_btn)
        lay.addSpacing(14)

        links = QHBoxLayout()
        links.setContentsMargins(2, 0, 2, 0)
        self.forgot_link = QPushButton(i18n.tr("forgot_password"))
        self.forgot_link.setObjectName("linkBtn")
        self.forgot_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.request_link = QPushButton(i18n.tr("request_account"))
        self.request_link.setObjectName("linkBtn")
        self.request_link.setCursor(Qt.CursorShape.PointingHandCursor)
        links.addWidget(self.forgot_link)
        links.addStretch()
        links.addWidget(self.request_link)
        lay.addLayout(links)
        lay.addStretch()

        self.username_edit.returnPressed.connect(self._attempt_login)
        self.password_edit.returnPressed.connect(self._attempt_login)
        return panel

    def _field(self, icon_name: str, widget: QWidget, trailing=None) -> QFrame:
        frame = QFrame()
        frame.setObjectName("field")
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(13, 0, 10, 0)
        fl.setSpacing(9)
        ico = QLabel()
        ico.setPixmap(icons.pixmap(icon_name, "#9a8467", 18))
        fl.addWidget(ico)
        widget.setObjectName("fieldInput")
        fl.addWidget(widget, 1)
        if trailing is not None:
            fl.addWidget(trailing)
        return frame

    def _toggle_password(self) -> None:
        self._pw_visible = not self._pw_visible
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if self._pw_visible
            else QLineEdit.EchoMode.Password
        )
        self._pw_toggle.setIcon(
            icons.icon("eye-off" if self._pw_visible else "eye", "#9a8467", 17))
        self._pw_toggle.setToolTip(
            i18n.tr("hide_password" if self._pw_visible else "show_password"))

    def focus_username(self) -> None:
        self.username_edit.setFocus()

    # -- language -----------------------------------------------------
    def _change_language(self) -> None:
        import logging

        i18n.set_language(self.lang_combo.currentData())
        app = QApplication.instance()
        if app is not None:
            app.setLayoutDirection(i18n.layout_direction())
        logging.getLogger("timber").info(
            "Login language -> %s", i18n.get_language()
        )
        # The host rebuilds the shell + this overlay in the new direction.
        self.language_changed.emit()

    def _retranslate(self) -> None:
        self.brand.title.setText(i18n.tr("app_name"))
        self.brand.tagline.setText(i18n.tr("app_tagline"))
        self.welcome.setText(i18n.tr("login"))
        self.lang_label.setText(i18n.tr("language"))
        self.user_label.setText(i18n.tr("username"))
        self.pass_label.setText(i18n.tr("password"))
        self.login_btn.setText("  " + i18n.tr("login"))
        self.forgot_link.setText(i18n.tr("forgot_password"))
        self.request_link.setText(i18n.tr("request_account"))

    # -- auth ---------------------------------------------------------
    def _attempt_login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            design.error(self, i18n.tr("login"), i18n.tr("enter_credentials"))
            return

        import logging
        import time

        # Tell a locked-out user how long to wait instead of repeating
        # "invalid password" at them.
        waiting = seconds_until_retry(username)
        if waiting > 0:
            design.error(
                self, i18n.tr("login"),
                i18n.tr("too_many_attempts").replace("{s}", str(int(waiting) + 1)),
            )
            self.password_edit.clear()
            self.password_edit.setFocus()
            return

        t0 = time.perf_counter()
        with SessionLocal() as session:
            user = authenticate(session, username, password)
            if user is None:
                again = seconds_until_retry(username)
                if again > 0:
                    design.error(
                        self, i18n.tr("login"),
                        i18n.tr("too_many_attempts").replace("{s}", str(int(again) + 1)),
                    )
                else:
                    design.error(self, i18n.tr("login"), i18n.tr("login_invalid"))
                self.password_edit.clear()
                self.password_edit.setFocus()
                return
            self.current_user = CurrentUser.from_user(user)
            # Signing in with the shipped default means anyone who has seen
            # the app can get in. Say so plainly; don't block the login.
            default_pw = is_default_admin_password(user, password)
        if default_pw:
            design.error(
                self, i18n.tr("login"), i18n.tr("default_password_warning")
            )
        logging.getLogger("timber").info(
            "Authentication took %.2fs", time.perf_counter() - t0
        )
        self.authenticated.emit(self.current_user)


class LoginOverlay(QWidget):
    """A dimming layer that fills its parent window and floats a ``LoginView``
    in the centre. Kept as a child of the main window so signing in never
    opens or closes a second window — the shell simply shows through, dimmed.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("loginOverlay")
        # Catch all input so the shell underneath can't be clicked while the
        # login is up (acts modal without a separate modal window).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self.view = LoginView(self)
        self.setGeometry(parent.rect())
        self._recenter()

    def _recenter(self) -> None:
        x = (self.width() - self.view.width()) // 2
        y = (self.height() - self.view.height()) // 2
        self.view.move(max(x, 0), max(y, 0))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._recenter()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Dim the shell behind the card (translucent slate).
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(15, 23, 42, 150))
        p.end()

    def focus(self) -> None:
        self.view.focus_username()


def _build_style() -> str:
    """The sign-in card, built from the ACTIVE palette.

    This used to be a hard-coded light stylesheet with a blue button on a gold
    card — it matched neither the app nor itself, and a dark-theme user got a
    blinding white panel. Colours now come from the same palette every other
    screen uses, so the login follows light/dark and shares the app accent.
    The warm timber brand panel stays: that is the business's identity.
    """
    p = theme.palette()
    dark = theme.get_theme() == "dark"
    surface = p["surface"]
    text = p["text"]
    muted = p["muted"]
    border = p["border"]
    accent = p["accent"]
    accent2 = p["accent2"]
    field_bg = p["input_bg"]
    # The form side sits a touch off the card so the fields read as raised.
    form_bg = p["window"] if dark else "#faf8fc"
    hover = p["menu_hover"]
    return f"""
QFrame#loginCard {{ background: {surface}; border-radius: 18px; }}
QWidget#brandPanel {{ background: transparent; }}
QLabel#brandTitle {{ color: #ffffff; font-size: 26px; font-weight: 800; letter-spacing: 0.5px; }}
QLabel#brandTagline {{ color: rgba(255,255,255,0.85); font-size: 13px; font-style: italic; }}

QFrame#formPanel {{
    background: {form_bg};
    border-top-right-radius: 18px; border-bottom-right-radius: 18px;
}}
QLabel#welcome {{ color: {text}; font-size: 24px; font-weight: 800; }}
QLabel#fieldLabel {{
    color: {muted}; font-size: 11px; font-weight: 700;
    letter-spacing: 0.6px; padding: 0 0 6px 2px;
}}

QFrame#field {{
    background: {field_bg}; border: 1px solid {border};
    border-radius: 11px; min-height: 46px;
}}
QFrame#field:focus-within {{ border: 1px solid {accent}; }}
QLineEdit#fieldInput, QComboBox#fieldInput {{
    border: none; background: transparent; padding: 10px 2px;
    font-size: 14px; color: {text}; min-height: 24px;
}}
QLineEdit#fieldInput::placeholder {{ color: {muted}; }}
QComboBox#fieldInput::drop-down {{ border: none; width: 22px; }}
QComboBox#fieldInput QAbstractItemView {{
    background: {field_bg}; color: {text}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: #ffffff; outline: 0;
}}

QPushButton#loginButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent2}, stop:1 {accent});
    color: #ffffff; border: none; border-radius: 12px; padding: 14px 18px;
    font-size: 15px; font-weight: 800; letter-spacing: 0.3px; min-height: 20px;
}}
QPushButton#loginButton:hover {{ background: {accent}; }}
QPushButton#loginButton:pressed {{ background: {p["primary_pressed"]}; }}

QPushButton#linkBtn {{
    background: transparent; border: none; color: {muted};
    font-size: 12px; font-weight: 600; padding: 2px 4px;
}}
QPushButton#linkBtn:hover {{ color: {accent}; text-decoration: underline; }}

QPushButton#closeBtn {{
    background: transparent; border: none; color: {muted};
    font-size: 15px; font-weight: 700; border-radius: 15px;
}}
QPushButton#closeBtn:hover {{ background: {hover}; color: {text}; }}

/* Reveal/hide button living inside the password field */
QPushButton#pwToggle {{ background: transparent; border: none; border-radius: 14px; }}
QPushButton#pwToggle:hover {{ background: {hover}; }}
"""

