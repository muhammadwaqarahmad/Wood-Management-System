"""Background translation worker.

Free-text strings that aren't cached yet are queued here. A worker thread
calls the online translation service (so the UI never blocks), writes the
result to the shared ``translations`` cache, and emits ``updated`` so the
current screen can refresh and show the Urdu text.
"""

from __future__ import annotations

import queue

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from timber.core import translate
from timber.db.engine import SessionLocal


class _Worker(QThread):
    translated = Signal(str, str, str)  # (source, target, result)

    def __init__(self, q: "queue.Queue") -> None:
        super().__init__()
        self._q = q
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:  # shutdown sentinel
                break
            text, target = item
            result = translate.remote_translate(text, target)
            if result and result != text:
                self.translated.emit(text, target, result)


class TranslationService(QObject):
    """Owns the queue + worker. ``updated`` fires (debounced) when new
    translations have been cached, so screens can refresh."""

    updated = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: "queue.Queue" = queue.Queue()
        self._pending: set[tuple[str, str]] = set()
        self._worker = _Worker(self._queue)
        self._worker.translated.connect(self._on_translated)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(600)
        self._debounce.timeout.connect(self.updated.emit)
        self._worker.start()

    def enqueue(self, text: str, target: str) -> None:
        key = (text, target)
        if key in self._pending or translate.is_cached(text, target):
            return
        self._pending.add(key)
        self._queue.put(key)

    def _on_translated(self, source: str, target: str, result: str) -> None:
        # Runs on the main thread: safe to touch the DB + memory cache.
        translate.remember(source, target, result)
        self._pending.discard((source, target))
        try:
            from timber.db.models import Translation

            with SessionLocal() as session:
                exists = session.query(Translation).filter_by(
                    source_text=source, target_lang=target
                ).first()
                if exists is None:
                    session.add(Translation(
                        source_text=source, target_lang=target,
                        translated_text=result,
                    ))
                    session.commit()
        except Exception:  # noqa: BLE001 - cache write is best-effort
            pass
        self._debounce.start()  # coalesce many updates into one refresh

    def shutdown(self) -> None:
        self._worker._running = False
        self._queue.put(None)
        self._worker.wait(2000)


_SERVICE: "TranslationService | None" = None


def get_service() -> "TranslationService":
    """Process-wide singleton (created after the QApplication exists)."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TranslationService()
    return _SERVICE
