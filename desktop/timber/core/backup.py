"""Backup / restore / prune — backend-aware.

- SQLite: uses SQLite's online backup API (safe while the app is open),
  producing a ``timber_<stamp>.db`` copy.
- PostgreSQL: shells out to ``pg_dump`` to produce a restorable plain-SQL
  ``timber_<stamp>.sql`` dump (``--clean --if-exists`` so it can be
  replayed over an existing database).

The destination folder is configurable (Settings -> Backup folder). Point
it at a "Google Drive for Desktop" synced folder and every backup is
uploaded to Google Drive automatically.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from timber import config
from timber.core import app_settings
from timber.db.engine import engine

log = logging.getLogger(__name__)

_PREFIX = "timber_"
_SQLITE_SUFFIX = ".db"
_PG_SUFFIX = ".sql"

# Where to look for pg_dump / psql if they aren't on PATH (Windows installs).
_PG_BIN_GLOBS = [
    r"C:\Program Files\PostgreSQL\*\bin",
    r"C:\Program Files (x86)\PostgreSQL\*\bin",
]


# --- backup folder (configurable; defaults to storage/backups) -------
def get_backup_dir() -> Path:
    """The folder backups are written to. Override via Settings; defaults
    to ``storage/backups``. Set it to a Google Drive folder to sync."""
    saved = app_settings.get("backup_dir")
    return Path(saved) if saved else config.BACKUP_DIR


def set_backup_dir(path: Path | str) -> None:
    app_settings.set("backup_dir", str(path))


# --- locating PostgreSQL tools ---------------------------------------
def _find_pg_tool(name: str) -> str:
    """Locate pg_dump/psql on PATH or in a standard PostgreSQL install."""
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if os.name == "nt" else "")
    # Allow an explicit override, then probe common install locations.
    override = app_settings.get("pg_bin_dir")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override) / exe)
    for pattern in _PG_BIN_GLOBS:
        base = Path(pattern).parent
        if base.exists():
            for d in sorted(base.glob(Path(pattern).name), reverse=True):
                candidates.append(d / exe)
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError(
        f"Could not find {name}. Install PostgreSQL client tools, or set the "
        "PostgreSQL bin folder in Settings."
    )


def _pg_env() -> dict:
    env = os.environ.copy()
    if config.PG_PASSWORD:
        env["PGPASSWORD"] = config.PG_PASSWORD
    return env


# --- backup ----------------------------------------------------------
def backup_now(dest_dir: Path | str | None = None) -> Path:
    """Create a timestamped backup of the active database. Returns the path."""
    dest_dir = Path(dest_dir or get_backup_dir())
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if config.DB_BACKEND == "postgresql":
        dest = dest_dir / f"{_PREFIX}{stamp}{_PG_SUFFIX}"
        pg_dump = _find_pg_tool("pg_dump")
        cmd = [
            pg_dump,
            "-h", config.PG_HOST,
            "-p", str(config.PG_PORT),
            "-U", config.PG_USER,
            "-d", config.PG_DB,
            "--clean", "--if-exists",
            "-f", str(dest),
        ]
        result = subprocess.run(
            cmd, env=_pg_env(), capture_output=True, text=True
        )
        if result.returncode != 0:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
        return dest

    # SQLite
    src = config.SQLITE_PATH
    if not Path(src).exists():
        raise FileNotFoundError("No database file to back up yet.")
    dest = dest_dir / f"{_PREFIX}{stamp}{_SQLITE_SUFFIX}"
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dest))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()
    return dest


def list_backups(backup_dir: Path | str | None = None) -> list[Path]:
    backup_dir = Path(backup_dir or get_backup_dir())
    if not backup_dir.exists():
        return []
    files = list(backup_dir.glob(f"{_PREFIX}*{_SQLITE_SUFFIX}"))
    files += list(backup_dir.glob(f"{_PREFIX}*{_PG_SUFFIX}"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


# --- restore ---------------------------------------------------------
def restore_from(backup_path: Path | str) -> None:
    """Replace the live database with a backup. The app should restart
    afterwards."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError("Backup file not found.")

    if config.DB_BACKEND == "postgresql":
        if backup_path.suffix.lower() != _PG_SUFFIX:
            raise RuntimeError(
                "This database is PostgreSQL; choose a .sql backup to restore."
            )
        psql = _find_pg_tool("psql")
        engine.dispose()
        cmd = [
            psql,
            "-h", config.PG_HOST,
            "-p", str(config.PG_PORT),
            "-U", config.PG_USER,
            "-d", config.PG_DB,
            "-f", str(backup_path),
        ]
        result = subprocess.run(
            cmd, env=_pg_env(), capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql restore failed: {result.stderr.strip()}")
        return

    if backup_path.suffix.lower() != _SQLITE_SUFFIX:
        raise RuntimeError(
            "This database is SQLite; choose a .db backup to restore."
        )
    engine.dispose()
    shutil.copy2(backup_path, config.SQLITE_PATH)


def prune_backups(keep_days: int = 30, backup_dir: Path | str | None = None) -> int:
    """Delete backups older than ``keep_days``. Returns count removed.
    ``keep_days <= 0`` means keep everything."""
    if keep_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    for path in list_backups(backup_dir):
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink()
            removed += 1
    return removed


# --- automatic backup settings + helpers -----------------------------
def get_auto_on_close() -> bool:
    return bool(app_settings.get("auto_backup_on_close", True))


def set_auto_on_close(value: bool) -> None:
    app_settings.set("auto_backup_on_close", bool(value))


def get_interval_hours() -> int:
    """How often to auto-backup while the app runs; 0 = off."""
    try:
        return int(app_settings.get("backup_interval_hours", 6) or 0)
    except (TypeError, ValueError):
        return 0


def set_interval_hours(value: int) -> None:
    app_settings.set("backup_interval_hours", int(value))


def get_keep_days() -> int:
    """How long to keep old backups; 0 = keep forever."""
    try:
        return int(app_settings.get("backup_keep_days", 30) or 0)
    except (TypeError, ValueError):
        return 30


def set_keep_days(value: int) -> None:
    app_settings.set("backup_keep_days", int(value))


def last_backup_time() -> datetime | None:
    """Timestamp of the most recent backup file, or None if there are none."""
    files = list_backups()
    if not files:
        return None
    return datetime.fromtimestamp(files[0].stat().st_mtime)


def interval_backup_due() -> bool:
    """True if an interval backup is configured and enough time has passed."""
    hours = get_interval_hours()
    if hours <= 0:
        return False
    last = last_backup_time()
    if last is None:
        return True
    return (datetime.now() - last) >= timedelta(hours=hours)


def auto_backup(min_gap_minutes: int = 0) -> Path | None:
    """Best-effort backup + prune for scheduled/on-close use. Never raises;
    skips if a backup was already made within ``min_gap_minutes``. Returns
    the new backup path, or None if skipped/failed."""
    last = last_backup_time()
    if (
        min_gap_minutes
        and last is not None
        and (datetime.now() - last) < timedelta(minutes=min_gap_minutes)
    ):
        return None
    try:
        dest = backup_now()
    except Exception:  # noqa: BLE001 - background task, must not crash the app
        log.exception("Automatic backup failed")
        return None
    try:
        prune_backups(get_keep_days())
    except Exception:  # noqa: BLE001
        log.exception("Pruning old backups failed")
    return dest
