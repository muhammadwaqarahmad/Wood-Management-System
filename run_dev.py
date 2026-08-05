"""Developer auto-reload runner.

Launches the app and watches the source tree; whenever a .py file changes
(anywhere under ``timber/``, ``alembic/`` or ``run.py``) it automatically
restarts the app — so you just save your edit and the app relaunches, no
need to close and open it yourself.

Usage (development only — NOT shipped to the client):

    ./.venv/Scripts/python.exe run_dev.py

Notes:
- It restarts the WHOLE app (a clean, reliable reload for a Qt desktop app);
  the database is untouched, so your data persists across restarts.
- Close the app window (or press Ctrl+C here) to stop watching.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCH_DIRS = [ROOT / "timber", ROOT / "alembic"]
WATCH_FILES = [ROOT / "run.py"]
POLL_SECONDS = 1.0


def _snapshot() -> dict[Path, float]:
    """Map every watched .py file to its last-modified time."""
    files: dict[Path, float] = {}
    for f in WATCH_FILES:
        if f.is_file():
            files[f] = f.stat().st_mtime
    for d in WATCH_DIRS:
        if d.is_dir():
            for p in d.rglob("*.py"):
                try:
                    files[p] = p.stat().st_mtime
                except OSError:
                    pass
    return files


def _start() -> subprocess.Popen:
    print("\n[auto-reload] starting app…")
    return subprocess.Popen([sys.executable, str(ROOT / "run.py")])


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # show messages promptly
    except Exception:  # noqa: BLE001
        pass
    print("[auto-reload] watching for code changes… (Ctrl+C to stop)")
    proc = _start()
    state = _snapshot()
    try:
        while True:
            time.sleep(POLL_SECONDS)
            if proc.poll() is not None:
                print("[auto-reload] app closed — stopping.")
                return 0
            current = _snapshot()
            if current != state:
                changed = sorted(
                    p.name for p in current
                    if state.get(p) != current.get(p)
                )
                state = current
                print(f"[auto-reload] change: {', '.join(changed[:5])}"
                      f"{' …' if len(changed) > 5 else ''} — restarting")
                _stop(proc)
                proc = _start()
    except KeyboardInterrupt:
        print("\n[auto-reload] stopping.")
    finally:
        _stop(proc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
