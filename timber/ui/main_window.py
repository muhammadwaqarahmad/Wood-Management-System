"""Main application window: a left nav + stacked screens.

Rebuilds itself when the language changes so every label and the
layout direction update instantly (no restart).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QScrollArea,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from timber import config, i18n
from timber.ui import icons, theme
from timber.core.current_user import CurrentUser
from timber.ui.screens.aging_screen import AgingScreen
from timber.ui.screens.audit_log_screen import AuditLogScreen
from timber.ui.screens.bank_accounts_screen import BankAccountsScreen
from timber.ui.screens.bank_book_screen import BankBookScreen
from timber.ui.screens.cheque_screen import ChequeScreen
from timber.ui.screens.loans_screen import LoansScreen
from timber.ui.screens.dashboard_screen import DashboardScreen
from timber.ui.screens.reports_screen import ReportsScreen
from timber.ui.screens.expenses_screen import ExpensesScreen
from timber.ui.screens.factory_ledger_screen import FactoryLedgerScreen
from timber.ui.screens.factory_split_screen import FactorySplitLedgerScreen
from timber.ui.screens.overdue_screen import OverdueScreen
from timber.ui.screens.party_ledger_screen import PartyLedgerScreen
from timber.ui.screens.party_manager import PartyManagerScreen
from timber.ui.screens.payment_entry import PaymentEntryScreen
from timber.ui.screens.position_screen import PositionScreen
from timber.ui.screens.profit_ledger_screen import ProfitLedgerScreen
from timber.ui.screens.trade_ledger_screen import TradeLedgerScreen
from timber.ui.screens.search_screen import SearchScreen
from timber.ui.screens.settings_screen import SettingsScreen
from timber.ui.screens.buy_sell_screen import BuySellScreen
from timber.ui.screens.trade_history_screen import TradeHistoryScreen
from timber.ui.screens.transfers_screen import TransfersScreen


def _is_editing(widget) -> bool:
    """True while the user has an input focused (typing a name, an amount, a
    date, editing a combo). The live-refresh timer skips these moments so a
    background re-query never freezes mid data-entry."""
    if widget is None:
        return False
    from PySide6.QtWidgets import (
        QAbstractSpinBox,
        QComboBox,
        QDateTimeEdit,
        QLineEdit,
        QPlainTextEdit,
        QTextEdit,
    )

    if isinstance(widget, (QLineEdit, QAbstractSpinBox, QDateTimeEdit,
                           QTextEdit, QPlainTextEdit)):
        return True
    if isinstance(widget, QComboBox) and widget.isEditable():
        return True
    return False


class _ReconnectOverlay(QWidget):
    """A dimming layer with a centred card shown while the database can't be
    reached. It has no buttons — the app keeps retrying in the background and
    removes it automatically once the connection is restored."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("reconnectOverlay")
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        self._card = QFrame(self)
        self._card.setObjectName("reconnectCard")
        self._card.setStyleSheet(
            "QFrame#reconnectCard { background:#ffffff; border-radius:16px; }"
            "QLabel { background: transparent; }"
        )
        box = QVBoxLayout(self._card)
        box.setContentsMargins(34, 28, 34, 28)
        box.setSpacing(10)
        from timber import i18n

        title = QLabel("⚠  " + i18n.tr("db_disconnected_title"))
        title.setStyleSheet("font-size:18px; font-weight:800; color:#b91c1c;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg.setStyleSheet("font-size:13px; color:#334155;")
        self._msg.setMinimumWidth(420)
        spin = QLabel("⟳  " + i18n.tr("db_reconnecting"))
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setStyleSheet("font-size:13px; font-weight:700; color:#4f46e5;")
        box.addWidget(title)
        box.addWidget(self._msg)
        box.addWidget(spin)
        self.setGeometry(parent.rect())
        self._recenter()

    def set_message(self, text: str) -> None:
        self._msg.setText(text)
        self._card.adjustSize()
        self._recenter()

    def _recenter(self) -> None:
        self._card.adjustSize()
        x = (self.width() - self._card.width()) // 2
        y = (self.height() - self._card.height()) // 2
        self._card.move(max(x, 0), max(y, 0))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._recenter()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PySide6.QtGui import QColor, QPainter

        p = QPainter(self)
        p.fillRect(self.rect(), QColor(15, 23, 42, 160))
        p.end()


class _Pending(QWidget):
    """Skeleton placeholder kept in the stack until a page is opened for
    the first time — pages are built lazily so the window appears
    instantly, and the user sees a loading skeleton instead of a blank."""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        from PySide6.QtGui import QColor, QPainter

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        shade = QColor(148, 163, 184, 42)   # translucent slate
        w = self.width()
        p.setBrush(shade)
        # title bar block + a few content rows, like a loading page
        p.drawRoundedRect(24, 24, min(280, int(w * 0.3)), 26, 8, 8)
        y = 78
        for i in range(6):
            width = int(w * (0.86 - (i % 3) * 0.12))
            p.drawRoundedRect(24, y, max(width - 48, 120), 18, 6, 6)
            y += 40
        p.end()


class _UserChip(QFrame):
    """Header profile button: just the avatar. Clicking it opens the account
    menu (name + role, then Account / Logout)."""

    def __init__(self, initials: str, menu: QMenu) -> None:
        super().__init__()
        self.setObjectName("userChip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu = menu

        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(0)
        avatar = QLabel(initials)
        avatar.setObjectName("avatar")
        avatar.setFixedSize(38, 38)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(avatar)

    def set_menu(self, menu: QMenu) -> None:
        self._menu = menu

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._menu.setMinimumWidth(230)
        # Drop the menu below the avatar, right-aligned so it stays on screen.
        x = self.width() - self._menu.sizeHint().width()
        self._menu.exec(self.mapToGlobal(QPoint(min(0, x), self.height() + 8)))


class MainWindow(QMainWindow):
    # Emitted (from a background thread) with the result of a DB reconnect
    # probe; Qt queues it to the UI thread so the probe never blocks the UI.
    _db_probe_result = Signal(bool)

    def __init__(self, current_user: CurrentUser | None = None) -> None:
        super().__init__()
        self._probe_inflight = False
        self._db_probe_result.connect(self._on_probe_result)
        # The window can be created and shown BEFORE anyone signs in: it then
        # renders only the shell (sidebar + header + loading skeletons) so the
        # program appears open the instant it launches, with the login dialog
        # on top. `set_user()` later brings it to life. See timber/app.py.
        self.current_user = current_user
        self._login_overlay = None  # in-window sign-in layer (see show_login)
        self._reconnect_overlay = None  # "database disconnected, retrying" layer
        self.resize(1100, 720)
        self._build()

        # When background translations arrive, re-render the current screen
        # so newly-translated Urdu data replaces the English placeholders.
        if config.TRANSLATE_ENABLED:
            from timber.ui.translation_worker import get_service

            get_service().updated.connect(self._on_translations_updated)

        # Automatic backups: check on a timer whether an interval backup is due.
        from PySide6.QtCore import QTimer

        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(30 * 60 * 1000)  # every 30 minutes
        self._backup_timer.timeout.connect(self._maybe_interval_backup)
        self._backup_timer.start()

        # Live sync: on a shared network database, entries made on ANOTHER PC
        # must appear here on their own. Every few seconds re-query the screen
        # the user is looking at. Safe by design: skipped while a dialog is
        # open, and table scroll/selection is preserved so it never jumps.
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(15000)  # every 15s (was 6s — too aggressive)
        self._live_timer.timeout.connect(self._live_refresh)
        self._live_timer.start()

    def set_user(self, current_user: CurrentUser | None) -> None:
        """Attach (or clear) the signed-in user.

        On LOGIN the shell was already built once at startup, so we don't
        rebuild it — we just light it up (title, account menu, open the
        dashboard). That's what makes signing in instant, with no blank
        'close/reopen' flash. On LOGOUT (``None``) we rebuild back to the
        neutral skeleton so the previous user's screens aren't left behind
        the login card.
        """
        self.current_user = current_user
        if current_user is None:
            self._build()  # logout: clean skeleton
            return
        # Login: light up the already-built shell — no rebuild.
        self.setWindowTitle(f"{i18n.tr('app_name')} — {current_user.display_name}")
        if getattr(self, "_user_chip", None) is not None:
            self._user_chip.set_menu(self._build_user_menu())
        # Land on the Dashboard. Every screen is native now, so opening it
        # creates no web view and the window is never rebuilt — sign-in is smooth.
        first = getattr(self, "_first_item", None)
        if first is not None:
            # Open on the next tick so the shell paints first.
            QTimer.singleShot(0, lambda: self.nav.setCurrentItem(first))

    # -- in-window login ---------------------------------------------
    def show_login(self) -> None:
        """Float the sign-in card over the shell. The window itself never
        opens or closes — the login is just a dimming overlay on top of the
        (skeleton) shell, recreated in the current language each time."""
        from timber.ui.login_dialog import LoginOverlay

        old = self._login_overlay
        if old is not None:
            old.hide()
            old.deleteLater()

        overlay = LoginOverlay(self)
        overlay.view.authenticated.connect(self._on_login_ok)
        overlay.view.cancelled.connect(self._on_login_cancel)
        overlay.view.language_changed.connect(self._on_login_lang)
        self._login_overlay = overlay
        overlay.setGeometry(self.rect())
        overlay.show()
        overlay.raise_()
        overlay.focus()

    def _on_login_ok(self, user: CurrentUser) -> None:
        if self._login_overlay is not None:
            self._login_overlay.hide()
        self.set_user(user)  # morph the shell from skeleton to live

    def _on_login_cancel(self) -> None:
        # User closed the login without signing in — quit the app.
        QApplication.quit()

    def _on_login_lang(self) -> None:
        # Language switched at the login screen: rebuild the (skeleton) shell
        # and recreate the overlay so both mirror LTR<->RTL cleanly.
        self._build()
        self.show_login()

    # (Removed: prime_web_native / prebuild_dashboard. They existed only to
    # absorb QtWebEngine's one-time window rebuild for the old embedded React
    # pages. Every screen is native Qt now, so no web view is ever created and
    # there is nothing to absorb — they were unreachable and still imported
    # QWebEngineView / the embedded web server.)

    # -- database-disconnected overlay -------------------------------
    def show_reconnecting(self, message: str) -> None:
        """Cover the shell with a 'database disconnected — reconnecting…' card.
        Non-modal recovery: it stays up (over login or a live screen) until
        :meth:`hide_reconnecting` is called once the DB is reachable again."""
        if self._reconnect_overlay is None:
            self._reconnect_overlay = _ReconnectOverlay(self)
        self._reconnect_overlay.set_message(message)
        self._reconnect_overlay.setGeometry(self.rect())
        self._reconnect_overlay.show()
        self._reconnect_overlay.raise_()

    def hide_reconnecting(self) -> None:
        if self._reconnect_overlay is not None:
            self._reconnect_overlay.hide()

    def is_reconnecting(self) -> bool:
        return (
            self._reconnect_overlay is not None
            and self._reconnect_overlay.isVisible()
        )

    def enter_reconnect_mode(self, message: str) -> None:
        """A live query hit a dropped database. Show the reconnecting card and
        poll in the background until the connection is back, then clear it and
        refresh the visible screen — the user does nothing, no restart."""
        if self.is_reconnecting():
            return
        self.show_reconnecting(message)
        self._reconnect_poll = QTimer(self)
        self._reconnect_poll.setInterval(4000)
        self._reconnect_poll.timeout.connect(self._poll_reconnect)
        self._reconnect_poll.start()
        self._poll_reconnect()  # probe once right away

    def _poll_reconnect(self) -> None:
        # Probe the DB on a BACKGROUND thread: connect() can block up to
        # connect_timeout while the server is down, and doing that on the UI
        # thread would freeze the reconnecting screen (and the whole app) for
        # seconds at a time. Result comes back via a queued signal.
        if self._probe_inflight:
            return
        self._probe_inflight = True

        def _probe() -> None:
            from timber.db.engine import is_connected, reset_pool

            try:
                reset_pool()  # drop dead sockets so the probe dials fresh
                ok = is_connected()
            except Exception:  # noqa: BLE001 - probe must never crash the thread
                ok = False
            self._db_probe_result.emit(ok)

        import threading

        threading.Thread(
            target=_probe, name="db-reconnect-probe", daemon=True
        ).start()

    def _on_probe_result(self, ok: bool) -> None:
        # Runs on the UI thread (queued from the probe thread).
        self._probe_inflight = False
        if not ok:
            return  # still down — keep the card up, next tick tries again
        poll = getattr(self, "_reconnect_poll", None)
        if poll is not None:
            poll.stop()
        self.hide_reconnecting()
        widget = self._page_of(self.stack.currentWidget())
        if widget is not None and not isinstance(widget, _Pending):
            fn = getattr(widget, "refresh", None)
            if fn is not None:
                try:
                    fn()
                except Exception:  # noqa: BLE001 - recovery must never crash
                    logging.getLogger("timber").exception("Post-reconnect refresh failed")

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if self._login_overlay is not None and self._login_overlay.isVisible():
            self._login_overlay.setGeometry(self.rect())
        if self._reconnect_overlay is not None and self._reconnect_overlay.isVisible():
            self._reconnect_overlay.setGeometry(self.rect())

    def _on_translations_updated(self) -> None:
        if _is_editing(QApplication.focusWidget()):
            return  # don't refresh while the user is entering data
        widget = self._page_of(self.stack.currentWidget())
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()

    def _live_refresh(self) -> None:
        """Re-query the visible screen so other PCs' new data shows up live."""
        if self.is_reconnecting():
            return  # the reconnect poll is already handling recovery
        if QApplication.activeModalWidget() is not None:
            return  # a dialog is open — don't disturb the user
        if not self.isActiveWindow():
            return  # app not in focus — refresh when they come back
        if _is_editing(QApplication.focusWidget()):
            return  # user is typing/selecting — never jank a live entry
        widget = self._page_of(self.stack.currentWidget())
        if widget is None or isinstance(widget, _Pending):
            return
        # Web pages (Dashboard / Reports / Buy & Sell) refresh themselves in
        # the browser layer, so the native timer leaves them alone.
        if getattr(widget, "no_live_refresh", False):
            return
        # Only screens that opt in with a LIGHT live_refresh() (updates just its
        # list) auto-update on the timer. Heavy pages (ledgers, bank) are NOT
        # re-queried every tick — that periodic full rebuild was a visible
        # stutter; they refresh on open and after your own actions instead.
        fn = getattr(widget, "live_refresh", None)
        if fn is None:
            return
        log = logging.getLogger("timber")
        from PySide6.QtWidgets import QTableWidget

        # Preserve each table's scroll + selected row across the refresh.
        tables = widget.findChildren(QTableWidget)
        saved = [
            (t, t.verticalScrollBar().value(), t.currentRow()) for t in tables
        ]
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a live refresh must never crash the UI
            log.exception("Live refresh failed")
            from timber.core.db_health import is_connection_error, unreachable_message

            if is_connection_error(exc):
                self.enter_reconnect_mode(unreachable_message(with_retry_hint=True))
            return
        for t, scroll, row in saved:
            if 0 <= row < t.rowCount():
                t.selectRow(row)
            t.verticalScrollBar().setValue(scroll)

    def _maybe_interval_backup(self) -> None:
        from timber.core import backup

        if backup.interval_backup_due():
            backup.auto_backup()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Back up on exit (best-effort; skip if one was just made).
        from timber.core import backup

        if backup.get_auto_on_close():
            backup.auto_backup(min_gap_minutes=2)
        super().closeEvent(event)
        # The app no longer auto-quits on last-window-closed (that was firing
        # mid-login), so closing THIS window must exit the program explicitly.
        QApplication.quit()

    # -- build / rebuild ---------------------------------------------
    def _build(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setLayoutDirection(i18n.layout_direction())
        if self.current_user is not None:
            self.setWindowTitle(
                f"{i18n.tr('app_name')} — {self.current_user.display_name}"
            )
        else:
            self.setWindowTitle(i18n.tr("app_name"))

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header: a dark brand block (menu toggle + business name) sitting
        # over the sidebar, and a light bar over the content (bell + account
        # chip). The dark block is part of the header and never collapses.
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(70)
        hbar = QHBoxLayout(header)
        hbar.setContentsMargins(0, 0, 0, 0)
        hbar.setSpacing(0)

        brand_box = QFrame()
        brand_box.setObjectName("brandBox")
        brand_box.setFixedWidth(250)  # aligned with the sidebar width
        bb = QHBoxLayout(brand_box)
        bb.setContentsMargins(12, 8, 14, 8)
        bb.setSpacing(8)
        menu_btn = QToolButton()
        menu_btn.setObjectName("menuToggle")
        menu_btn.setIcon(icons.icon("menu", theme.header_icon_color(), 20))
        menu_btn.setIconSize(QSize(20, 20))
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setToolTip(i18n.tr("toggle_menu"))
        menu_btn.clicked.connect(self._toggle_sidebar)
        brand_lbl = QLabel(i18n.tr("app_name"))
        brand_lbl.setObjectName("headerBrand")
        bb.addWidget(menu_btn)
        bb.addSpacing(4)
        bb.addWidget(brand_lbl)
        bb.addStretch()
        self._brand_box = brand_box

        main_box = QFrame()
        main_box.setObjectName("headerMain")
        mb = QHBoxLayout(main_box)
        mb.setContentsMargins(24, 8, 16, 8)
        mb.setSpacing(11)

        bell = QToolButton()
        bell.setObjectName("bell")
        bell.setIcon(icons.icon("bell", theme.header_icon_color(), 19))
        bell.setIconSize(QSize(19, 19))
        bell.setCursor(Qt.CursorShape.PointingHandCursor)

        divider = QFrame()
        divider.setObjectName("headerDivider")
        divider.setFixedSize(1, 30)

        # Header shows only the profile icon; details live in its dropdown.
        chip = _UserChip(self._brand_mark(), self._build_user_menu())
        self._user_chip = chip  # kept so login can refresh the account menu

        mb.addStretch()
        mb.addWidget(bell)
        mb.addWidget(divider)
        mb.addSpacing(2)
        mb.addWidget(chip)

        hbar.addWidget(brand_box)
        hbar.addWidget(main_box, 1)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body)

        # Sidebar: the icon navigation list (dark panel).
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        self._sidebar = sidebar
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        self.nav = QTreeWidget()
        self.nav.setObjectName("nav")
        # Icon slot = glyph + the widest manual indent (see icons._padded).
        self.nav.setIconSize(QSize(19 + icons.NAV_PAD_MAX, 19))
        self.nav.setHeaderHidden(True)
        self.nav.setRootIsDecorated(False)  # we draw our own chevrons
        # No branch strip at all — Qt paints selections on it and no QSS
        # reliably stops that. Depth is shown by padding the item icons.
        self.nav.setIndentation(0)
        # Qt paints the row's selection into the indent strip as a separate
        # rounded box (PE_PanelItemViewRow). Suppress that primitive so the
        # gradient pill is the ONLY thing painted for a selected row.
        from PySide6.QtWidgets import QProxyStyle, QStyle

        class _NoRowPanel(QProxyStyle):
            def drawPrimitive(self, element, option, painter, widget=None):
                if element == QStyle.PrimitiveElement.PE_PanelItemViewRow:
                    return
                super().drawPrimitive(element, option, painter, widget)

        self._nav_style = _NoRowPanel()
        self.nav.setStyle(self._nav_style)
        sv.addWidget(self.nav, 1)
        body.addWidget(sidebar)

        # Content area: a full-width page bar (title + export) in the gap,
        # then the floating content "panel" below it.
        content_wrap = QWidget()
        wrap_layout = QVBoxLayout(content_wrap)
        # Tight, even gutter around the floating panel; the page bar sits just
        # under the header and close to the panel (was a wide, uneven band).
        wrap_layout.setContentsMargins(16, 8, 16, 14)
        wrap_layout.setSpacing(8)

        page_bar = QFrame()
        page_bar.setObjectName("pageBar")
        # A guaranteed height so the 23px title can never be clipped, plus real
        # padding — with 0 top/bottom it sat crushed against the header.
        page_bar.setMinimumHeight(48)
        pbl = QHBoxLayout(page_bar)
        # Left inset matches the panel's content inset so the title lines up
        # with the cards below it; right inset small so export hugs the edge.
        pbl.setContentsMargins(6, 4, 6, 4)
        pbl.setSpacing(10)
        self._page_title = QLabel("")
        self._page_title.setObjectName("pageTitle")
        self._exp_pdf = QPushButton(i18n.tr("export_pdf"))
        self._exp_pdf.setObjectName("toolBtn")
        self._exp_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exp_pdf.clicked.connect(lambda: self._export_current("pdf"))
        self._exp_xls = QPushButton(i18n.tr("export_excel"))
        self._exp_xls.setObjectName("toolBtn")
        self._exp_xls.setCursor(Qt.CursorShape.PointingHandCursor)
        self._exp_xls.clicked.connect(lambda: self._export_current("xlsx"))
        self._cur_builder = None
        self._cur_name = "report"
        pbl.addWidget(self._page_title)
        pbl.addStretch()
        pbl.addWidget(self._exp_pdf)
        pbl.addWidget(self._exp_xls)
        wrap_layout.addWidget(page_bar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        wrap_layout.addWidget(self.stack, 1)
        body.addWidget(content_wrap, stretch=1)

        # Screen factories read ``self.current_user`` when the page is first
        # opened (post-login), so the shell is built ONCE (at startup) and
        # login just lights it up — no second full rebuild, no blank flash.
        self._nav_icon_colors = theme.sidebar_icon_colors()
        self._factories = {}

        # Screens are registered as FACTORIES and built lazily on first
        # open — login shows the window with only the dashboard built.
        self._add_header(i18n.tr("nav_dashboard"))
        first = self._add_screen(
            i18n.tr("dashboard"), lambda: DashboardScreen(self.current_user), "dashboard"
        )
        self._add_screen(i18n.tr("reports"), lambda: ReportsScreen(self.current_user), "pie-chart")

        self._add_header(i18n.tr("nav_entry"))
        self._add_screen(i18n.tr("trade"), lambda: BuySellScreen(self.current_user), "cart")
        self._add_screen(i18n.tr("trades"), lambda: TradeHistoryScreen(self.current_user), "receipt")
        self._add_screen(i18n.tr("payment"), lambda: PaymentEntryScreen(self.current_user), "wallet")
        self._add_screen(i18n.tr("search"), lambda: SearchScreen(self.current_user), "search")

        self._add_header(i18n.tr("nav_money"))
        banks = self._add_screen(
            i18n.tr("bank_accounts"), lambda: BankAccountsScreen(self.current_user), "landmark"
        )
        # Bank Book is a subpage of Bank Accounts.
        self._add_screen(
            i18n.tr("bank_book"), lambda: BankBookScreen(self.current_user), "book-open",
            parent=banks,
        )
        self._add_screen(i18n.tr("transfers"), lambda: TransfersScreen(self.current_user), "transfer")
        self._add_screen(i18n.tr("expenses"), lambda: ExpensesScreen(self.current_user), "trending-down")
        self._add_screen(i18n.tr("cheques"), lambda: ChequeScreen(self.current_user), "file-check")
        self._add_screen(i18n.tr("loans"), lambda: LoansScreen(self.current_user), "hand-coins")

        self._add_header(i18n.tr("nav_ledgers"))
        # Financial Position is a NATIVE screen — it's the post-login landing so
        # signing in never creates a web view (no window rebuild / no flicker).
        self._landing_item = self._add_screen(
            i18n.tr("financial_position"), lambda: PositionScreen(self.current_user), "pie-chart"
        )
        self._add_screen(
            i18n.tr("party_ledger"), lambda: PartyLedgerScreen(self.current_user), "book-user"
        )
        fled = self._add_screen(
            i18n.tr("factory_ledger"), lambda: FactoryLedgerScreen(self.current_user), "factory"
        )
        # The split sub-ledger is a subpage of the Factory Ledger. It now holds
        # BOTH the detailed ledger and the weekly settlement (a view toggle).
        self._add_screen(
            i18n.tr("factory_sub_ledger"), lambda: FactorySplitLedgerScreen(self.current_user),
            "book-text", parent=fled,
        )
        self._add_screen(
            i18n.tr("trade_ledger"), lambda: TradeLedgerScreen(self.current_user), "book-text"
        )
        self._add_screen(
            i18n.tr("profit_ledger"), lambda: ProfitLedgerScreen(self.current_user), "trending-up"
        )
        self._add_screen(
            i18n.tr("overdue_report"), lambda: OverdueScreen(self.current_user), "alarm-clock"
        )
        self._add_screen(i18n.tr("aging"), lambda: AgingScreen(self.current_user), "calendar-clock")

        self._add_header(i18n.tr("nav_manage"))
        self._add_screen(
            i18n.tr("master_data"), lambda: PartyManagerScreen(self.current_user), "database"
        )

        self._add_header(i18n.tr("nav_settings"))
        self._settings_item = self._add_screen(
            i18n.tr("settings"),
            lambda: SettingsScreen(
                self.current_user,
                on_language_change=self._rebuild,
                on_open_audit=self._open_audit_log,
            ),
            "settings",
        )
        # The audit log has NO sidebar entry — it is reached only from the
        # Settings page. The page is still registered in the stack so it can
        # be shown; it simply has no nav item to click.
        self._audit_idx = self._register_page(
            lambda: AuditLogScreen(
                self.current_user, on_back=self._open_settings
            )
        )

        # Section headers stay open so the nav reads as a list. A page that
        # owns subpages (Factory Ledger, Settings) starts CLOSED and toggles
        # on click, exactly like a section — its subpages are no longer
        # permanently pinned open.
        self.nav.expandAll()
        for i in range(self.nav.topLevelItemCount()):
            section = self.nav.topLevelItem(i)
            for j in range(section.childCount()):
                page = section.child(j)
                if page.childCount():
                    page.setExpanded(False)
        self.nav.currentItemChanged.connect(self._on_nav_changed)
        self.nav.itemClicked.connect(self._on_nav_clicked)
        self.nav.itemExpanded.connect(self._update_chevron)
        self.nav.itemCollapsed.connect(self._update_chevron)
        # Every item with subpages gets a right-side open/close chevron.
        def _attach_all(item) -> None:
            if item.childCount():
                self._attach_chevron(item)
            for i in range(item.childCount()):
                _attach_all(item.child(i))
        for i in range(self.nav.topLevelItemCount()):
            _attach_all(self.nav.topLevelItem(i))
        # Select the first page AFTER the window has painted, so the shell
        # (sidebar + header + skeleton) appears instantly on login and the
        # dashboard loads visibly right after — no dead "did it crash?" gap.
        # Before anyone signs in (no user) we leave every page as a skeleton:
        # the screens need the current user, and none is built until login.
        from PySide6.QtCore import QTimer

        self._first_item = first
        if self.current_user is not None:
            QTimer.singleShot(50, lambda: self.nav.setCurrentItem(self._first_item))

        # Restore the remembered sidebar state (shown by default).
        from timber.core import app_settings

        if app_settings.get("sidebar_visible", "1") != "1":
            self._apply_sidebar(False)

        self.setCentralWidget(central)

    def _toggle_sidebar(self) -> None:
        from timber.core import app_settings

        show = not self._sidebar.isVisible()
        self._apply_sidebar(show)
        app_settings.set("sidebar_visible", "1" if show else "0")

    def _apply_sidebar(self, show: bool) -> None:
        """Show/hide the nav sidebar. The header's dark brand block (menu
        button + business name) stays exactly as it is either way."""
        self._sidebar.setVisible(show)

    def _rebuild(self) -> None:
        """Re-create everything in the (possibly new) language."""
        import logging
        import time

        t0 = time.perf_counter()
        self._build()
        logging.getLogger("timber").info(
            "Window rebuild (language/theme) took %.2fs", time.perf_counter() - t0
        )

    def _brand_mark(self) -> str:
        """Up to 3 initials of the business name for the sidebar logo badge."""
        words = [w for w in i18n.tr("app_name").split() if w]
        return "".join(w[0] for w in words[:3]).upper() or "A"

    def _initials(self) -> str:
        name = (self.current_user.display_name or "").strip()
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def _role_label(self) -> str:
        if self.current_user is None:
            return ""
        role = (self.current_user.role or "").lower()
        return {
            "admin": "Administrator",
            "manager": "Manager",
            "viewer": "Viewer",
        }.get(role, (self.current_user.role or "").title())

    def _chip_name(self) -> str:
        """Business name + the signed-in user, e.g. 'Abdul Sattar Woods | Administrator'."""
        if self.current_user is None:
            return i18n.tr("app_name")
        return f"{i18n.tr('app_name')} | {self.current_user.display_name}"

    def _build_user_menu(self) -> QMenu:
        """The dropdown from the header chip: who's logged in, then actions."""
        menu = QMenu(self)
        menu.setObjectName("userMenu")

        # Header row: avatar + business name + the signed-in user's role.
        header = QWidget()
        header.setObjectName("menuHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 22, 10)
        hl.setSpacing(10)
        av = QLabel(self._brand_mark())
        av.setObjectName("avatar")
        av.setFixedSize(38, 38)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        name = QLabel(self._chip_name())
        name.setObjectName("menuName")
        role = QLabel(self._role_label())
        role.setObjectName("menuRole")
        col.addWidget(name)
        col.addWidget(role)
        hl.addWidget(av)
        hl.addLayout(col)
        header_action = QWidgetAction(menu)
        header_action.setDefaultWidget(header)
        header_action.setEnabled(False)
        menu.addAction(header_action)
        menu.addSeparator()

        account = QAction(icons.icon("user", "#64748b", 16), i18n.tr("account"), self)
        account.triggered.connect(self._open_account)
        logout = QAction(icons.icon("logout", "#e11d48", 16), i18n.tr("logout"), self)
        logout.triggered.connect(self._logout)
        menu.addAction(account)
        menu.addSeparator()
        menu.addAction(logout)
        return menu

    def _open_account(self) -> None:
        item = getattr(self, "_settings_item", None)
        if item is not None:
            self.nav.setCurrentItem(item)

    def _logout(self) -> None:
        # Don't close the window — drop the shell back to its skeleton and
        # bring the login overlay back up on the SAME window.
        self.set_user(None)
        self.show_login()

    # -- nav ----------------------------------------------------------
    def _on_nav_changed(self, current, previous=None) -> None:
        if current is None:
            return
        idx = current.data(0, Qt.ItemDataRole.UserRole)
        if idx is None or idx < 0:
            return  # a section toggle, not a page
        widget, just_built = self._ensure_built(idx)
        if widget is None:
            return
        self.stack.setCurrentIndex(idx)
        label = current.text(0)
        self._page_title.setText(label)
        self._sync_page_bar(widget, label)
        if just_built:
            return  # its constructor already loaded fresh data — don't re-query
        # An already-built page: reload its data a beat later, and only if it is
        # still the page on screen. So flipping quickly through pages doesn't run
        # a heavy query for every one you pass — only the one you land on.
        self._pending_nav_idx = idx
        QTimer.singleShot(80, self._refresh_current_nav)

    def _refresh_current_nav(self) -> None:
        idx = getattr(self, "_pending_nav_idx", None)
        if idx is None or self.stack.currentIndex() != idx:
            return  # user moved on before this fired
        if _is_editing(QApplication.focusWidget()):
            return
        widget = self._page_of(self.stack.widget(idx))
        if widget is None:
            return
        # Web pages (Dashboard / Reports / Buy & Sell) keep themselves current
        # in the browser — calling refresh() there RELOADS all of Chromium,
        # which is slow and flashes. Just show the already-loaded view.
        if getattr(widget, "no_live_refresh", False):
            return
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _on_nav_clicked(self, item, column: int) -> None:
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        # Re-clicking the row that is ALREADY selected fires no selection
        # change, so a page opened from inside another page (the Audit Log)
        # could not be escaped by clicking its parent in the sidebar.
        if isinstance(idx, int) and idx >= 0 and self.stack.currentIndex() != idx:
            self._on_nav_changed(item, None)
        if idx is None or idx < 0:
            item.setExpanded(not item.isExpanded())  # sections toggle on click
        elif item.childCount():
            # A page that owns subpages behaves the same way: the click still
            # opens the page (handled by the selection change) AND folds its
            # children away, so they can be hidden like any other group.
            item.setExpanded(not item.isExpanded())

    def _attach_chevron(self, item) -> None:
        """Overlay a right-aligned open/close chevron on a parent row. The
        overlay ignores the mouse, so clicks still select/toggle the item."""
        overlay = QWidget()
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(overlay)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.addStretch()
        chev = QLabel()
        chev.setStyleSheet("background: transparent;")
        lay.addWidget(chev)
        self.nav.setItemWidget(item, 0, overlay)
        item._chevron = chev
        self._update_chevron(item)

    def _update_chevron(self, item) -> None:
        chev = getattr(item, "_chevron", None)
        if chev is None:
            return
        closed = (
            "chevron-left"
            if i18n.layout_direction() == Qt.LayoutDirection.RightToLeft
            else "chevron-right"
        )
        name = "chevron-down" if item.isExpanded() else closed
        chev.setPixmap(icons.pixmap(name, "#8296b8", 14))

    def _sync_page_bar(self, widget: QWidget, label: str) -> None:
        """Move the screen's own title + export into the shared page bar: hide
        the in-card title, show the toolbar's export wired to this screen."""
        if not getattr(widget, "_chrome_stripped", False):
            for lbl in widget.findChildren(QLabel):
                ss = lbl.styleSheet() or ""
                if lbl.text() == label and ss.startswith("font-size: 20px; font-weight: bold;"):
                    lbl.hide()
            widget._chrome_stripped = True

        builder = getattr(widget, "_report_builder", None)
        multi = getattr(widget, "_report_multi", False)
        single = builder is not None and not multi
        # A single-report screen: the toolbar drives it, hide the in-card copies.
        for btn in getattr(widget, "_export_btns", []):
            btn.setVisible(not single)
        self._cur_builder = builder if single else None
        self._cur_name = getattr(widget, "_report_name", "report")
        self._exp_pdf.setVisible(single)
        self._exp_xls.setVisible(single)

    def _export_current(self, fmt: str) -> None:
        if self._cur_builder is None:
            return
        from timber.ui.screens.export_helpers import run_export

        run_export(self, self._cur_builder, self._cur_name, fmt)

    def _open_settings(self) -> None:
        """Return to the Settings page (from the Audit Log's Back button)."""
        item = getattr(self, "_settings_item", None)
        if item is None:
            return
        if self.nav.currentItem() is item:
            # Already the selected row, so selecting it fires no signal —
            # switch the stack directly.
            self._on_nav_changed(item, None)
        else:
            self.nav.setCurrentItem(item)

    def _register_page(self, factory) -> int:
        """Add a lazily-built page to the stack WITHOUT a sidebar entry.

        Returns its stack index. Used for pages that are opened from inside
        another page rather than from the nav.
        """
        idx = self.stack.addWidget(_Pending())
        self._factories[idx] = factory
        return idx

    def _open_audit_log(self) -> None:
        """Show the Audit Log (the button on the Settings page)."""
        idx = getattr(self, "_audit_idx", None)
        if idx is None:
            return
        page, _just_built = self._ensure_built(idx)
        if page is None:
            return
        self.stack.setCurrentIndex(idx)
        label = i18n.tr("audit_log")
        self._page_title.setText(label)
        self._sync_page_bar(page, label)

    def _add_screen(
        self, label: str, factory, icon_name: str = "", parent=None
    ) -> QTreeWidgetItem:
        """Register a page under ``parent`` (another page item) or the
        current section. ``factory`` is a zero-arg callable that builds the
        screen — pages are built LAZILY on first open, so login and
        language/theme switches don't pay for all ~20 screens at once."""
        idx = self.stack.addWidget(_Pending())
        self._factories[idx] = factory
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, idx)
        if icon_name:
            normal, selected = self._nav_icon_colors
            # Indentation lives in the icon (16px per level) — the tree's
            # own branch strip is disabled.
            pad = 12 if parent is None else 28
            item.setIcon(0, icons.nav_icon(icon_name, normal, selected, pad=pad))
        (parent if parent is not None else self._section).addChild(item)
        return item

    @staticmethod
    def _page_of(widget):
        """The real page behind a scroll wrapper (or the widget itself)."""
        return getattr(widget, "_scrolled_page", widget)

    def _wrap_scrollable(self, page: QWidget) -> QWidget:
        """Put a page inside a scroll area unless it already has one.

        Most screens had NO scroll area: on a window shorter than their
        content the bottom was simply unreachable. Pages that already manage
        their own scrolling (Dashboard, Buy & Sell, Payment, Settings) are
        left alone so they are not nested inside a second one.
        """
        for child in page.findChildren(QScrollArea):
            # Only a scroll area that spans the page counts as "its own".
            if child.parentWidget() is page:
                return page

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.viewport().setAutoFillBackground(False)
        page.setAutoFillBackground(False)
        area.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea > QWidget > QWidget{background:transparent;}"
        )
        area.setWidget(page)
        area._scrolled_page = page       # so refresh()/export find the page
        return area

    def _ensure_built(self, idx: int) -> tuple[QWidget, bool]:
        """Build the page at ``idx`` on first use (swap out the placeholder).
        Returns ``(widget, just_built)`` — ``just_built`` is True only on the
        first build, whose constructor already loaded the page's data (so the
        caller can skip an immediate, redundant refresh)."""
        widget = self.stack.widget(idx)
        if isinstance(widget, _Pending):
            real = self._factories[idx]()
            holder = self._wrap_scrollable(real)
            self.stack.removeWidget(widget)
            widget.deleteLater()
            self.stack.insertWidget(idx, holder)
            return real, True
        return self._page_of(widget), False

    def _add_header(self, label: str) -> QTreeWidgetItem:
        """A collapsible section (not a page itself)."""
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, -1)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # clickable toggle, never selected
        # Small-caps with letter spacing reads as a group label rather than
        # another nav row. The colour comes from the palette's
        # ``sidebar_section`` slot, which was defined but never used — the
        # header was hard-coded to one shade for both themes.
        font = item.font(0)
        font.setBold(True)
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.0))
        font.setCapitalization(QFont.Capitalization.AllUppercase)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
        item.setFont(0, font)
        item.setForeground(
            0, QBrush(QColor(theme.palette().get("sidebar_section", "#93a4c3")))
        )
        self.nav.addTopLevelItem(item)
        self._section = item
        return item
