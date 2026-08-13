"""Application entry point: startup init -> login -> main window."""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from timber import __version__, config, i18n
from timber.core.logging_setup import setup_logging
from timber.db.engine import SessionLocal
from timber.db.init_db import upgrade_to_head
from timber.db.seed import ensure_admin
from timber.ui import theme
from timber.ui.main_window import MainWindow

log = logging.getLogger("timber")

_LOCK = None  # single-instance lock; held for the process lifetime
_MAIN_WINDOW = None  # the one window, so the excepthook can drive reconnect mode


def _startup_init() -> None:
    """Make the app self-initialising: migrate the DB, ensure an admin and
    the Cash account exist, and (on a brand-new database) load the client's
    suppliers/factories/accounts. Tolerant of a concurrent first run."""
    import time as _t

    from sqlalchemy.exc import IntegrityError

    _s0 = _t.perf_counter()

    def _dbstep(name: str) -> None:
        log.info("  DBINIT %-20s %6.2fs", name, _t.perf_counter() - _s0)
        for _h in log.handlers:
            _h.flush()

    _dbstep("ENTERED _startup_init")
    upgrade_to_head()
    _dbstep("upgrade_to_head")
    with SessionLocal() as session:
        try:
            ensure_admin(session)
            _dbstep("ensure_admin")
            from timber.db.seed_master import (
                ensure_master_data,
                ensure_unknown_parties,
            )

            # Also get-or-creates the "Cash" account.
            created = ensure_master_data(session)
            ensure_unknown_parties(session)  # Unknown supplier/factory placeholders
            if any(created.values()):
                log.info("Seeded master data: %s", created)
            session.commit()
            _dbstep("ensure_master_data")
        except IntegrityError:
            # Another instance seeded the same rows at the same time — fine.
            session.rollback()

        # Housekeeping: keep only the last N days of audit log (config
        # AUDIT_RETENTION_DAYS, default 3). Runs on every launch — with the PCs
        # off at night that means a daily prune. Best-effort; never blocks.
        try:
            from timber.core.audit import prune_audit_log

            removed = prune_audit_log(session)
            if removed:
                log.info("Pruned %d old audit-log entries", removed)
            session.commit()
            _dbstep("prune_audit_log")
        except Exception:  # noqa: BLE001 - housekeeping must never block startup
            session.rollback()
            log.exception("Audit-log prune failed")

        # One-time: recompute FIFO allocations so any data created before the
        # opening-balance fix shows the correct paid/unpaid status.
        try:
            from timber.core import app_settings

            if not app_settings.get("realloc_opening_v1"):
                from sqlalchemy import select as _select

                from timber.core.payment_service import reallocate_party
                from timber.db.models import Party

                for pid in list(session.scalars(_select(Party.id))):
                    reallocate_party(session, pid)
                session.commit()
                app_settings.set("realloc_opening_v1", True)
            _dbstep("realloc check")
        except Exception:  # noqa: BLE001 - maintenance step, never block startup
            session.rollback()
            log.exception("Could not recompute allocations")

        # Warm the translation cache so Urdu data shows instantly.
        try:
            from timber.core import translate

            translate.load_cache(session)
            _dbstep("translate.load_cache")
        except Exception:  # noqa: BLE001 - translation is non-critical
            log.exception("Could not load translation cache")


from timber.core.db_health import is_connection_error as _is_db_connection_error
from timber.core.db_health import unreachable_message as _db_unreachable_message


def _show_db_error(exc: Exception) -> None:
    """Explain a startup DB failure in plain language.

    The overwhelmingly common cause on a client PC is 'server off' or 'wrong
    Wi-Fi', so say exactly that instead of dumping a driver traceback.
    """
    if _is_db_connection_error(exc):
        msg = _db_unreachable_message()
    else:
        msg = f"{i18n.tr('db_init_failed')}:\n{exc}"
    QMessageBox.critical(None, i18n.tr("error"), msg)


def _install_excepthook() -> None:
    """Log uncaught exceptions and show a dialog instead of crashing. A dropped
    database connection puts the window into its 'reconnecting…' mode, which
    keeps retrying in the background and clears itself the moment the server is
    reachable again — no dialog to dismiss, no restart. Anything else shows the
    generic error."""

    def hook(exc_type, exc, tb):
        log.exception("Uncaught exception", exc_info=(exc_type, exc, tb))
        try:
            if _is_db_connection_error(exc):
                if _MAIN_WINDOW is not None:
                    _MAIN_WINDOW.enter_reconnect_mode(
                        _db_unreachable_message(with_retry_hint=True)
                    )
                else:
                    QMessageBox.warning(
                        None, i18n.tr("error"),
                        _db_unreachable_message(with_retry_hint=True),
                    )
            else:
                QMessageBox.critical(
                    None, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
                )
        except Exception:  # noqa: BLE001 - never let the handler itself crash
            pass

    sys.excepthook = hook


def _prewarm_db_async() -> None:
    """Open a database connection in the background so the first screen doesn't
    pay for it on the UI thread — on a cloud database the first connect costs a
    ~2-4s TLS handshake.

    NOTE: this used to also start the embedded uvicorn/FastAPI web server for
    the old React pages. Every screen is native now, so nothing ever talked to
    that server — starting it just burned seconds of startup, a thread and
    memory on every launch. Removed.
    """
    import threading

    def _run() -> None:
        try:
            from timber.db.engine import warm_pool

            warm_pool()
        except Exception:  # noqa: BLE001 - best effort
            log.exception("DB pool warm failed")

    threading.Thread(target=_run, name="prewarm-db", daemon=True).start()


# (Removed: _warm_web_engine. It pre-spun Chromium for the old embedded React
# pages. Every screen is native Qt now, so QtWebEngine is never loaded at all —
# the function had no call sites left.)


def main() -> int:
    setup_logging()
    log.info("Starting %s v%s", config.APP_NAME, __version__)
    import time as _t

    _t0 = _t.perf_counter()

    def _step(name: str) -> None:
        log.info("STARTUP %-22s %6.2fs", name, _t.perf_counter() - _t0)

    # Keep QtWebEngine (Chromium) light on a 4-8GB office PC: all our pages are
    # the SAME site (the in-process server), so share ONE renderer process for
    # them instead of one per page. Big RAM/CPU saving with 3 embedded pages.
    # Must be set BEFORE QtWebEngine initialises.
    # --ignore-gpu-blocklist / --enable-gpu-rasterization: the office PCs have
    # old GPUs (e.g. Intel HD 3000, 2011) that Chromium blocklists, silently
    # falling back to SwiftShader = SOFTWARE rendering. That makes the embedded
    # pages slow to draw AND makes Qt's one-time window rebuild look like a
    # lurching flicker instead of an instant blink. Forcing the GPU on gives the
    # pages hardware drawing again. If a PC's GPU is too broken for this, set
    # TIMBER_FORCE_GPU=0 in its .env to fall back to software rendering.
    _gpu = "" if os.getenv("TIMBER_FORCE_GPU", "1").strip().lower() in ("0", "off", "false", "no") \
        else "--ignore-gpu-blocklist --enable-gpu-rasterization "
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        f"{_gpu}--process-per-site --disable-features=Translate,MediaRouter",
    )

    # Required for embedded web views (QtWebEngine) — must be set before the app.
    from PySide6.QtCore import Qt

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    _step("QApplication")
    app.setApplicationName(config.APP_NAME)
    # Do NOT quit when the "last" window closes. The login card, a transient
    # QtWebEngine view (dashboard/warm-up), or a reparent during login can each
    # momentarily leave zero visible windows — with the Qt default that would
    # QUIT the whole app mid-login (the "it closes then reopens" the client saw).
    # The app now exits ONLY on an explicit quit (main window closed / login
    # cancelled). See MainWindow.closeEvent.
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.build_stylesheet())
    _step("stylesheet")
    app.setLayoutDirection(i18n.layout_direction())
    _install_excepthook()

    # Background English->Urdu translation of free-text data.
    if config.TRANSLATE_ENABLED:
        from timber.core import translate
        from timber.ui.translation_worker import get_service

        service = get_service()
        translate.set_enqueue(service.enqueue)
        app.aboutToQuit.connect(service.shutdown)
        _step("translate service")

    # Open the first DB connection on a background thread, in parallel with the
    # (slow) window construction, so no screen pays the connect cost later.
    _prewarm_db_async()
    _step("db prewarm started")

    # Single-instance guard: a second launch (e.g. double-click) shouldn't
    # start another copy racing on the same database.
    from PySide6.QtCore import QLockFile

    config.ensure_dirs()
    global _LOCK  # keep the lock alive for the whole process lifetime
    _LOCK = QLockFile(str(config.STORAGE_DIR / "app.lock"))
    _LOCK.setStaleLockTime(0)  # auto-recover if a previous run crashed
    if not _LOCK.tryLock(200):
        QMessageBox.information(
            None, config.APP_NAME, i18n.tr("already_running")
        )
        return 0

    # Show the application shell (sidebar + header + loading skeletons) at
    # once, then run the database init and the login dialog ON TOP of it. The
    # user sees the program open immediately instead of a blank, frozen window.
    global _MAIN_WINDOW
    _step("lock acquired")
    window = MainWindow()  # no user yet — skeleton only
    _step("MainWindow built")
    _MAIN_WINDOW = window

    # Give the window a native handle up front — CHEAP (no Chromium). With
    # AA_ShareOpenGLContexts this lets the dashboard web view attach later
    # without Qt recreating the whole window (the hide/show that looked like
    # "close then reopen"). We deliberately do NOT warm Chromium before show:
    # in a PyInstaller build that blocks startup for 30-40s. Chromium is warmed
    # in the background AFTER login instead (see _finish_startup).
    window.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)

    window.showMaximized()
    app.processEvents()              # paint the skeleton before the DB work
    _step("window shown")

    from PySide6.QtCore import QTimer

    from timber.db.engine import reset_pool

    def _finish_startup() -> None:
        _step("db init done")
        window.hide_reconnecting()
        # Every screen is now NATIVE (no embedded web/QtWebEngine anywhere), so
        # the window's native handle is never recreated — there is no taskbar
        # 'close then reopen' at open, at login, or on any page. Just float the
        # sign-in card over the shell.
        window.show_login()
        _step("LOGIN VISIBLE")

    def _retry_startup() -> None:
        # Background retry loop, entered ONLY after a connection failure so the
        # healthy path stays fast. Keeps trying until the server is reachable.
        try:
            _startup_init()
        except Exception as exc:  # noqa: BLE001
            if _is_db_connection_error(exc):
                log.warning("Database still unreachable; retrying: %s", exc)
                reset_pool()  # drop dead sockets so the next try dials fresh
                QTimer.singleShot(4000, _retry_startup)
                return
            log.exception("Database init failed")
            _show_db_error(exc)
            app.quit()
            return
        _finish_startup()

    # First attempt is SYNCHRONOUS so a healthy start is fast. Only if the
    # database is unreachable do we switch to the non-blocking retry loop: the
    # window stays open, shows the reconnecting card, and recovers on its own.
    try:
        _startup_init()
    except Exception as exc:  # noqa: BLE001
        if _is_db_connection_error(exc):
            log.warning("Database unreachable at startup; retrying in bg: %s", exc)
            window.show_reconnecting(_db_unreachable_message(with_retry_hint=True))
            reset_pool()
            QTimer.singleShot(4000, _retry_startup)
        else:
            log.exception("Database init failed")
            _show_db_error(exc)
            return 1
    else:
        _finish_startup()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
